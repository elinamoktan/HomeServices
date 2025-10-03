from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from jobs.models import Worker, Customer, Appointment, WorkerRating, Service, WorkerService, WorkerSubTaskPricing, ServiceCategory, SubTask
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.utils.timezone import make_aware, now
from django.core.mail import send_mail
from django.db.models import Avg, QuerySet, Count
from django.db.models import F, ExpressionWrapper, FloatField
from datetime import datetime
from phonenumber_field.formfields import PhoneNumberField
from django.views.decorators.http import require_POST
from datetime import date
from math import radians, sin, cos, sqrt, asin
from django.core.paginator import Paginator
from django.template.defaultfilters import register
from django.contrib.auth import logout, login, authenticate
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging
from .models import FavoriteWorker 
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt 

# ✅ FIXED: Import CustomUser instead of User
try:
    from accounts.models import CustomUser
except ImportError:
    # Fallback if CustomUser doesn't exist
    from django.contrib.auth.models import User as CustomUser

# OTP imports
from otp_auth.models import OTP
from otp_auth.utils import send_otp_via_email

# Configure logging for email failures
logger = logging.getLogger(__name__)


# Add these helper functions after the imports
def get_client_ip(request):
    """Get client IP address for geolocation fallback"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def update_user_location_with_coords(user, latitude, longitude, accuracy=None, source='browser'):
    """
    Update user location with coordinates - REPLACES old location
    """
    try:
        # Try worker profile first
        if hasattr(user, 'worker'):
            worker = user.worker
            # Replace old location with new location
            worker.latitude = latitude
            worker.longitude = longitude
            worker.location_accuracy = accuracy
            worker.location_source = source
            worker.location_updated_at = timezone.now()
            worker.save(update_fields=['latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'])
            logger.info(f"Updated worker {worker.name} location to ({latitude}, {longitude}) from {source}")
        
        # Try customer profile
        elif hasattr(user, 'customer'):
            customer = user.customer
            # Replace old location with new location
            customer.latitude = latitude
            customer.longitude = longitude
            customer.location_accuracy = accuracy
            customer.location_source = source
            customer.location_updated_at = timezone.now()
            customer.save(update_fields=['latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'])
            logger.info(f"Updated customer {customer.name} location to ({latitude}, {longitude}) from {source}")
            
    except Exception as e:
        logger.error(f"Error updating location with coordinates: {e}")

def update_user_location_with_ip(user, ip_address):
    """
    Update user location using IP geolocation (fallback) - REPLACES old location
    """
    try:
        # Try to import geocoder
        try:
            import geocoder
            GEOCODER_AVAILABLE = True
        except ImportError:
            GEOCODER_AVAILABLE = False
            logger.warning("geocoder module not available. Install with: pip install geocoder")
            return

        if GEOCODER_AVAILABLE:
            # Use free IP geolocation service
            g = geocoder.ip(ip_address)
            if g.ok and g.latlng:
                latitude, longitude = g.latlng
                
                if hasattr(user, 'worker'):
                    worker = user.worker
                    worker.latitude = latitude
                    worker.longitude = longitude
                    worker.location_accuracy = 5000  # IP geolocation is less accurate
                    worker.location_source = 'ip'
                    worker.location_updated_at = timezone.now()
                    worker.save(update_fields=['latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'])
                    
                elif hasattr(user, 'customer'):
                    customer = user.customer
                    customer.latitude = latitude
                    customer.longitude = longitude
                    customer.location_accuracy = 5000
                    customer.location_source = 'ip'
                    customer.location_updated_at = timezone.now()
                    customer.save(update_fields=['latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'])
                    
                logger.info(f"Updated {user.username} location via IP to ({latitude}, {longitude})")
                
    except Exception as e:
        logger.error(f"Error updating location via IP: {e}")
def index(request):
    return HttpResponse("<h1>BlueCaller</h1>")

@csrf_exempt
def store_landing_location(request):
    """
    Store location captured on landing page in session for later use
    """
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            accuracy = data.get('accuracy')
            
            if not latitude or not longitude:
                return JsonResponse({'error': 'Latitude and longitude required'}, status=400)
            
            # Store in session for use after login
            request.session['landing_location'] = {
                'latitude': float(latitude),
                'longitude': float(longitude),
                'accuracy': float(accuracy) if accuracy else None,
                'timestamp': timezone.now().isoformat()
            }
            
            logger.info(f"Landing location stored in session: ({latitude}, {longitude})")
            
            return JsonResponse({
                'success': True,
                'message': 'Location stored successfully'
            })
            
        except Exception as e:
            logger.error(f"Error storing landing location: {e}")
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

def service_categories(request):
    """
    View to display all service categories with their services, subtasks, durations, and pricing
    """
    categories = ServiceCategory.objects.all().prefetch_related(
        'services', 
        'services__subtasks'
    )
    
    # Get worker services with pricing if user is authenticated and is a worker
    worker_services = None
    if request.user.is_authenticated:
        try:
            worker = Worker.objects.get(owner=request.user)
            worker_services = WorkerService.objects.filter(
                worker=worker
            ).prefetch_related(
                'pricing',
                'pricing__subtask'
            )
        except Worker.DoesNotExist:
            pass
    
    context = {
        'categories': categories,
        'worker_services': worker_services,
    }
    
    return render(request, 'jobs/service_categories.html', context)

# Enhanced email functions with better formatting and error handling
def send_appointment_request_email(worker, appointment):
    """Send email notification to worker when customer requests an appointment"""
    try:
        subject = f"New Appointment Request - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}"
        
        # Get price information safely
        price_info = "Contact for pricing"
        if appointment.service_subtask and appointment.service_subtask.price:
            price_info = f"₹{appointment.service_subtask.price}"
        
        # Create HTML email template
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">New Appointment Request</h2>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #007bff; margin-top: 0;">Appointment Details</h3>
                    <p><strong>Customer:</strong> {appointment.customer.name}</p>
                    <p><strong>Service:</strong> {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Not specified'}</p>
                    <p><strong>Price:</strong> {price_info}</p>
                    <p><strong>Date & Time:</strong> {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}</p>
                    <p><strong>Location:</strong> {appointment.location or 'Not specified'}</p>
                    {f"<p><strong>Special Instructions:</strong> {appointment.special_instructions}</p>" if appointment.special_instructions else ""}
                </div>
                
                <div style="background: #e8f4f8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="color: #17a2b8; margin-top: 0;">What's Next?</h4>
                    <p>Please log in to your BlueCaller dashboard to:</p>
                    <ul>
                        <li>Accept or reject this appointment request</li>
                        <li>View customer contact information</li>
                        <li>Communicate with the customer</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{settings.SITE_URL}/worker/dashboard/" 
                       style="background: #007bff; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        View Dashboard
                    </a>
                </div>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from BlueCaller. 
                    Please do not reply to this email directly.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
New Appointment Request

Dear {worker.name},

You have received a new appointment request from {appointment.customer.name}.

Appointment Details:
- Service: {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Not specified'}
- Price: {price_info}
- Date & Time: {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}
- Location: {appointment.location or 'Not specified'}
{f"- Special Instructions: {appointment.special_instructions}" if appointment.special_instructions else ""}

Please log in to your BlueCaller dashboard to accept or reject this request.
Dashboard: {settings.SITE_URL}/worker/dashboard/

Best regards,
BlueCaller Team
        """
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [worker.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Appointment request email sent to worker {worker.name} ({worker.owner.email})")
        
    except Exception as e:
        logger.error(f"Failed to send appointment request email to worker {worker.name}: {str(e)}")
        # Don't raise the exception to prevent appointment creation from failing
        pass

def send_appointment_status_email(appointment, status):
    """Send email notification to customer when appointment status changes"""
    try:
        customer = appointment.customer
        worker = appointment.worker
        
        # Get price information safely
        price_info = "Contact for pricing"
        if appointment.service_subtask and appointment.service_subtask.price:
            price_info = f"₹{appointment.service_subtask.price}"
        
        if status == 'accepted':
            subject = f"Appointment Confirmed - {worker.name}"
            status_message = "Your appointment has been confirmed!"
            status_color = "#28a745"
            next_steps = """
            <p>Your appointment is now confirmed. Here's what happens next:</p>
            <ul>
                <li>The worker will contact you if needed</li>
                <li>Please be available at the scheduled time</li>
                <li>You can contact the worker through our platform</li>
            </ul>
            """
        else:  # rejected
            subject = f"Appointment Update - {worker.name}"
            status_message = "Your appointment request was declined"
            status_color = "#dc3545"
            next_steps = """
            <p>Unfortunately, this worker was unable to accept your appointment. You can:</p>
            <ul>
                <li>Browse other available workers</li>
                <li>Try a different date and time with the same worker</li>
                <li>Contact our support team for assistance</li>
            </ul>
            """
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Appointment Update</h2>
                
                <div style="background: {status_color}; color: white; padding: 15px; 
                           border-radius: 8px; text-align: center; margin: 20px 0;">
                    <h3 style="margin: 0;">{status_message}</h3>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #007bff; margin-top: 0;">Appointment Details</h3>
                    <p><strong>Worker:</strong> {worker.name}</p>
                    <p><strong>Service:</strong> {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Not specified'}</p>
                    <p><strong>Price:</strong> {price_info}</p>
                    <p><strong>Date & Time:</strong> {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}</p>
                    <p><strong>Location:</strong> {appointment.location or 'Not specified'}</p>
                    {f"<p><strong>Special Instructions:</strong> {appointment.special_instructions}</p>" if appointment.special_instructions else ""}
                </div>
                
                <div style="background: #e8f4f8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="color: #17a2b8; margin-top: 0;">What's Next?</h4>
                    {next_steps}
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{settings.SITE_URL}/customer/appointments/" 
                       style="background: #007bff; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        View My Appointments
                    </a>
                    <a href="{settings.SITE_URL}/get-started/" 
                       style="background: #28a745; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block; margin-left: 10px;">
                        Browse Workers
                    </a>
                </div>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from BlueCaller. 
                    Please do not reply to this email directly.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
Appointment Update

Dear {customer.name},

{status_message}

Appointment Details:
- Worker: {worker.name}
- Service: {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Not specified'}
- Price: {price_info}
- Date & Time: {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}
- Location: {appointment.location or 'Not specified'}
{f"- Special Instructions: {appointment.special_instructions}" if appointment.special_instructions else ""}

View your appointments: {settings.SITE_URL}/customer/appointments/
Browse workers: {settings.SITE_URL}/get-started/

Best regards,
BlueCaller Team
        """
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [customer.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Appointment status email ({status}) sent to customer {customer.name} ({customer.owner.email})")
        
    except Exception as e:
        logger.error(f"Failed to send appointment status email to customer {customer.name}: {str(e)}")
        # Don't raise the exception to prevent the main action from failing
        pass

def send_appointment_completion_email(appointment):
    """Send email notification when appointment is completed"""
    try:
        customer = appointment.customer
        worker = appointment.worker
        
        subject = f"Appointment Completed - Please Rate Your Experience"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Appointment Completed</h2>
                
                <div style="background: #28a745; color: white; padding: 15px; 
                           border-radius: 8px; text-align: center; margin: 20px 0;">
                    <h3 style="margin: 0;">Your appointment has been completed!</h3>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #007bff; margin-top: 0;">Appointment Details</h3>
                    <p><strong>Worker:</strong> {worker.name}</p>
                    <p><strong>Service:</strong> {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Not specified'}</p>
                    <p><strong>Date & Time:</strong> {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
                
                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <h4 style="color: #856404; margin-top: 0;">Rate Your Experience</h4>
                    <p style="color: #856404;">
                        Help other customers by rating your experience with {worker.name}. 
                        Your feedback helps maintain service quality on our platform.
                    </p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{settings.SITE_URL}/rate-worker/{appointment.id}/" 
                       style="background: #ffc107; color: #333; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Rate & Review
                    </a>
                    <a href="{settings.SITE_URL}/customer/appointments/" 
                       style="background: #007bff; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block; margin-left: 10px;">
                        View Appointments
                    </a>
                </div>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated message from BlueCaller. 
                    Please do not reply to this email directly.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
Appointment Completed

Dear {customer.name},

Your appointment with {worker.name} has been completed!

Appointment Details:
- Worker: {worker.name}
- Service: {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Not specified'}
- Date & Time: {appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')}

Please take a moment to rate your experience: {settings.SITE_URL}/rate-worker/{appointment.id}/
View your appointments: {settings.SITE_URL}/customer/appointments/

Best regards,
BlueCaller Team
        """
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [customer.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Appointment completion email sent to customer {customer.name} ({customer.owner.email})")
        
    except Exception as e:
        logger.error(f"Failed to send appointment completion email to customer {customer.name}: {str(e)}")
        raise

def _haversine_km(lat1, lon1, lat2, lon2):
    """Return distance in km between two lat/lon points using Haversine formula."""
    try:
        # Check for None values
        if None in (lat1, lon1, lat2, lon2):
            return float('inf')
        
        # Convert to floats
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        
        # Validate coordinate ranges
        if not (-90 <= lat1 <= 90) or not (-180 <= lon1 <= 180) or \
           not (-90 <= lat2 <= 90) or not (-180 <= lon2 <= 180):
            return float('inf')
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon/2) ** 2
        c = 2 * asin(sqrt(a))
        
        # Earth radius in kilometers
        return 6371.0 * c
        
    except (ValueError, TypeError):
        return float('inf')

class WorkerListView(ListView):
    model = Worker
    template_name = 'jobs/worker_list.html'

    def get_queryset(self):
        query = self.request.GET.get('q')
        filter_param = self.request.GET.get('filter')
        service_filter = self.request.GET.get('service')
        max_distance = self.request.GET.get('max_distance')

        queryset = Worker.objects.all()

        if query:
            queryset = queryset.filter(tagline__icontains=query)
            
        if service_filter:
            # Filter workers who offer this service
            queryset = queryset.filter(services__service__id=service_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        query = self.request.GET.get('q')
        context['q'] = query
        filter_param = self.request.GET.get('filter')
        service_filter = self.request.GET.get('service')
        max_distance = self.request.GET.get('max_distance')
        
        # Add services for filtering
        context['all_services'] = Service.objects.all()
        context['selected_service'] = service_filter
        context['max_distance'] = max_distance

        # Get the base queryset
        workers_qs = context.get('object_list', self.get_queryset())

        # Get customer info if available
        customer = getattr(self.request.user, 'customer', None)
        cust_lat = None
        cust_lon = None
        
        # PRIORITY 1: Check for landing page location (most recent)
        landing_location = self.request.session.get('landing_location')
        if landing_location:
            try:
                cust_lat = float(landing_location['latitude'])
                cust_lon = float(landing_location['longitude'])
                logger.info("Using landing page location for worker sorting")
            except (ValueError, TypeError, KeyError):
                cust_lat = None
                cust_lon = None
        
        # PRIORITY 2: Check session location (from login/updates)
        if cust_lat is None:
            current_lat = self.request.session.get('current_latitude')
            current_lon = self.request.session.get('current_longitude')
            
            if current_lat and current_lon:
                cust_lat = current_lat
                cust_lon = current_lon
                logger.info("Using session location for worker sorting")
        
        # PRIORITY 3: Fallback to database location
        if cust_lat is None and customer:
            if customer.latitude and customer.longitude:
                try:
                    cust_lat = float(customer.latitude)
                    cust_lon = float(customer.longitude)
                    logger.info("Using database location for worker sorting")
                except (ValueError, TypeError):
                    cust_lat = None
                    cust_lon = None

        # Create a list of dictionaries with worker and distance info
        workers_with_distance = []
        
        for w in workers_qs:
            distance_km = None
            
            # Calculate distance if customer has coordinates and worker has coordinates
            if cust_lat is not None and cust_lon is not None and w.latitude and w.longitude:
                try:
                    worker_lat = float(w.latitude)
                    worker_lon = float(w.longitude)
                    distance_km = _haversine_km(worker_lat, worker_lon, cust_lat, cust_lon)
                    if distance_km == float('inf'):
                        distance_km = None
                    else:
                        distance_km = round(distance_km, 2)
                except (ValueError, TypeError):
                    distance_km = None
            
            # Create a dictionary with worker and distance info
            worker_info = {
                'worker': w,
                'distance_km': distance_km
            }
            workers_with_distance.append(worker_info)
        
        # ✅ NEW: Apply distance filtering if max_distance is provided
        if max_distance and cust_lat is not None and cust_lon is not None:
            try:
                max_distance_float = float(max_distance)
                # Filter workers within the specified distance
                workers_with_distance = [
                    worker_info for worker_info in workers_with_distance 
                    if worker_info['distance_km'] is not None and worker_info['distance_km'] <= max_distance_float
                ]
            except (ValueError, TypeError):
                # If max_distance is invalid, ignore the filter
                pass
        
        # Apply filters - DEFAULT SORTING BY DISTANCE
        if filter_param == 'rating':
            # First, annotate each worker with their average rating
            for worker_info in workers_with_distance:
                w = worker_info['worker']
                average_rating = w.bayesian_average_rating()
                worker_info['average_rating'] = average_rating
                worker_info['total_ratings'] = w.ratings.count()
            
            # Then sort by average rating (descending)
            workers_with_distance.sort(key=lambda x: x.get('average_rating', 0), reverse=True)
        
        else:
            # DEFAULT: Sort by distance (nearest first) when customer has location
            # This will apply by default AND when filter_param == 'distance'
            if cust_lat is not None and cust_lon is not None:
                # Sort by distance (nearest first), workers without distance go to the end
                workers_with_distance.sort(key=lambda x: 
                    x['distance_km'] if x['distance_km'] is not None else float('inf'))
            else:
                # If no customer location, sort by rating as fallback
                for worker_info in workers_with_distance:
                    w = worker_info['worker']
                    average_rating = w.bayesian_average_rating()
                    worker_info['average_rating'] = average_rating
                
                workers_with_distance.sort(key=lambda x: x.get('average_rating', 0), reverse=True)
        
        # Add rating information to each worker for display
        for worker_info in workers_with_distance:
            w = worker_info['worker']
            average_rating = w.bayesian_average_rating()
            w.average_rating = average_rating
            w.total_ratings = w.ratings.count()
            breakdown = w.get_rating_breakdown()
            w.rating_breakdown = breakdown

            full_stars = int(average_rating)
            half_star = 1 if average_rating % 1 >= 0.5 else 0
            empty_stars = 5 - (full_stars + half_star)

            w.full_stars = range(full_stars)
            w.half_star = half_star
            w.empty_stars = range(empty_stars)
            
            # Add distance to worker object for template access
            w.distance_km = worker_info['distance_km']

        # Replace the object_list with our sorted list of workers
        context['object_list'] = [worker_info['worker'] for worker_info in workers_with_distance]
        context['workers_with_distance'] = workers_with_distance
        
        # Add location context for template
        context['customer_location'] = {
            'latitude': cust_lat,
            'longitude': cust_lon,
            'source': 'session' if current_lat else 'database'
        } if cust_lat and cust_lon else None
        
        # Add filter context for template
        context['current_filter'] = filter_param or 'distance'  # default to distance
        
        return context   
# Class-based view for worker detail
class WorkerDetailView(LoginRequiredMixin, DetailView):
    model = Worker
    template_name = 'jobs/worker_detail.html'

    def get_queryset(self):
        return Worker.objects.all()

    def get_object(self, queryset=None):
        worker = super().get_object(queryset)
        
        if self.request.user != worker.owner and not hasattr(self.request.user, 'customer'):
            raise PermissionDenied("You do not have permission to view this worker's details.")
        return worker

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker = self.get_object()

        average_rating = worker.bayesian_average_rating()
        total_ratings = worker.ratings.count()
        
        full_stars = int(average_rating)
        half_star = 1 if average_rating % 1 >= 0.5 else 0
        empty_stars = 5 - (full_stars + half_star)
        
        # Get rating breakdown
        rating_breakdown = {}
        for i in range(1, 6):
            rating_breakdown[i] = WorkerRating.objects.filter(worker=worker, rating=i).count()
        
        # Get services with pricing for this worker
        services_with_pricing = []
        worker_services = WorkerService.objects.filter(worker=worker).select_related('service')
        
        for worker_service in worker_services:
            subtasks_with_pricing = WorkerSubTaskPricing.objects.filter(
                worker_service=worker_service
            ).select_related('subtask')
            
            # Prepare subtask data with pricing information
            subtasks_data = []
            for pricing in subtasks_with_pricing:
                subtask_data = {
                    'id': pricing.id,
                    'name': pricing.subtask.name,
                    'description': pricing.subtask.description,
                    'price': pricing.price,
                    'pricing_type': pricing.pricing_type,
                    'pricing_type_display': pricing.get_pricing_type_display(),
                    'experience_level': pricing.experience_level,
                    'night_shift_extra': pricing.night_shift_extra,
                    'is_night_shift': False  # Will be set based on selection
                }
                subtasks_data.append(subtask_data)
            
            services_with_pricing.append({
                'service': worker_service.service,
                'subtasks': subtasks_data
            })

        # Get portfolio images if available (placeholder - you'll need to implement this model)
        portfolio_images = []
        # If you have a PortfolioImage model, you can query it here
        # portfolio_images = worker.portfolio_images.all()[:6]  # Example
        
        # Calculate distance if customer is viewing
        distance_km = None
        if hasattr(self.request.user, 'customer'):
            customer = self.request.user.customer
            if customer.latitude and customer.longitude and worker.latitude and worker.longitude:
                try:
                    distance_km = _haversine_km(
                        float(worker.latitude), float(worker.longitude),
                        float(customer.latitude), float(customer.longitude)
                    )
                    distance_km = round(distance_km, 2)
                except (ValueError, TypeError):
                    distance_km = None

        context.update({
            'average_rating': average_rating,
            'total_ratings': total_ratings,
            'full_stars': range(full_stars),
            'half_star': half_star,
            'empty_stars': range(empty_stars),
            'rating_breakdown': rating_breakdown,
            'min_date': date.today().strftime('%Y-%m-%d'),
            'services_with_pricing': services_with_pricing,
            'portfolio_images': portfolio_images,
            'distance_km': distance_km,
            'today': date.today(),  # Add today's date
        })
        
        return context

# ENHANCED: API endpoint for worker services with detailed information
# Add this to your views.py - Fixed worker_services_api function

@login_required
def worker_services_api(request, worker_id):
    """API endpoint to get worker's services data with detailed information for frontend"""
    worker = get_object_or_404(Worker, id=worker_id)
    
    # Get all services for this worker with their subtasks and pricing
    worker_services = WorkerService.objects.filter(
        worker=worker, 
        is_available=True
    ).select_related(
        'service', 'service__category'
    ).prefetch_related(
        'pricing__subtask'
    )
    
    # Group services by category
    categories_data = {}
    
    for worker_service in worker_services:
        category = worker_service.service.category
        service = worker_service.service
        
        # Initialize category data if not exists
        if category.id not in categories_data:
            categories_data[category.id] = {
                'id': category.id,
                'name': category.name,
                'description': category.description or '',
                'icon': category.icon or 'wrench',
                'services': []
            }
        
        # Get subtasks with pricing for this service
        pricing_entries = WorkerSubTaskPricing.objects.filter(
            worker_service=worker_service
        ).select_related('subtask')
        
        for pricing in pricing_entries:
            subtask = pricing.subtask
            
            # Build features list
            features = [
                "Professional service provider",
                "Quality work guaranteed",
                "Customer support included"
            ]
            
            if pricing.experience_level:
                features.insert(0, f"{pricing.experience_level.title()} level expertise")
            
            if subtask.materials_included:
                features.append("Materials included in price")
            
            # Determine pricing display
            pricing_display = f"₹{pricing.price}"
            if pricing.pricing_type == 'hourly':
                pricing_display += f"/hour (min {pricing.min_hours} hrs)"
            elif pricing.pricing_type == 'sqft':
                pricing_display += "/sq.ft"
            elif pricing.pricing_type == 'unit':
                pricing_display += "/unit"
            elif pricing.pricing_type == 'shift':
                pricing_display += "/shift"
            elif pricing.pricing_type == 'inspection':
                pricing_display += "/inspection"
            
            # Build service item
            service_item = {
                'id': pricing.id,
                'title': subtask.name,
                'description': subtask.description,
                'detailed_description': getattr(subtask, 'detailed_description', ''),
                'price': pricing_display,
                'base_price': float(pricing.price),
                'pricing_type': pricing.pricing_type,
                'pricing_type_display': pricing.get_pricing_type_display(),
                'complexity': pricing.experience_level or 'Standard',
                'duration': subtask.duration or f"Starting from {pricing.min_hours or 1} hour(s)",
                'requirements': subtask.requirements or '',
                'features': features,
                'image': service.image.url if service.image else None,
                'night_shift_extra': float(pricing.night_shift_extra) if pricing.night_shift_extra else 0,
                'has_offer': subtask.special_offer,
                'offer_details': {
                    'original_price': float(subtask.original_price) if subtask.original_price else float(pricing.price),
                    'offer_price': float(subtask.offer_price) if subtask.offer_price else float(pricing.price),
                } if subtask.special_offer else {},
                'requires_inspection': pricing.price == 0,
                'inspection_price_display': 'Price upon inspection' if pricing.price == 0 else '',
                'terms_conditions': 'Terms and conditions apply',
                'materials_included': subtask.materials_included
            }
            
            categories_data[category.id]['services'].append(service_item)
    
    # If no services found, create a default structure
    if not categories_data:
        categories_data['general'] = {
            'id': 'general',
            'name': 'General Services',
            'description': 'Professional services offered by our expert',
            'icon': 'wrench',
            'services': [{
                'id': 'consultation',
                'title': f'Consultation with {worker.name}',
                'description': worker.bio or 'Professional consultation and service assessment',
                'detailed_description': '',
                'price': '₹500/hour',
                'base_price': 500,
                'pricing_type': 'hourly',
                'pricing_type_display': 'Hourly Rate',
                'complexity': 'Standard',
                'duration': '1 hour minimum',
                'requirements': 'Contact for specific requirements',
                'features': [
                    'Professional consultation',
                    'Expert advice',
                    'Quality service',
                    'Customer support'
                ],
                'image': worker.profile_pic.url if worker.profile_pic else None,
                'night_shift_extra': 0,
                'has_offer': False,
                'offer_details': {},
                'requires_inspection': False,
                'inspection_price_display': '',
                'terms_conditions': 'Terms and conditions apply',
                'materials_included': False
            }]
        }
    
    categories_list = list(categories_data.values())
    
    response_data = {
        'worker': {
            'id': worker.id,
            'name': worker.name,
            'tagline': worker.tagline,
            'bio': worker.bio or '',
            'profile_pic': worker.profile_pic.url if worker.profile_pic else None,
            'phone_number': str(worker.phone_number),
            'average_rating': float(worker.average_rating),
            'total_ratings': worker.rating_count,
            'verified': worker.verified
        },
        'categories': categories_list
    }
    
    return JsonResponse(response_data)

    
# Class-based view for creating a worker profile
class WorkerCreateView(LoginRequiredMixin, CreateView):
    model = Worker
    fields = ['name', 'profile_pic', 'tagline', 'phone_number', 'bio', 'citizenship_image', 'certificate_file', 'shift']
    success_url = reverse_lazy('worker-list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        
        # Handle latitude
        try:
            latitude = self.request.POST.get('latitude')
            form.instance.latitude = float(latitude) if latitude else None
        except (ValueError, TypeError):
            form.instance.latitude = None
        
        # Handle longitude
        try:
            longitude = self.request.POST.get('longitude')
            form.instance.longitude = float(longitude) if longitude else None
        except (ValueError, TypeError):
            form.instance.longitude = None
        
        return super(WorkerCreateView, self).form_valid(form)


# Class-based view for creating a customer profile
class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    fields = ['name', 'profile_pic', 'phone_number']
    success_url = reverse_lazy('worker-list')

    def form_valid(self, form):    
        form.instance.owner = self.request.user
        
        # Handle latitude
        try:
            latitude = self.request.POST.get('latitude')
            form.instance.latitude = float(latitude) if latitude else None
        except (ValueError, TypeError):
            form.instance.latitude = None
        
        # Handle longitude
        try:
            longitude = self.request.POST.get('longitude')
            form.instance.longitude = float(longitude) if longitude else None
        except (ValueError, TypeError):
            form.instance.longitude = None
        
        return super(CustomerCreateView, self).form_valid(form)


from allauth.account.views import LoginView as AllauthLoginView
from allauth.account.utils import perform_login

class CustomLoginView(AllauthLoginView):
    """
    Custom login view that captures location data during login
    """
    template_name = 'account/login.html'
    
    def form_valid(self, form):
        """
        Override form_valid to capture location data from hidden fields
        """
        # Get location data from POST (from hidden form fields)
        latitude = self.request.POST.get('latitude', '').strip()
        longitude = self.request.POST.get('longitude', '').strip()
        accuracy = self.request.POST.get('location_accuracy', '').strip()
        
        # Store in session for use after authentication
        if latitude and longitude:
            try:
                self.request.session['pending_location'] = {
                    'latitude': float(latitude),
                    'longitude': float(longitude),
                    'accuracy': float(accuracy) if accuracy else None,
                    'source': 'browser'
                }
                logger.info(f"Location captured during login: ({latitude}, {longitude})")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid location data during login: {e}")
        else:
            # No location data - will use IP fallback
            logger.info("No browser location provided, will use IP fallback")
            self.request.session['pending_location'] = None
        
        # Call parent's form_valid which handles the actual login
        return super().form_valid(form)
    
    def get_success_url(self):
        """
        After successful login, redirect to handle_login which will update location
        """
        return reverse('handle_login')
# MODIFIED: Enhanced handle_login with OTP integration

@login_required
def handle_login(request):
    """Enhanced login handler with automatic location tracking"""
    
    if not request.user.is_authenticated:
        return redirect('account_login')
    
    # Get client IP for fallback geolocation
    client_ip = get_client_ip(request)
    
    # Check for pending location data from login form
    pending_location = request.session.get('pending_location')
    
    if pending_location and isinstance(pending_location, dict):
        # Browser geolocation was captured
        try:
            lat_float = float(pending_location['latitude'])
            lon_float = float(pending_location['longitude'])
            acc_float = pending_location.get('accuracy')
            
            # Store in session for immediate use
            request.session['current_latitude'] = lat_float
            request.session['current_longitude'] = lon_float
            request.session['location_accuracy'] = acc_float
            request.session['location_updated_at'] = timezone.now().isoformat()
            
            # Update user profile location
            update_user_location_with_coords(
                request.user, lat_float, lon_float, acc_float, 'browser'
            )
            logger.info(f"User {request.user.username} location updated from browser: ({lat_float}, {lon_float})")
            
            # Clear pending location
            del request.session['pending_location']
            
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Error processing pending location for user {request.user.username}: {e}")
            # Fallback to IP-based location
            update_user_location_with_ip(request.user, client_ip)
    else:
        # No browser location - use IP-based geolocation as fallback
        logger.info(f"No browser location for user {request.user.username}, trying IP-based location")
        update_user_location_with_ip(request.user, client_ip)
    
    # Check if user needs OTP verification for login
    if request.session.get('needs_login_otp'):
        user_id = request.session.get('login_user_id')
        if user_id:
            return redirect('verify_login_otp', user_id=user_id)
    
    # Try to detect worker profile
    try:
        worker = request.user.worker
        messages.success(request, f"Welcome back, {worker.name}! Your location has been updated.")
        return redirect('worker_dashboard')
    except Worker.DoesNotExist:
        pass

    # Try to detect customer profile
    try:
        customer = request.user.customer
        messages.success(request, f"Welcome back, {customer.name}! Your location has been updated.")
        return redirect('worker-list')
    except Customer.DoesNotExist:
        pass

    # If neither exists, show account setup screen
    return render(request, 'jobs/choose_account.html', {})

def update_user_location_on_login(request, client_ip=None):
    """Update user location on login based on available data"""
    try:
        # Check if we have coordinates from the request (browser geolocation)
        latitude = request.session.get('current_latitude')
        longitude = request.session.get('current_longitude')
        accuracy = request.session.get('location_accuracy')
        
        if latitude and longitude:
            # We have precise browser coordinates
            update_user_location_with_coords(request.user, latitude, longitude, accuracy, 'browser')
        elif client_ip:
            # Fallback to IP-based geolocation
            update_user_location_with_ip(request.user, client_ip)
            
    except Exception as e:
        logger.error(f"Error updating user location on login: {e}")


@csrf_exempt
@login_required
def update_current_location(request):
    """
    API endpoint to update user's current location from browser - REPLACES old location
    """
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            accuracy = data.get('accuracy')
            
            if not latitude or not longitude:
                return JsonResponse({'error': 'Latitude and longitude required'}, status=400)
            
            # Update session for immediate use (replaces old session data)
            request.session['current_latitude'] = float(latitude)
            request.session['current_longitude'] = float(longitude)
            request.session['location_accuracy'] = float(accuracy) if accuracy else None
            request.session['location_updated_at'] = timezone.now().isoformat()
            
            # Update user profile (replaces old database location)
            update_user_location_with_coords(
                request.user, latitude, longitude, accuracy, 'browser'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Location updated successfully',
                'latitude': latitude,
                'longitude': longitude,
                'accuracy': accuracy
            })
            
        except Exception as e:
            logger.error(f"Error updating current location: {e}")
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def get_nearby_workers(request):
    """API endpoint to get nearby workers based on current location"""
    try:
        customer = request.user.customer
        max_distance = request.GET.get('max_distance', 50)  # Default 50km
        
        # Get current location from session or database
        lat = request.session.get('current_latitude')
        lon = request.session.get('current_longitude')
        
        if not lat or not lon:
            # Use database location
            customer_location = customer.get_current_location()
            if customer_location:
                lat = customer_location['latitude']
                lon = customer_location['longitude']
        
        if not lat or not lon:
            return JsonResponse({'error': 'Location not available'}, status=400)
        
        # Find nearby workers
        nearby_workers = customer.find_nearby_workers(max_distance_km=float(max_distance))
        
        workers_data = []
        for worker in nearby_workers:
            workers_data.append({
                'id': worker.id,
                'name': worker.name,
                'tagline': worker.tagline,
                'profile_pic': worker.profile_pic.url if worker.profile_pic else None,
                'average_rating': float(worker.average_rating),
                'distance_km': getattr(worker, 'distance_km', None),
                'verified': worker.verified
            })
        
        return JsonResponse({
            'workers': workers_data,
            'current_location': {
                'latitude': lat,
                'longitude': lon
            },
            'total_count': len(workers_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting nearby workers: {e}")
        return JsonResponse({'error': str(e)}, status=400)


def custom_login(request):
    """
    Custom login view that integrates OTP verification
    This should replace your existing allauth login view
    """
    if request.user.is_authenticated:
        return redirect('handle_login')
    
    if request.method == 'POST':
        username = request.POST.get('login')
        password = request.POST.get('password')
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Generate OTP for login verification
            otp = OTP.create_otp(user, "login")
            send_otp_via_email(user, otp.code)
            
            # Store user ID in session for OTP verification
            request.session['needs_login_otp'] = True
            request.session['login_user_id'] = user.id
            
            messages.info(request, "An OTP has been sent to your email. Please verify to login.")
            return redirect('verify_login_otp', user_id=user.id)
        else:
            messages.error(request, "Invalid credentials. Please try again.")
    
    # If GET request or failed authentication, show login form
    from allauth.account.views import LoginView
    return LoginView.as_view()(request)

# NEW: Custom signup view with OTP integration  
def custom_signup(request):
    """
    Custom signup view that integrates OTP verification
    This should replace your existing allauth signup view
    """
    if request.user.is_authenticated:
        return redirect('handle_login')
    
    if request.method == 'POST':
        # Use allauth's signup form
        from allauth.account.forms import SignupForm
        form = SignupForm(request.POST)
        
        if form.is_valid():
            # Create user but don't activate yet
            user = form.save(commit=False)
            user.is_active = False  # User will be activated after OTP verification
            user.save()
            
            # Generate OTP for signup verification
            otp = OTP.create_otp(user, "signup")
            send_otp_via_email(user, otp.code)
            
            # Store user ID in session for OTP verification
            request.session['needs_signup_otp'] = True
            request.session['signup_user_id'] = user.id
            
            messages.info(request, "An OTP has been sent to your email. Please verify to complete registration.")
            return redirect('verify_signup_otp', user_id=user.id)
    else:
        from allauth.account.forms import SignupForm
        form = SignupForm()
    
    # Use allauth's signup template
    from allauth.account.views import SignupView
    return SignupView.as_view()(request)

@login_required
def appoint_worker(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    
    # Check if user has a customer profile
    try:
        customer = request.user.customer
    except AttributeError:
        messages.error(request, "You need a customer profile to book appointments.")
        return redirect('customer-create')

    if request.method == "POST":
        # Get form data
        appointment_date_str = request.POST.get("appointment_date")
        appointment_time_str = request.POST.get("appointment_time")
        service_type = request.POST.get("service_type")
        specific_service = request.POST.get("specific_service")
        pricing_basis = request.POST.get("pricing_basis")
        quantity = request.POST.get("quantity", "1")
        special_requests = request.POST.get("special_requests", "")

        # Validate required fields
        if not all([appointment_date_str, appointment_time_str, service_type, specific_service]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('worker-detail', pk=worker_id)

        try:
            # Parse datetime
            datetime_str = f"{appointment_date_str} {appointment_time_str}"
            appointment_datetime = make_aware(datetime.strptime(datetime_str, "%Y-%m-%d %H:%M"))
            
            # Check if appointment is in the future
            if appointment_datetime <= now():
                messages.error(request, "You can only book appointments for future dates/times.")
                return redirect('worker-detail', pk=worker_id)

            # Check for conflicting appointments
            conflicting_appointments = Appointment.objects.filter(
                worker=worker,
                appointment_date=appointment_datetime,
                status__in=['pending', 'accepted']
            )
            
            if conflicting_appointments.exists():
                messages.error(request, "Worker already has an appointment at this time.")
                return redirect('worker-detail', pk=worker_id)

            # Create appointment with the available fields
            appointment = Appointment.objects.create(
                customer=customer,
                worker=worker,
                appointment_date=appointment_datetime,
                status="pending",
                service_subtask=None,  # Set to None since we're using service type/specific service
                shift_type=pricing_basis if pricing_basis else None,
                location=special_requests,  # Using special_requests as location for now
                special_instructions=special_requests
            )

            # Send email notification to worker (with better error handling)
            try:
                send_appointment_request_email(worker, appointment)
                logger.info(f"Appointment request email sent successfully for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"Email sending failed for appointment {appointment.id}: {email_error}")
                # Continue without failing the appointment creation
                messages.warning(request, "Appointment created but email notification may have failed.")
            
            messages.success(request, "Appointment request sent to worker successfully.")
            return redirect('customer_appointments')

        except ValueError as e:
            print(f"Error parsing datetime: {e}")
            messages.error(request, "Invalid appointment date or time format.")
            return redirect('worker-detail', pk=worker_id)
        except Exception as e:
            print(f"Unexpected error in appoint_worker: {e}")
            messages.error(request, "An error occurred while processing your request. Please try again.")
            return redirect('worker-detail', pk=worker_id)
    
    return redirect('worker-detail', pk=worker_id)


@login_required
def customer_appointments(request):
    customer = get_object_or_404(Customer, owner=request.user)
    appointments = Appointment.objects.filter(customer=customer).order_by('-appointment_date')
    
    for appointment in appointments:
        appointment.has_rated = WorkerRating.objects.filter(
            appointment=appointment,
            customer=customer
        ).exists()

    # Add current_page context
    context = {
        'appointments': appointments,
        'current_page': 'appointments'
    }
    
    return render(request, 'jobs/customer_dashboard.html', context)

@require_POST
@login_required
def request_new_worker(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    # Optional: You can mark the old appointment as 'archived' if needed.
    # appointment.status = 'archived'
    # appointment.save()
    
    messages.info(request, "You can now request a new worker.")
    return redirect('worker-list')

# NEW: Worker Dashboard View
@login_required
def worker_dashboard(request):
    """
    Main dashboard view for workers to see their appointments
    """
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get all appointments for this worker with explicit field selection
    # This prevents Django from trying to access non-existent fields like 'uuid'
    appointments = Appointment.objects.filter(worker=worker).select_related(
        'customer', 'service_subtask', 'service_subtask__subtask'
    ).only(
        'id', 'customer', 'worker', 'appointment_date', 'status', 
        'service_subtask', 'location', 'special_instructions',
        'customer_completed', 'worker_completed', 'created_at'
    ).order_by('-appointment_date')
    
    # Separate appointments by status for better organization
    pending_appointments = appointments.filter(status='pending')
    accepted_appointments = appointments.filter(status='accepted')
    completed_appointments = appointments.filter(status='completed')
    rejected_appointments = appointments.filter(status='rejected')
    
    context = {
        'worker': worker,
        'appointments': appointments,
        'pending_appointments': pending_appointments,
        'accepted_appointments': accepted_appointments,
        'completed_appointments': completed_appointments,
        'rejected_appointments': rejected_appointments,
        'today': timezone.now().date(),
    }
    
    return render(request, 'jobs/worker_dashboard.html', context)

# MODIFIED: Worker Appointments View (keep for backward compatibility)
@login_required
def worker_appointments(request, worker_id=None):
    """
    View worker appointments - can be called with worker_id or for current user's worker profile
    """
    if worker_id:
        worker = get_object_or_404(Worker, id=worker_id)
        # Check if the user is authorized to view this worker's appointments
        if worker.owner != request.user:
            messages.error(request, "You are not authorized to view these appointments.")
            return redirect('worker-list')
    else:
        # Get current user's worker profile
        try:
            worker = request.user.worker
        except AttributeError:
            messages.error(request, "You don't have a worker profile.")
            return redirect('worker-list')
    
    appointments = Appointment.objects.filter(worker=worker).order_by('-appointment_date')
    return render(request, 'jobs/worker_appointments.html', {
        'appointments': appointments,
        'worker': worker
    })

@login_required
def accept_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Check if the current user is the owner of the worker
    if appointment.worker.owner != request.user:
        messages.error(request, "You are not authorized to accept this appointment.")
        return redirect('worker_dashboard')

    if request.method == 'POST':
        if appointment.status == 'pending':
            appointment.status = 'accepted'
            appointment.save()
            
            # Send email notification to customer
            try:
                send_appointment_status_email(appointment, 'accepted')
                logger.info(f"Appointment acceptance email sent for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"Failed to send acceptance email for appointment {appointment.id}: {email_error}")
                # Continue without failing - appointment is still accepted
                messages.warning(request, "Appointment accepted but email notification may have failed.")
            
            messages.success(request, "Appointment accepted successfully.")
        else:
            messages.warning(request, "This appointment is not in a pending state.")
    
    return redirect('worker_dashboard')

@login_required
def reject_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Check if the current user is the owner of the worker
    if appointment.worker.owner != request.user:
        messages.error(request, "You are not authorized to reject this appointment.")
        return redirect('worker_dashboard')

    if request.method == 'POST':
        if appointment.status == 'pending':
            appointment.status = 'rejected'
            appointment.save()
            
            # Send email notification to customer
            try:
                send_appointment_status_email(appointment, 'rejected')
                logger.info(f"Appointment rejection email sent for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"Failed to send rejection email for appointment {appointment.id}: {email_error}")
                # Continue without failing
                messages.warning(request, "Appointment rejected but email notification may have failed.")
            
            messages.info(request, "Appointment rejected.")
        else:
            messages.warning(request, "This appointment is not in a pending state.")
    
    return redirect('worker_dashboard')

@login_required
def delete_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    if request.user == appointment.customer.owner or request.user == appointment.worker.owner:
        appointment.delete()
        messages.success(request, "Appointment deleted successfully.")

        if request.user == appointment.customer.owner:
            return redirect('customer_appointments')
        elif request.user == appointment.worker.owner:
            return redirect('worker_dashboard')
    else:
        messages.error(request, "You are not authorized to delete this appointment.")
        
    return redirect('worker_dashboard')

@login_required
def complete_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)

    if appointment.worker.owner != request.user:
        messages.error(request, "You are not allowed to complete this appointment.")
        return redirect('worker_dashboard')

    if request.method == 'POST':
        if appointment.status == 'accepted':
            appointment.status = 'completed'
            appointment.save()
            
            # Send completion email to customer
            try:
                send_appointment_completion_email(appointment)
                logger.info(f"Appointment completion email sent for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"Failed to send completion email for appointment {appointment.id}: {email_error}")
                # Continue without failing
                messages.warning(request, "Appointment completed but email notification may have failed.")
            
            messages.success(request, "Appointment marked as completed.")
        else:
            messages.warning(request, "This appointment cannot be marked as completed (status not accepted).")

    return redirect('worker_dashboard')

@login_required
def rate_worker(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Check if user is authorized to rate this appointment
    if request.user.customer != appointment.customer:
        messages.error(request, "You can only rate workers for your own appointments.")
        return redirect('customer_dashboard')
    
    # Check if appointment is completed
    if appointment.status != 'completed':
        messages.error(request, "You can only rate workers after the appointment is completed.")
        return redirect('customer_dashboard')
    
    # Check if already rated
    existing_rating = WorkerRating.objects.filter(
        worker=appointment.worker,
        appointment=appointment,
        customer=request.user.customer
    ).first()
    
    if request.method == 'POST':
        rating_value = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()
        
        if not rating_value:
            messages.error(request, "Please provide a rating.")
            return redirect('rate_worker', appointment_id=appointment_id)
        
        try:
            rating_value = int(rating_value)
            if not 1 <= rating_value <= 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError:
            messages.error(request, "Invalid rating value.")
            return redirect('rate_worker', appointment_id=appointment_id)
        
        if existing_rating:
            # Update existing rating
            existing_rating.rating = rating_value
            existing_rating.comment = comment
            existing_rating.save()
            messages.success(request, "Your rating has been updated.")
        else:
            # Create new rating
            WorkerRating.objects.create(
                worker=appointment.worker,
                appointment=appointment,
                customer=request.user.customer,
                rating=rating_value,
                comment=comment
            )
            messages.success(request, "Thank you for rating the worker!")
        
        # Update worker's average rating using Bayesian algorithm
        appointment.worker.update_average_rating()
        
        return redirect('customer_dashboard')
    
    # For GET request, show the rating form
    context = {
        'appointment': appointment,
        'existing_rating': existing_rating
    }
    
    return render(request, 'jobs/rate_worker.html', context)

@login_required
def mark_customer_completed(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)

    # Ensure the logged-in user is the customer who booked the appointment
    if not hasattr(request.user, 'customer') or appointment.customer != request.user.customer:
        return HttpResponseForbidden("Only the customer can mark this appointment as completed.")

    # Customer can only mark completed if the worker has accepted the job
    if appointment.status != 'accepted':
        messages.error(request, "You can only mark appointments as completed after they are accepted.")
        return redirect('customer_appointments')

    # Mark as completed by customer
    appointment.customer_completed = True
    appointment.save()

    messages.success(request, "You marked the appointment as completed. Now the worker must confirm.")
    return redirect('customer_appointments')

@login_required
def mark_worker_completed(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)

    # Ensure the logged-in user is the assigned worker
    if not hasattr(request.user, 'worker') or appointment.worker != request.user.worker:
        return HttpResponseForbidden("Only the assigned worker can mark this appointment as completed.")

    # Prevent worker from marking complete before customer
    if not appointment.customer_completed:
        messages.error(request, "The customer must mark the appointment as completed first.")
        return redirect('worker_dashboard')

    # Worker can now confirm completion
    appointment.status = 'completed'
    appointment.worker_completed = True
    appointment.save()
    
    # Send completion email to customer
    try:
        send_appointment_completion_email(appointment)
        logger.info(f"Appointment completion email sent for appointment {appointment.id}")
    except Exception as email_error:
        logger.error(f"Failed to send completion email for appointment {appointment.id}: {email_error}")
        messages.warning(request, "Appointment completed but email notification may have failed.")

    messages.success(request, "You confirmed the appointment as completed.")
    return redirect('worker_dashboard')

# endpoint to update worker location (POST)
@login_required
@require_POST
def update_worker_location(request):
    """
    Accepts POST or JSON body with 'lat' and 'lon' and stores them on the worker profile.
    The view is forgiving about field names (latitude/longitude or worker_latitude/worker_longitude)
    so it should work with your existing model fields used in migrations.
    """
    try:
        # accept form-encoded or JSON
        if request.content_type.startswith("application/json"):
            data = json.loads(request.body.decode() or "{}")
            lat = data.get("lat") or data.get("latitude")
            lon = data.get("lon") or data.get("longitude")
        else:
            lat = request.POST.get("lat") or request.POST.get("latitude")
            lon = request.POST.get("lon") or request.POST.get("longitude")

        if lat is None or lon is None:
            return JsonResponse({"error": "lat and lon required"}, status=400)

        # get related worker object (adjust if your relation name differs)
        worker = getattr(request.user, "worker", None)
        if not worker:
            return JsonResponse({"error": "No worker profile for this user"}, status=403)

        lat_f = float(lat)
        lon_f = float(lon)

        # try common attribute names used across projects/migrations
        for name, val in (("latitude", lat_f), ("longitude", lon_f),
                          ("worker_latitude", lat_f), ("worker_longitude", lon_f)):
            if hasattr(worker, name):
                setattr(worker, name, val)

        worker.save()
        return JsonResponse({"status": "ok", "lat": lat_f, "lon": lon_f})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

# New AJAX views for enhanced functionality
@login_required
def get_worker_availability(request, worker_id):
    """Check worker availability for a given date"""
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        date_str = request.GET.get('date')
        worker = get_object_or_404(Worker, id=worker_id)
        
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Check if worker has appointments on this date
            appointments = Appointment.objects.filter(
                worker=worker,
                appointment_date__date=selected_date,
                status__in=['pending', 'accepted']
            )
            
            # Get available time slots (simplified logic)
            available_slots = []
            for hour in range(9, 18):  # 9 AM to 6 PM
                time_slot = f"{hour:02d}:00"
                # Check if this time slot is available
                slot_occupied = appointments.filter(
                    appointment_date__hour=hour
                ).exists()
                
                if not slot_occupied:
                    available_slots.append(time_slot)
            
            return JsonResponse({
                'available': len(available_slots) > 0,
                'available_slots': available_slots
            })
            
        except ValueError:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def calculate_service_price(request):
    """Calculate service price based on selections"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            data = json.loads(request.body)
            service_id = data.get('service_id')
            is_night_shift = data.get('is_night_shift', False)
            quantity = data.get('quantity', 1)
            
            service_pricing = get_object_or_404(WorkerSubTaskPricing, id=service_id)
            
            # Calculate base price
            base_price = service_pricing.price
            
            # Apply night shift extra if needed
            if is_night_shift and service_pricing.night_shift_extra:
                base_price += service_pricing.night_shift_extra
            
            # Apply quantity multiplier for certain pricing types
            if service_pricing.pricing_type in ['sqft', 'unit', 'shift']:
                total_price = base_price * float(quantity)
            else:
                total_price = base_price
            
            return JsonResponse({
                'price': total_price,
                'price_breakdown': {
                    'base_price': service_pricing.price,
                    'night_shift_extra': service_pricing.night_shift_extra if is_night_shift else 0,
                    'quantity': quantity,
                    'pricing_type': service_pricing.pricing_type
                }
            })
            
        except (ValueError, KeyError) as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def initiate_chat(request, worker_id):
    """Initiate a chat session with a worker"""
    worker = get_object_or_404(Worker, id=worker_id)
    
    # In a real implementation, you would create or get a chat session
    # For now, we'll just return a success response
    return JsonResponse({
        'success': True,
        'message': 'Chat initiated successfully'
    })

@register.filter
def filter_status(queryset, status):
    return queryset.filter(status=status)

@login_required
def customer_dashboard(request):
    """Customer dashboard view with stats, appointments, and ratings"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    # Get appointments
    appointments_list = Appointment.objects.filter(customer=customer).order_by('-appointment_date')
    
    # Add rating status to each appointment
    for appointment in appointments_list:
        appointment.has_rated = WorkerRating.objects.filter(
            appointment=appointment,
            customer=customer
        ).exists()
    
    # Count appointments by status
    pending_appointments = appointments_list.filter(status='pending')
    accepted_appointments = appointments_list.filter(status='accepted')
    completed_appointments = appointments_list.filter(status='completed')
    
    # Get favorite workers count
    favorite_workers_count = FavoriteWorker.objects.filter(customer=customer).count()
    
    # Get recent appointments for display
    recent_appointments = appointments_list[:3]
    
    # Get completed appointments for activity section
    completed_for_activity = completed_appointments[:4]
    
    # Get worker appointment requests
    worker_requests = Appointment.objects.filter(
        customer=customer,
        status='pending'
    ).select_related('worker', 'service_subtask', 'service_subtask__subtask').order_by('-created_at')
    
    # NEW: Ratings and Reviews Data - USING YOUR EXISTING BAYESIAN FUNCTION
    customer_ratings = WorkerRating.objects.filter(customer=customer).select_related(
        'worker', 'appointment', 'appointment__service_subtask__subtask'
    ).order_by('-created_at')
    
    total_reviews = customer_ratings.count()
    
    # Calculate average rating for CUSTOMER'S reviews (simple average since it's the customer's own ratings)
    if total_reviews > 0:
        # For customer's own rating summary, use simple average of their ratings
        ratings_list = [rating.rating for rating in customer_ratings]
        average_rating = sum(ratings_list) / len(ratings_list)
        average_rating_int = int(average_rating)
        
        # Also get Bayesian averages for each worker the customer rated (for display if needed)
        worker_bayesian_ratings = {}
        for rating in customer_ratings:
            worker = rating.worker
            worker_bayesian_ratings[worker.id] = worker.bayesian_average_rating()
    else:
        average_rating = 0.0
        average_rating_int = 0
        worker_bayesian_ratings = {}
    
    # Calculate rating distribution for CUSTOMER'S reviews
    rating_distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    for rating in customer_ratings:
        if 1 <= rating.rating <= 5:
            rating_distribution[rating.rating] += 1
    
    # Convert to percentages for display
    rating_distribution_percent = {}
    if total_reviews > 0:
        for star in [5, 4, 3, 2, 1]:
            rating_distribution_percent[star] = round((rating_distribution[star] / total_reviews) * 100)
    else:
        rating_distribution_percent = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    
    # Get recent reviews (last 5)
    recent_reviews = customer_ratings[:5]
    
    # Get pending reviews (completed appointments without ratings)
    pending_reviews = completed_appointments.filter(
        customer_completed=True,
        worker_completed=True
    ).exclude(
        id__in=WorkerRating.objects.filter(customer=customer).values('appointment_id')
    )[:5]
    
    # Calculate total reviews given (you already have this as total_reviews)
    total_reviews_given = total_reviews
    
    context = {
        'customer': customer,
        'appointments': recent_appointments,
        'pending_appointments': pending_appointments,
        'completed_appointments': completed_appointments,
        'all_appointments': appointments_list,
        'favorite_workers_count': favorite_workers_count,
        'completed_for_activity': completed_for_activity,
        'worker_requests': worker_requests,
        'total_appointments': appointments_list.count(),
        'pending_count': pending_appointments.count(),
        'completed_count': completed_appointments.count(),
        'current_page': 'dashboard',
        # NEW: Ratings context
        'total_reviews': total_reviews_given,  # This goes in your stats grid
        'average_rating': round(average_rating, 1),
        'average_rating_int': average_rating_int,
        'rating_distribution': rating_distribution_percent,
        'recent_reviews': recent_reviews,
        'pending_reviews': pending_reviews,
        'customer_ratings': customer_ratings,  # All ratings given by this customer
    }
    
    return render(request, 'jobs/customer_dashboard.html', context)


def custom_logout(request):
    if request.method == 'POST':
        logout(request)
        return redirect('landing-page')
    # If someone tries to access via GET, just redirect them
    return redirect('landing-page')

@login_required
def appointment_request_details(request, appointment_id):
    """API endpoint to get detailed appointment request information"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    data = {
        'success': True,
        'worker_name': appointment.worker.name,
        'worker_tagline': appointment.worker.tagline,
        'worker_profile_pic': appointment.worker.profile_pic.url if appointment.worker.profile_pic else None,
        'service_name': appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service',
        'appointment_date': appointment.appointment_date.strftime('%B %d, %Y'),
        'appointment_time': appointment.appointment_date.strftime('%I:%M %p'),
        'special_instructions': appointment.special_instructions,
        'duration': '2 hours',  # You might want to calculate this based on service
        'price': f"₹{appointment.service_subtask.price}" if appointment.service_subtask and appointment.service_subtask.price else 'To be discussed',
        'worker_message': 'I would be happy to assist you with this service. Please let me know if the proposed time works for you.'
    }
    
    return JsonResponse(data)

@login_required
def notification_count(request):
    """AJAX view to get notification count"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Example: count pending appointments for customer
        customer = get_object_or_404(Customer, owner=request.user)
        count = Appointment.objects.filter(
            customer=customer, 
            status='pending'
        ).count()
        
        return JsonResponse({'count': count})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# NEW: Add the missing view functions that your template references
@login_required
def customer_reviews(request):
    """View for customers to see their reviews"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    # Get all ratings given by this customer, ordered by creation date (newest first)
    ratings = WorkerRating.objects.filter(customer=customer).select_related(
        'worker', 'appointment'
    ).order_by('-created_at')
    
    context = {
        'ratings': ratings,
        'current_page': 'reviews'
    }
    
    return render(request, 'jobs/customer_reviews.html', context)

@login_required
def customer_profile(request):
    """View for customers to edit their profile"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    if request.method == 'POST':
        # Handle profile updates
        customer.name = request.POST.get('name', customer.name)
        customer.phone_number = request.POST.get('phone_number', customer.phone_number)
        
        # Handle location updates
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        if latitude and longitude:
            try:
                customer.latitude = float(latitude)
                customer.longitude = float(longitude)
            except (ValueError, TypeError):
                pass
        
        # Handle profile picture upload
        if 'profile_pic' in request.FILES:
            customer.profile_pic = request.FILES['profile_pic']
        
        customer.save()
        messages.success(request, "Profile updated successfully!")
        return redirect('customer_profile')
    
    # Count completed appointments
    completed_appointments_count = customer.customer_appointments.filter(status='completed').count()
    
    context = {
        'customer': customer,
        'completed_appointments_count': completed_appointments_count,
        'current_page': 'profile'
    }
    
    return render(request, 'jobs/customer_profile.html', context)

@login_required
def customer_settings(request):
    """View for customer settings"""
    context = {
        'current_page': 'settings'
    }
    return render(request, 'jobs/customer_settings.html', context)

@login_required
def customer_support(request):
    """View for customer support"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    context = {
        'customer': customer,
        'current_page': 'support'
    }
    return render(request, 'jobs/customer_support.html', context)

from django.utils import timezone
from datetime import timedelta
import json

# Add to your views.py

@login_required
def worker_notifications(request):
    """API endpoint to fetch worker notifications"""
    try:
        worker = request.user.worker
    except AttributeError:
        return JsonResponse({'error': 'Worker profile required'}, status=403)
    
    # Get notifications from the last 7 days
    seven_days_ago = timezone.now() - timedelta(days=7)
    
    # Get pending appointments (new requests)
    pending_appointments = Appointment.objects.filter(
        worker=worker, 
        status='pending',
        created_at__gte=seven_days_ago
    ).select_related('customer').order_by('-created_at')
    
    # Get appointments marked as completed by customer
    completed_by_customer = Appointment.objects.filter(
        worker=worker,
        customer_completed=True,
        worker_completed=False,
        updated_at__gte=seven_days_ago
    ).select_related('customer').order_by('-updated_at')
    
    # Format notifications
    notifications = []
    
    for appointment in pending_appointments:
        notifications.append({
            'id': f'appointment-pending-{appointment.id}',
            'type': 'appointment',
            'message': f'New appointment request from {appointment.customer.name}',
            'customer_name': appointment.customer.name,
            'appointment_id': appointment.id,
            'is_read': False,  # You might want to implement a read status system
            'created_at': appointment.created_at.isoformat(),
            'time_ago': get_time_ago(appointment.created_at)
        })
    
    for appointment in completed_by_customer:
        notifications.append({
            'id': f'appointment-completed-{appointment.id}',
            'type': 'completion',
            'message': f'{appointment.customer.name} marked the appointment as completed',
            'customer_name': appointment.customer.name,
            'appointment_id': appointment.id,
            'is_read': False,
            'created_at': appointment.updated_at.isoformat(),
            'time_ago': get_time_ago(appointment.updated_at)
        })
    
    # Count unread notifications (simplified - all are unread in this implementation)
    unread_count = len([n for n in notifications if not n['is_read']])
    
    return JsonResponse({
        'notifications': notifications,
        'unread_count': unread_count
    })

@require_POST
@login_required
def mark_notification_read(request):
    """API endpoint to mark a notification as read"""
    try:
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        # In a real implementation, you would update a Notification model
        # For now, we'll just return success
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@require_POST
@login_required
def mark_all_notifications_read(request):
    """API endpoint to mark all notifications as read"""
    try:
        # In a real implementation, you would update all notifications for this user
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def get_time_ago(dt):
    """Helper function to get a human-readable time ago string"""
    now = timezone.now()
    diff = now - dt
    
    if diff.days > 0:
        return f'{diff.days} day{"s" if diff.days > 1 else ""} ago'
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f'{hours} hour{"s" if hours > 1 else ""} ago'
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
    else:
        return 'Just now'
    

@login_required
def appointment_request(request, worker_id):
    """View to handle appointment request form"""
    worker = get_object_or_404(Worker, id=worker_id)
    
    # Check if user has a customer profile
    try:
        customer = request.user.customer
    except AttributeError:
        messages.error(request, "You need a customer profile to book appointments.")
        return redirect('customer-create')

    if request.method == "POST":
        # Get form data from the booking modal
        service_id = request.POST.get("service_id")
        preferred_date = request.POST.get("preferred_date")
        preferred_time = request.POST.get("preferred_time")
        preferred_shift = request.POST.get("preferred_shift")
        address = request.POST.get("address", "")
        pincode = request.POST.get("pincode", "")
        city = request.POST.get("city", "")
        customer_name = request.POST.get("customer_name", "")
        customer_phone = request.POST.get("customer_phone", "")
        special_instructions = request.POST.get("special_instructions", "")

        # Debug logging
        print(f"POST data received: service_id={service_id}, date={preferred_date}, time={preferred_time}")

        # Validate required fields
        if not all([preferred_date, preferred_time, address, customer_name, customer_phone]):
            messages.error(request, "Please fill in all required fields.")
            return redirect('worker_service_details', worker_id=worker_id)

        try:
            # Parse preferred time slot (e.g., "09:00-11:00")
            if '-' in preferred_time:
                start_time = preferred_time.split('-')[0].strip()
            else:
                start_time = preferred_time.strip()
            
            # Create appointment datetime
            datetime_str = f"{preferred_date} {start_time}"
            appointment_datetime = make_aware(datetime.strptime(datetime_str, "%Y-%m-%d %H:%M"))
            
            # Check if appointment is in the future
            if appointment_datetime <= now():
                messages.error(request, "You can only book appointments for future dates/times.")
                return redirect('worker_service_details', worker_id=worker_id)

            # Check for conflicting appointments
            conflicting_appointments = Appointment.objects.filter(
                worker=worker,
                appointment_date__date=appointment_datetime.date(),
                appointment_date__hour__range=(
                    appointment_datetime.hour, 
                    appointment_datetime.hour + 2
                ),
                status__in=['pending', 'accepted']
            )
            
            if conflicting_appointments.exists():
                messages.error(request, "Worker already has an appointment during this time slot.")
                return redirect('worker_service_details', worker_id=worker_id)

            # Get service subtask pricing if service_id is provided
            service_subtask = None
            if service_id and service_id != 'default' and service_id != '':
                try:
                    service_subtask = WorkerSubTaskPricing.objects.get(id=service_id)
                    print(f"Found service subtask: {service_subtask}")
                except WorkerSubTaskPricing.DoesNotExist:
                    print(f"Service subtask not found for ID: {service_id}")
                    pass

            # Build complete location string
            complete_location = f"{address}, {city}"
            if pincode:
                complete_location += f" - {pincode}"

            # Create appointment
            appointment = Appointment.objects.create(
                customer=customer,
                worker=worker,
                appointment_date=appointment_datetime,
                status="pending",
                service_subtask=service_subtask,
                shift_type=preferred_shift if preferred_shift else 'day',
                location=complete_location,
                special_instructions=special_instructions
            )

            print(f"Appointment created: ID={appointment.id}")

            # Send email notification to worker (with error handling)
            try:
                send_appointment_request_email(worker, appointment)
                logger.info(f"Appointment request email sent successfully for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"Email sending failed for appointment {appointment.id}: {email_error}")
                # Don't show warning to user - appointment is still created successfully
                # messages.warning(request, "Appointment created but email notification may have failed.")
            
            messages.success(request, f"Appointment request sent successfully to {worker.name}! They will be notified shortly.")
            return redirect('customer_appointments')

        except ValueError as e:
            logger.error(f"Error parsing datetime: {e}")
            messages.error(request, f"Invalid appointment date or time format: {str(e)}")
            return redirect('worker_service_details', worker_id=worker_id)
        except Exception as e:
            logger.error(f"Unexpected error in appointment_request: {e}")
            import traceback
            traceback.print_exc()
            messages.error(request, f"An error occurred: {str(e)}. Please try again.")
            return redirect('worker_service_details', worker_id=worker_id)
    
    # GET request - redirect to worker service details
    return redirect('worker_service_details', worker_id=worker_id)

@login_required
def worker_service_details(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    
    try:
        # Get worker services with pricing from database
        worker_services = WorkerService.objects.filter(
            worker=worker, 
            is_available=True
        ).select_related('service', 'service__category').prefetch_related(
            'pricing__subtask'
        )
        
        # Organize services by category
        categories_dict = {}
        
        for worker_service in worker_services:
            category = worker_service.service.category
            service = worker_service.service
            
            # Create category entry if it doesn't exist
            if category.id not in categories_dict:
                categories_dict[category.id] = {
                    'id': category.id,
                    'name': category.name,
                    'description': category.description or '',
                    'icon': get_category_icon(category.name),
                    'services': []
                }
            
            # Get pricing for each subtask of this service
            pricing_entries = WorkerSubTaskPricing.objects.filter(
                worker_service=worker_service
            ).select_related('subtask')
            
            for pricing in pricing_entries:
                subtask = pricing.subtask
                
                # ✅ FIXED: Handle missing or None values safely
                try:
                    base_price = float(pricing.price) if pricing.price else 0.0
                    night_shift_extra = float(pricing.night_shift_extra) if pricing.night_shift_extra else 0.0
                    min_hours = pricing.min_hours if pricing.min_hours else 1
                except (ValueError, TypeError):
                    base_price = 0.0
                    night_shift_extra = 0.0
                    min_hours = 1
                
                # Build pricing display
                pricing_display = f"₹{base_price:.2f}"
                if pricing.pricing_type == 'hourly':
                    pricing_display += f"/hour"
                    if min_hours > 1:
                        pricing_display += f" (min {min_hours} hrs)"
                elif pricing.pricing_type == 'sqft':
                    pricing_display += "/sq.ft"
                elif pricing.pricing_type == 'unit':
                    pricing_display += "/unit"
                elif pricing.pricing_type == 'shift':
                    pricing_display += "/shift"
                elif pricing.pricing_type == 'inspection':
                    pricing_display = "Contact for pricing"
                
                # Build features list
                features = []
                if pricing.experience_level:
                    features.append(f"{pricing.get_experience_level_display()} expertise")
                else:
                    features.append("Professional service")
                    
                features.append("Quality work guaranteed")
                
                if getattr(subtask, 'materials_included', False):
                    features.append("Materials included in price")
                else:
                    features.append("Materials not included")
                    
                if night_shift_extra > 0:
                    features.append(f"Night shift available (+₹{night_shift_extra:.2f})")
                    
                features.append("Customer support included")
                
                # ✅ FIXED: Convert all values to JSON-serializable types
                service_data = {
                    'id': str(pricing.id),  # Convert to string for safety
                    'name': str(getattr(subtask, 'name', 'Service')),
                    'description': str(getattr(subtask, 'description', 'Professional service')),
                    'detailed_description': str(getattr(subtask, 'detailed_description', '')),
                    'price_display': str(pricing_display),
                    'base_price': float(base_price),
                    'pricing_type': str(pricing.pricing_type),
                    'pricing_type_display': str(pricing.get_pricing_type_display()),
                    'duration': str(getattr(subtask, 'duration', 'Duration varies based on project scope')),
                    'features': [str(feature) for feature in features],
                    'requirements': str(getattr(subtask, 'requirements', 'Standard requirements apply')),
                    'materials_included': bool(getattr(subtask, 'materials_included', False)),
                    'night_shift_extra': float(night_shift_extra),
                    'min_hours': int(min_hours),
                    'experience_level_display': str(pricing.get_experience_level_display() if pricing.experience_level else 'Standard'),
                    'special_offer': bool(getattr(subtask, 'special_offer', False)),
                    'offer_price': float(subtask.offer_price) if getattr(subtask, 'offer_price', None) else None,
                    'original_price': float(subtask.original_price) if getattr(subtask, 'original_price', None) else None,
                    'image': str(service.image.url) if service.image else None,
                }
                
                categories_dict[category.id]['services'].append(service_data)
        
        # Convert dict to list and sort categories by name
        categories_data = sorted(list(categories_dict.values()), key=lambda x: x['name'])
        
        # ✅ NEW: Convert categories_data to JSON-serializable format
        for category in categories_data:
            category['id'] = str(category['id'])  # Ensure ID is string
            for service in category['services']:
                # Ensure all service values are JSON serializable
                service['id'] = str(service['id'])
                service['base_price'] = float(service['base_price'])
                service['night_shift_extra'] = float(service['night_shift_extra'])
                service['min_hours'] = int(service['min_hours'])
                if service['offer_price'] is not None:
                    service['offer_price'] = float(service['offer_price'])
                if service['original_price'] is not None:
                    service['original_price'] = float(service['original_price'])
        
    except Exception as e:
        logger.error(f"Error in worker_service_details for worker {worker_id}: {str(e)}")
        categories_data = []
        messages.error(request, "Error loading service details. Please try again.")
    
    # If no services found, create a default consultation category
    if not categories_data:
        categories_data = [{
            'id': 'consultation',
            'name': 'Professional Consultation',
            'description': f'Contact {worker.name} for custom services and quotes',
            'icon': '💬',
            'services': [{
                'id': 'consultation',
                'name': f'Consultation with {worker.name}',
                'description': worker.bio or 'Professional consultation and service assessment',
                'detailed_description': 'Get expert advice and custom quotes for your project',
                'price_display': 'Contact for pricing',
                'base_price': 0.0,
                'pricing_type': 'consultation',
                'pricing_type_display': 'Custom Quote',
                'duration': '1 hour minimum',
                'features': [
                    'Professional assessment', 
                    'Customized solution',
                    'Expert advice',
                    'Free initial consultation'
                ],
                'requirements': 'Please describe your specific requirements',
                'materials_included': False,
                'night_shift_extra': 0.0,
                'min_hours': 1,
                'experience_level_display': 'Expert',
                'special_offer': False,
                'offer_price': None,
                'original_price': None,
                'image': str(worker.profile_pic.url) if worker.profile_pic else None,
            }]
        }]
    
    # ✅ NEW: Convert to JSON string for safe template rendering
     # Convert to JSON string for safe template rendering
    import json
    from datetime import date  
    categories_data_json = json.dumps(categories_data, ensure_ascii=False)
    
    # ✅ THEN UPDATE YOUR CONTEXT DICTIONARY
    context = {
        'worker': worker,
        'categories_data': categories_data,
        'categories_data_json': categories_data_json,  # ✅ NEW: JSON version
        'worker_name': worker.name,
        'worker_tagline': worker.tagline,
        'worker_bio': worker.bio or 'Professional service provider',
        'worker_phone': str(worker.phone_number),
        'worker_profile_pic': worker.profile_pic.url if worker.profile_pic else None,
        'worker_verified': worker.verified,
        'today': date.today().isoformat(),
    }
    
    return render(request, 'jobs/worker_service_details.html', context)

def get_category_icon(category_name):
    """Helper function to get appropriate icon based on category name"""
    category_icons = {
        'plumber': '🔧',
        'plumbing': '🔧',
        'electrician': '⚡',
        'electrical': '⚡',
        'painter': '🎨',
        'painting': '🎨',
        'cleaning': '🧹',
        'cleaner': '🧹',
        'carpenter': '🔨',
        'carpentry': '🔨',
        'construction': '🏗️',
        'repair': '🔧',
        'maintenance': '⚙️',
        'installation': '🔧',
        'design': '📐',
    }
    
    category_lower = category_name.lower()
    for key, icon in category_icons.items():
        if key in category_lower:
            return icon
    
    return '🔧'  # Default icon

@login_required
def toggle_favorite_worker(request, worker_id):
    """Toggle favorite status for a worker"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            worker = get_object_or_404(Worker, id=worker_id)
            customer = request.user.customer
            
            # Check if already favorited
            favorite_exists = FavoriteWorker.objects.filter(
                customer=customer, 
                worker=worker
            ).exists()
            
            if favorite_exists:
                # Remove from favorites
                FavoriteWorker.objects.filter(customer=customer, worker=worker).delete()
                is_favorite = False
                message = "Worker removed from favorites"
            else:
                # Add to favorites
                FavoriteWorker.objects.create(customer=customer, worker=worker)
                is_favorite = True
                message = "Worker added to favorites"
            
            return JsonResponse({
                'success': True,
                'is_favorite': is_favorite,
                'message': message
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def favorite_workers_list(request):
    """View to display customer's favorite workers"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    # Get favorite workers with distance calculation
    favorite_workers = FavoriteWorker.objects.filter(
        customer=customer
    ).select_related('worker').order_by('-created_at')
    
    # Calculate distance for each favorite worker
    workers_with_distance = []
    cust_lat = None
    cust_lon = None
    
    if customer.latitude and customer.longitude:
        try:
            cust_lat = float(customer.latitude)
            cust_lon = float(customer.longitude)
        except (ValueError, TypeError):
            cust_lat = None
            cust_lon = None
    
    for favorite in favorite_workers:
        worker = favorite.worker
        distance_km = None
        
        # Calculate distance if customer has coordinates and worker has coordinates
        if cust_lat is not None and cust_lon is not None and worker.latitude and worker.longitude:
            try:
                worker_lat = float(worker.latitude)
                worker_lon = float(worker.longitude)
                distance_km = _haversine_km(worker_lat, worker_lon, cust_lat, cust_lon)
                if distance_km != float('inf'):
                    distance_km = round(distance_km, 2)
            except (ValueError, TypeError):
                distance_km = None
        
        # Add rating information
        average_rating = worker.bayesian_average_rating()
        worker.average_rating = average_rating
        worker.total_ratings = worker.ratings.count()
        
        # Star breakdown for display
        full_stars = int(average_rating)
        half_star = 1 if average_rating % 1 >= 0.5 else 0
        empty_stars = 5 - (full_stars + half_star)
        
        worker.full_stars = range(full_stars)
        worker.half_star = half_star
        worker.empty_stars = range(empty_stars)
        worker.distance_km = distance_km
        
        workers_with_distance.append({
            'worker': worker,
            'favorited_at': favorite.created_at,
            'distance_km': distance_km
        })
    
    context = {
        'favorite_workers': workers_with_distance,
        'current_page': 'favorites'
    }
    
    return render(request, 'jobs/favorite_workers.html', context)

@login_required
def check_favorite_status(request, worker_id):

    """Check if a worker is favorited by the current customer"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            worker = get_object_or_404(Worker, id=worker_id)
            customer = request.user.customer
            
            is_favorite = FavoriteWorker.objects.filter(
                customer=customer, 
                worker=worker
            ).exists()
            
            return JsonResponse({
                'is_favorite': is_favorite
            })
            
        except Exception as e:
            return JsonResponse({
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)



@login_required
def worker_calendar(request):
    """Worker calendar view"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get appointments for calendar
    appointments = Appointment.objects.filter(worker=worker).select_related(
        'customer', 'service_subtask', 'service_subtask__subtask'
    ).order_by('appointment_date')
    
    # Format appointments for calendar
    calendar_events = []
    for appointment in appointments:
        calendar_events.append({
            'id': appointment.id,
            'title': f"{appointment.customer.name} - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}",
            'start': appointment.appointment_date.isoformat(),
            'end': (appointment.appointment_date + timedelta(hours=2)).isoformat(),
            'status': appointment.status,
            'customer_name': appointment.customer.name,
            'service_name': appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service',
            'location': appointment.location,
        })
    
    context = {
        'worker': worker,
        'calendar_events': json.dumps(calendar_events),
        'current_section': 'calendar'
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'calendar_events': calendar_events})
    
    return render(request, 'jobs/worker_calendar.html', context)

@login_required
def worker_reviews(request):
    """Worker reviews view"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get ratings for this worker
    ratings = WorkerRating.objects.filter(worker=worker).select_related(
        'customer', 'appointment'
    ).order_by('-created_at')
    
    # Calculate rating statistics
    total_ratings = ratings.count()
    average_rating = worker.bayesian_average_rating()
    
    # Rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        rating_distribution[i] = ratings.filter(rating=i).count()
    
    context = {
        'worker': worker,
        'ratings': ratings,
        'total_ratings': total_ratings,
        'average_rating': average_rating,
        'rating_distribution': rating_distribution,
        'current_section': 'reviews'
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        ratings_data = []
        for rating in ratings:
            ratings_data.append({
                'id': rating.id,
                'customer_name': rating.customer.name,
                'rating': rating.rating,
                'comment': rating.comment,
                'created_at': rating.created_at.isoformat(),
                'appointment_date': rating.appointment.appointment_date if rating.appointment else None,
            })
        return JsonResponse({
            'ratings': ratings_data,
            'average_rating': average_rating,
            'total_ratings': total_ratings
        })
    
    return render(request, 'jobs/worker_reviews.html', context)

@login_required
def worker_analytics(request):
    """Worker analytics view"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Calculate analytics data
    total_appointments = Appointment.objects.filter(worker=worker).count()
    completed_appointments = Appointment.objects.filter(worker=worker, status='completed').count()
    pending_appointments = Appointment.objects.filter(worker=worker, status='pending').count()
    accepted_appointments = Appointment.objects.filter(worker=worker, status='accepted').count()
    
    # Monthly earnings (example calculation)
    monthly_earnings = []
    for i in range(6):  # Last 6 months
        month = timezone.now() - timedelta(days=30*i)
        monthly_appointments = Appointment.objects.filter(
            worker=worker,
            status='completed',
            appointment_date__month=month.month,
            appointment_date__year=month.year
        )
        monthly_income = sum(
            appointment.service_subtask.price 
            for appointment in monthly_appointments 
            if appointment.service_subtask
        )
        monthly_earnings.append({
            'month': month.strftime('%b %Y'),
            'income': monthly_income
        })
    
    # Service popularity
    service_stats = []
    worker_services = WorkerService.objects.filter(worker=worker)
    for service in worker_services:
        service_appointments = Appointment.objects.filter(
            worker=worker,
            service_subtask__worker_service=service
        ).count()
        service_stats.append({
            'service_name': service.service.name,
            'appointment_count': service_appointments
        })
    
    context = {
        'worker': worker,
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'pending_appointments': pending_appointments,
        'accepted_appointments': accepted_appointments,
        'monthly_earnings': monthly_earnings,
        'service_stats': service_stats,
        'current_section': 'analytics'
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'total_appointments': total_appointments,
            'completed_appointments': completed_appointments,
            'completion_rate': (completed_appointments / total_appointments * 100) if total_appointments > 0 else 0,
            'monthly_earnings': monthly_earnings,
            'service_stats': service_stats
        })
    
    return render(request, 'jobs/worker_analytics.html', context)

@login_required
def worker_earnings(request):
    """Worker earnings view"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get completed appointments with pricing
    completed_appointments = Appointment.objects.filter(
        worker=worker,
        status='completed'
    ).select_related('service_subtask').order_by('-appointment_date')
    
    # Calculate total earnings
    total_earnings = sum(
        appointment.service_subtask.price 
        for appointment in completed_appointments 
        if appointment.service_subtask
    )
    
    # Earnings by month
    monthly_earnings = {}
    for appointment in completed_appointments:
        if appointment.service_subtask:
            month_year = appointment.appointment_date.strftime('%Y-%m')
            if month_year not in monthly_earnings:
                monthly_earnings[month_year] = 0
            monthly_earnings[month_year] += appointment.service_subtask.price
    
    # Recent transactions
    recent_transactions = []
    for appointment in completed_appointments[:10]:  # Last 10 transactions
        if appointment.service_subtask:
            recent_transactions.append({
                'date': appointment.appointment_date,
                'customer': appointment.customer.name,
                'service': appointment.service_subtask.subtask.name,
                'amount': appointment.service_subtask.price,
                'status': 'completed'
            })
    
    context = {
        'worker': worker,
        'total_earnings': total_earnings,
        'monthly_earnings': monthly_earnings,
        'recent_transactions': recent_transactions,
        'completed_appointments': completed_appointments,
        'current_section': 'earnings'
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'total_earnings': total_earnings,
            'monthly_earnings': monthly_earnings,
            'recent_transactions': recent_transactions
        })
    
    return render(request, 'jobs/worker_earnings.html', context)

@login_required
def worker_settings(request):
    """Worker settings view"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    if request.method == 'POST':
        # Handle profile updates
        worker.name = request.POST.get('name', worker.name)
        worker.tagline = request.POST.get('tagline', worker.tagline)
        worker.bio = request.POST.get('bio', worker.bio)
        worker.phone_number = request.POST.get('phone_number', worker.phone_number)
        worker.shift = request.POST.get('shift', worker.shift)
        
        # Handle profile picture upload
        if 'profile_pic' in request.FILES:
            worker.profile_pic = request.FILES['profile_pic']
        
        # Handle location updates
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        if latitude and longitude:
            try:
                worker.latitude = float(latitude)
                worker.longitude = float(longitude)
            except (ValueError, TypeError):
                pass
        
        worker.save()
        messages.success(request, "Profile updated successfully!")
        return redirect('worker_settings')
    
    context = {
        'worker': worker,
        'current_section': 'settings'
    }
    
    return render(request, 'jobs/worker_settings.html', context)


@login_required
@require_POST
def delete_worker_review(request):
    """Delete a worker review"""
    try:
        review_id = request.POST.get('review_id')
        review = get_object_or_404(WorkerRating, id=review_id)
        
        # Check if the current user owns this worker's reviews
        if review.worker.owner != request.user:
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Delete the review
        review.delete()
        
        # Update worker's average rating
        review.worker.update_average_rating()
        
        return JsonResponse({'success': True, 'message': 'Review deleted successfully'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})