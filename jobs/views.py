from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from jobs.models import Worker, Customer, Appointment, WorkerRating, Service, WorkerService, WorkerSubTaskPricing, ServiceCategory, SubTask,  User 
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
from jobs.models import Notification
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import threading
import requests 
from django.core.cache import cache
from django.views.decorators.cache import cache_page
import hashlib
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from admin_dashboard.models import AdminActivityLog
from django.db.models import Q 
from django.views.decorators.http import require_http_methods 
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

def get_client_ip(request):
    """Get client IP address for geolocation fallback with cache consideration"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    # Log cache status
    cached_ip_location = get_cached_ip_location(ip)
    if cached_ip_location:
        logger.debug(f"IP {ip} has cached location data")
    
    return ip

def admin_required(user):
    """Check if user is staff/admin"""
    return user.is_authenticated and user.is_staff


# MODIFIED: Enhanced update_user_location_with_coords with caching
def update_user_location_with_coords(user, latitude, longitude, accuracy=None, source='browser'):
    """
    Update user location with coordinates - REPLACES old location with caching
    """
    try:
        # Cache the location first
        if user.is_authenticated:
            cache_user_location(user.id, latitude, longitude, accuracy, source)
        
        # Then update the database
        if hasattr(user, 'worker'):
            worker = user.worker
            worker.latitude = latitude
            worker.longitude = longitude
            worker.location_accuracy = accuracy
            worker.location_source = source
            worker.location_updated_at = timezone.now()
            worker.save(update_fields=['latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'])
            logger.info(f"Updated worker {worker.name} location to ({latitude}, {longitude}) from {source}")
        
        elif hasattr(user, 'customer'):
            customer = user.customer
            customer.latitude = latitude
            customer.longitude = longitude
            customer.location_accuracy = accuracy
            customer.location_source = source
            customer.location_updated_at = timezone.now()
            customer.save(update_fields=['latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'])
            logger.info(f"Updated customer {customer.name} location to ({latitude}, {longitude}) from {source}")
            
    except Exception as e:
        logger.error(f"Error updating location with coordinates: {e}")

# MODIFIED: Enhanced update_user_location_with_ip with caching
def update_user_location_with_ip(user, ip_address):
    """
    Update user location using IP geolocation (fallback) - REPLACES old location with caching
    """
    try:
        # Check cache first
        cached_location = get_cached_ip_location(ip_address)
        if cached_location:
            logger.info(f"Using cached IP location for {ip_address}")
            update_user_location_with_coords(
                user, 
                cached_location['latitude'], 
                cached_location['longitude'], 
                cached_location['accuracy'], 
                'ip_cached'
            )
            return

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
                
                # Cache the IP location
                cache_ip_location(ip_address, latitude, longitude)
                
                # Update user location
                update_user_location_with_coords(
                    user, latitude, longitude, 5000, 'ip'
                )
                
                logger.info(f"Updated {user.username} location via IP to ({latitude}, {longitude}) and cached it")
                
    except Exception as e:
        logger.error(f"Error updating location via IP: {e}")

def index(request):
    return HttpResponse("<h1>BlueCaller</h1>")

@csrf_exempt
def store_landing_location(request):
    """
    Store location captured on landing page in session and cache for later use
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
            
            # Also cache for anonymous users
            if not request.user.is_authenticated:
                ip_address = get_client_ip(request)
                cache_ip_location(ip_address, latitude, longitude, accuracy)
            
            logger.info(f"Landing location stored in session and cache: ({latitude}, {longitude})")
            
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

def send_email_async(subject, plain_message, from_email, recipients, html_message=None):
    """Send email in a separate thread to avoid blocking"""
    def send_email():
        try:
            if html_message:
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_message,
                    from_email=from_email,
                    to=recipients
                )
                email.attach_alternative(html_message, "text/html")
                email.send()
            else:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=from_email,
                    recipient_list=recipients,
                    html_message=html_message,
                    fail_silently=False
                )
            logger.info(f"Email sent successfully to {recipients}")
        except Exception as e:
            logger.error(f"Failed to send email to {recipients}: {str(e)}")
    
    # Start email sending in background thread
    thread = threading.Thread(target=send_email)
    thread.daemon = True
    thread.start()
# Enhanced email functions with better formatting and error handling
def send_appointment_request_email(worker, appointment):
    """Send email notification to worker when customer requests an appointment"""
    try:
        subject = f"New Appointment Request - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}"
        
        # Get price information safely
        price_info = "Contact for pricing"
        if appointment.service_subtask and appointment.service_subtask.price:
            price_info = f"₹{appointment.service_subtask.price}"
        
        # Use template rendering instead of hardcoded HTML
        context = {
            'worker_name': worker.name,
            'customer_name': appointment.customer.name,
            'service_name': appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service',
            'price_info': price_info,
            'appointment_date': appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p'),
            'location': appointment.location or 'Not specified',
            'special_instructions': appointment.special_instructions or '',
            'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            'appointment_id': appointment.id
        }
        
        # Render HTML template
        html_message = render_to_string('emails/appointment_request_to_worker.html', context)
        plain_message = strip_tags(html_message)
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [worker.owner.email]
        
        # Send email asynchronously
        send_email_async(subject, plain_message, from_email, recipients, html_message)
        
        logger.info(f"Appointment request email sent to worker {worker.name} ({worker.owner.email})")
        
    except Exception as e:
        logger.error(f"Failed to send appointment request email to worker {worker.name}: {str(e)}")
        # Don't raise the exception to prevent appointment creation from failing

def send_appointment_status_email(appointment, status):
    """Send email notification to customer when appointment status changes - FIXED VERSION"""
    try:
        customer = appointment.customer
        worker = appointment.worker
        
        # Get price information safely
        price_info = "Contact for pricing"
        if appointment.service_subtask and appointment.service_subtask.price:
            price_info = f"₹{appointment.service_subtask.price}"
        
        # Service name safely
        service_name = "Service"
        if appointment.service_subtask and appointment.service_subtask.subtask:
            service_name = appointment.service_subtask.subtask.name
        
        # Date safely
        appointment_date_str = "Not specified"
        if appointment.appointment_date:
            appointment_date_str = appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p')
        
        context = {
            'customer_name': customer.name,
            'worker_name': worker.name,
            'status': status,
            'service_name': service_name,
            'price_info': price_info,
            'appointment_date': appointment_date_str,
            'location': appointment.location or 'Not specified',
            'special_instructions': appointment.special_instructions or '',
            'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            'appointment_id': appointment.id
        }
        
        if status == 'accepted':
            subject = f"Appointment Confirmed - {worker.name}"
            
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c3e50;">Appointment Confirmed! 🎉</h2>
                    
                    <div style="background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin: 0;">Your appointment has been confirmed</h3>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #007bff; margin-top: 0;">Appointment Details</h3>
                        <p><strong>Worker:</strong> {worker.name}</p>
                        <p><strong>Service:</strong> {service_name}</p>
                        <p><strong>Date & Time:</strong> {appointment_date_str}</p>
                        <p><strong>Location:</strong> {appointment.location or 'Not specified'}</p>
                        <p><strong>Estimated Price:</strong> {price_info}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/customer/appointments/" 
                           style="background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Appointment
                        </a>
                    </div>
                </div>
            </body>
            </html>
            """
            
        else:  # rejected
            subject = f"Appointment Declined - {worker.name}"
            
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c3e50;">Appointment Declined</h2>
                    
                    <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin: 0;">Your appointment request was declined</h3>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <p><strong>Worker:</strong> {worker.name}</p>
                        <p><strong>Service:</strong> {service_name}</p>
                        <p><strong>Reason:</strong> The worker was unable to accept your appointment at this time.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/workers/" 
                           style="background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Find Another Worker
                        </a>
                    </div>
                </div>
            </body>
            </html>
            """
        
        # Create plain text version
        plain_message = strip_tags(html_message)
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [customer.owner.email]
        
        # Send email asynchronously
        send_email_async(subject, plain_message, from_email, recipients, html_message)
        
        logger.info(f"Appointment status email ({status}) sent to customer {customer.name}")
        
    except Exception as e:
        logger.error(f"❌ FAILED to send appointment status email to customer {customer.name}: {str(e)}")
        # Re-raise the exception to see the actual error
        raise


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
def get_recommended_workers(request, limit=8):
    """
    Get recommended workers using Bayesian algorithm - FIXED VERSION
    """
    try:
        # Get all available, verified workers
        workers = Worker.objects.filter(
            is_available=True,
            verified=True
        ).select_related('owner').prefetch_related('ratings')
        
        # Calculate Bayesian rating for each worker
        workers_with_ratings = []
        for worker in workers:
            bayesian_rating = worker.bayesian_average_rating()
            rating_count = worker.ratings.count()
            
            # Add all workers to the list, not just those with ratings
            workers_with_ratings.append((worker, bayesian_rating, rating_count))
        
        # ✅ FIXED: Sort by Bayesian rating (highest first), then by number of ratings
        # Workers with no ratings will have bayesian_rating = 2.5 (default)
        workers_with_ratings.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        # Prepare the top workers for template
        recommended_workers = []
        for worker, bayesian_rating, rating_count in workers_with_ratings[:limit]:
            worker.average_rating = bayesian_rating
            worker.total_ratings = rating_count
            worker.has_ratings = rating_count > 0
            
            # Add star breakdown
            if rating_count > 0:
                full_stars = int(bayesian_rating)
                half_star = 1 if bayesian_rating % 1 >= 0.5 else 0
                empty_stars = 5 - (full_stars + half_star)
            else:
                full_stars = 0
                half_star = 0
                empty_stars = 5
            
            worker.full_stars = range(full_stars)
            worker.half_star = half_star
            worker.empty_stars = range(empty_stars)
            
            recommended_workers.append(worker)
        
        return recommended_workers
        
    except Exception as e:
        logger.error(f"Error in get_recommended_workers: {e}")
        # Fallback: return any available verified workers
        fallback_workers = Worker.objects.filter(
            is_available=True,
            verified=True
        )[:limit]
        
        for worker in fallback_workers:
            worker.average_rating = 0
            worker.total_ratings = 0
            worker.has_ratings = False
            worker.full_stars = range(0)
            worker.half_star = 0
            worker.empty_stars = range(5)
            
        return fallback_workers


def calculate_recommendation_score(worker, bayesian_rating):
    """
    Calculate a recommendation score from 0-1 based on multiple factors
    """
    try:
        score = 0.0
        
        # 1. Bayesian Rating Weight (40%)
        rating_weight = (bayesian_rating / 5.0) * 0.4
        
        # 2. Rating Count Weight (30%)
        rating_count = worker.ratings.count()
        count_weight = min(rating_count / 20.0, 1.0) * 0.3  # Cap at 20 ratings
        
        # 3. Verification Bonus (15%)
        verification_bonus = 0.15 if worker.verified else 0.0
        
        # 4. Response Rate (15%) - You'll need to track this
        response_bonus = 0.15  # Placeholder
        
        score = rating_weight + count_weight + verification_bonus + response_bonus
        
        return min(score, 1.0)  # Cap at 1.0
        
    except Exception as e:
        logger.error(f"Error calculating recommendation score: {e}")
        return 0.0
    
    
class WorkerListView(ListView):
    model = Worker
    template_name = 'jobs/worker_list.html'
    context_object_name = 'workers'
    paginate_by = 12

    def get_queryset(self):
        query = self.request.GET.get('q')
        filter_param = self.request.GET.get('filter')
        service_filter = self.request.GET.get('service')
        max_distance = self.request.GET.get('max_distance')

        # ✅ FIXED: Only show verified and available workers
        queryset = Worker.objects.filter(
            is_available=True,
            verified=True,
            verification_status='approved'
        ).select_related('owner').prefetch_related('ratings')

        if query:
            queryset = queryset.filter(
                Q(tagline__icontains=query) | 
                Q(name__icontains=query) |
                Q(bio__icontains=query)
            )
            
        if service_filter:
            queryset = queryset.filter(services__service__id=service_filter)

        # ✅ FIX: Get customer location with session consistency
        customer_location = None
        if hasattr(self.request.user, 'customer'):
            customer = self.request.user.customer
            
            # Use cached session location for consistency across page refreshes
            session_lat = self.request.session.get('current_latitude')
            session_lon = self.request.session.get('current_longitude')
            
            if session_lat and session_lon:
                # Use session location (doesn't change during browsing session)
                customer_location = {
                    'latitude': float(session_lat),
                    'longitude': float(session_lon),
                    'source': 'session'
                }
            else:
                # Fallback to database location only if no session location
                customer_location = customer.get_current_location()
                
                # Cache it in session for future requests
                if customer_location:
                    self.request.session['current_latitude'] = customer_location['latitude']
                    self.request.session['current_longitude'] = customer_location['longitude']

        # ✅ FIXED: Calculate ratings and add to each worker WITH DISTANCE SORTING
        workers_with_ratings_and_distance = []
        for worker in queryset:
            # Calculate Bayesian rating
            bayesian_rating = worker.bayesian_average_rating()
            rating_count = worker.ratings.count()
            has_ratings = rating_count > 0
            
            # Add rating properties to worker object
            worker.average_rating = bayesian_rating
            worker.total_ratings = rating_count
            worker.has_ratings = has_ratings
            
            # Calculate star breakdown
            if has_ratings:
                full_stars = int(bayesian_rating)
                half_star = 1 if bayesian_rating % 1 >= 0.5 else 0
                empty_stars = 5 - (full_stars + half_star)
            else:
                full_stars = 0
                half_star = 0
                empty_stars = 5
            
            worker.full_stars = range(full_stars)
            worker.half_star = half_star
            worker.empty_stars = range(empty_stars)
            
            # ✅ FIX: Calculate distance with consistent rounding
            distance_km = float('inf')  # Default to infinity if no location
            if customer_location and worker.latitude and worker.longitude:
                try:
                    distance_km = _haversine_km(
                        float(worker.latitude), float(worker.longitude),
                        float(customer_location['latitude']), float(customer_location['longitude'])
                    )
                    # ✅ Round to 1 decimal for consistency
                    distance_km = round(distance_km, 1)
                except (ValueError, TypeError):
                    distance_km = float('inf')
            
            worker.distance_km = distance_km
            
            # Add worker and distance to list for sorting
            workers_with_ratings_and_distance.append((worker, distance_km))

        # ✅ CRITICAL FIX: Sort workers by distance (closest first)
        # Workers with no distance (infinity) will be at the end
        workers_with_ratings_and_distance.sort(key=lambda x: x[1])
        
        # ✅ FIX: Extract just the worker objects in sorted order AND maintain distance property
        sorted_workers = []
        for worker, distance in workers_with_ratings_and_distance:
            worker.distance_km = distance  # Ensure distance is preserved
            sorted_workers.append(worker)
        
        return sorted_workers

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # ✅ FIXED: Add recommended workers (highest rated)
        recommended_workers = get_recommended_workers(self.request, limit=8)
        context['recommended_workers'] = recommended_workers
        
        # Add search query
        context['q'] = self.request.GET.get('q', '')
        context['max_distance'] = self.request.GET.get('max_distance', 50)
        
        # ✅ FIX: Add customer location info with session indicator
        if hasattr(self.request.user, 'customer'):
            customer = self.request.user.customer
            session_lat = self.request.session.get('current_latitude')
            session_lon = self.request.session.get('current_longitude')
            
            if session_lat and session_lon:
                customer_location = {
                    'latitude': float(session_lat),
                    'longitude': float(session_lon),
                    'source': 'session'
                }
            else:
                customer_location = customer.get_current_location()
            
            context['customer_location'] = customer_location
        
        return context

def get_dynamic_time_slots(worker_shift):
    """
    Generate dynamic time slots based on worker's shift preference
    Returns list of time slots in format: {'value': '14:00-16:00', 'display': '2:00 PM - 4:00 PM'}
    """
    def format_time_display(hour):
        """Helper function to format hour to 12-hour format with AM/PM"""
        if hour == 0:
            return "12:00 AM"
        elif hour < 12:
            return f"{hour}:00 AM"
        elif hour == 12:
            return "12:00 PM"
        else:
            return f"{hour-12}:00 PM"
    
    time_slots = []
    
    if worker_shift == 'day':
        # Day shift: 6 AM to 6 PM
        for hour in range(6, 18, 2):  # 2-hour slots from 6 AM to 6 PM
            start_time = f"{hour:02d}:00"
            end_time = f"{(hour + 2):02d}:00"
            time_slots.append({
                'value': f"{start_time}-{end_time}",  # ✅ FIXED: This should be time range like "14:00-16:00"
                'display': f"{format_time_display(hour)} - {format_time_display(hour + 2)}"
            })
    
    elif worker_shift == 'night':
        # Night shift: 6 PM to 6 AM
        # 6 PM to 12 AM
        for hour in range(18, 24, 2):
            start_time = f"{hour:02d}:00"
            end_hour = hour + 2 if hour < 22 else 0
            end_time = f"{end_hour:02d}:00"
            time_slots.append({
                'value': f"{start_time}-{end_time}",  # ✅ FIXED
                'display': f"{format_time_display(hour)} - {format_time_display(end_hour if end_hour != 0 else 24)}"
            })
        # 12 AM to 6 AM
        for hour in range(0, 6, 2):
            start_time = f"{hour:02d}:00"
            end_time = f"{(hour + 2):02d}:00"
            time_slots.append({
                'value': f"{start_time}-{end_time}",  # ✅ FIXED
                'display': f"{format_time_display(hour)} - {format_time_display(hour + 2)}"
            })
    
    else:  # 'all' shift
        # All day: 6 AM to 6 AM next day
        # Day slots (6 AM - 6 PM)
        for hour in range(6, 18, 2):
            start_time = f"{hour:02d}:00"
            end_time = f"{(hour + 2):02d}:00"
            time_slots.append({
                'value': f"{start_time}-{end_time}",  # ✅ FIXED
                'display': f"{format_time_display(hour)} - {format_time_display(hour + 2)}"
            })
        # Evening/Night slots (6 PM - 12 AM)
        for hour in range(18, 24, 2):
            start_time = f"{hour:02d}:00"
            end_hour = hour + 2 if hour < 22 else 0
            end_time = f"{end_hour:02d}:00"
            time_slots.append({
                'value': f"{start_time}-{end_time}",  # ✅ FIXED
                'display': f"{format_time_display(hour)} - {format_time_display(end_hour if end_hour != 0 else 24)}"
            })
        # Early morning slots (12 AM - 6 AM)
        for hour in range(0, 6, 2):
            start_time = f"{hour:02d}:00"
            end_time = f"{(hour + 2):02d}:00"
            time_slots.append({
                'value': f"{start_time}-{end_time}",  # ✅ FIXED
                'display': f"{format_time_display(hour)} - {format_time_display(hour + 2)}"
            })
    
    return time_slots

def get_shift_display_name(shift):
    """Get display name for shift"""
    shift_names = {
        'day': 'Day Shift (6 AM - 6 PM)',
        'night': 'Night Shift (6 PM - 6 AM)', 
        'all': '24 Hours Available'
    }
    return shift_names.get(shift, 'Flexible Hours')


def send_worker_verification_email(worker, approved, rejection_reason=None):
    """Send email notification to worker about verification status - FIXED VERSION"""
    try:
        if approved:
            subject = "🎉 Your BlueCaller Worker Profile Has Been Verified!"
            html_message = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        margin: 0;
                        padding: 0;
                        background-color: #f4f4f4;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 20px auto;
                        background-color: #ffffff;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                        color: white;
                        padding: 40px 20px;
                        text-align: center;
                    }}
                    .content {{
                        padding: 30px;
                    }}
                    .success-badge {{
                        background: #d4edda;
                        color: #155724;
                        padding: 15px;
                        border-radius: 8px;
                        text-align: center;
                        margin: 20px 0;
                        border-left: 4px solid #28a745;
                    }}
                    .button {{
                        display: inline-block;
                        background: #10b981;
                        color: white;
                        padding: 14px 28px;
                        text-decoration: none;
                        border-radius: 8px;
                        font-weight: 600;
                        margin: 10px 0;
                    }}
                    .footer {{
                        background: #f8f9fa;
                        padding: 20px;
                        text-align: center;
                        font-size: 12px;
                        color: #6b7280;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ Profile Verified!</h1>
                        <p>Congratulations! Your worker profile has been approved</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hello {worker.name},</h2>
                        
                        <div class="success-badge">
                            <h3>Your BlueCaller worker profile has been successfully verified!</h3>
                        </div>
                        
                        <p>Great news! Your profile is now active and visible to customers. You can start receiving appointment requests immediately.</p>
                        
                        <h3>What's Next?</h3>
                        <ul>
                            <li>✅ Your profile is now visible in search results</li>
                            <li>✅ Customers can book appointments with you</li>
                            <li>✅ Start building your reputation with reviews</li>
                            <li>✅ Manage your appointments from your dashboard</li>
                        </ul>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{settings.SITE_URL}/worker/dashboard/" class="button">
                                Go to Your Dashboard
                            </a>
                        </div>
                        
                        <p>If you have any questions, please don't hesitate to contact our support team.</p>
                    </div>
                    
                    <div class="footer">
                        <p>Best regards,<br>The BlueCaller Team</p>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            subject = "Update on Your BlueCaller Worker Profile Verification"
            html_message = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        margin: 0;
                        padding: 0;
                        background-color: #f4f4f4;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 20px auto;
                        background-color: #ffffff;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                        color: white;
                        padding: 40px 20px;
                        text-align: center;
                    }}
                    .content {{
                        padding: 30px;
                    }}
                    .warning-badge {{
                        background: #fef2f2;
                        color: #dc2626;
                        padding: 15px;
                        border-radius: 8px;
                        margin: 20px 0;
                        border-left: 4px solid #ef4444;
                    }}
                    .button {{
                        display: inline-block;
                        background: #3b82f6;
                        color: white;
                        padding: 14px 28px;
                        text-decoration: none;
                        border-radius: 8px;
                        font-weight: 600;
                        margin: 10px 0;
                    }}
                    .footer {{
                        background: #f8f9fa;
                        padding: 20px;
                        text-align: center;
                        font-size: 12px;
                        color: #6b7280;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📋 Verification Required</h1>
                        <p>Additional information needed for your profile</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hello {worker.name},</h2>
                        
                        <div class="warning-badge">
                            <h3>Your profile needs additional verification</h3>
                        </div>
                        
                        <p>We've reviewed your worker profile application and need some additional information to complete the verification process.</p>
                        
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin: 20px 0;">
                            <strong>Reason:</strong> {rejection_reason or 'Profile information needs verification'}
                        </div>
                        
                        <h3>What to Do Next?</h3>
                        <ul>
                            <li>📝 Update your profile with the required information</li>
                            <li>📎 Ensure all documents are clear and valid</li>
                            <li>✅ Resubmit your profile for review</li>
                            <li>💬 Contact support if you need assistance</li>
                        </ul>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{settings.SITE_URL}/worker/profile/" class="button">
                                Update Your Profile
                            </a>
                        </div>
                        
                        <p>Once you've made the necessary updates, your profile will be reviewed again within 24-48 hours.</p>
                    </div>
                    
                    <div class="footer">
                        <p>Best regards,<br>The BlueCaller Team</p>
                    </div>
                </div>
            </body>
            </html>
            """
        
        # Plain text version
        plain_message = strip_tags(html_message)
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [worker.owner.email]
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Worker verification email sent to {worker.name} ({worker.owner.email}) - Approved: {approved}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send worker verification email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def public_verify_worker(request, worker_id):
    """
    Public verification endpoint for email links
    This allows verification without requiring admin login
    """
    worker = get_object_or_404(Worker, id=worker_id)
    
    action = request.GET.get('action')
    token = request.GET.get('token')  # Simple security token
    
    # Generate expected token (you can make this more secure)
    import hashlib
    expected_token = hashlib.md5(f"verify_{worker.id}_{worker.created_at}".encode()).hexdigest()
    
    if token != expected_token:
        messages.error(request, "Invalid verification link.")
        return redirect('landing-page')
    
    if action == 'approve':
        worker.verify_worker()
        
        # Send email notification to worker
        try:
            send_worker_verification_email(worker, True)
            messages.success(request, f"Worker {worker.name} has been verified successfully! They are now visible to customers.")
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")
            messages.success(request, f"Worker {worker.name} has been verified successfully! (Email notification failed)")
        
    elif action == 'reject':
        reason = request.GET.get('reason', 'Profile does not meet verification requirements')
        worker.reject_worker(reason)
        
        # Send email notification to worker
        try:
            send_worker_verification_email(worker, False, reason)
            messages.info(request, f"Worker {worker.name} has been rejected. Notification sent.")
        except Exception as e:
            logger.error(f"Failed to send rejection email: {e}")
            messages.info(request, f"Worker {worker.name} has been rejected.")
    
    else:
        messages.error(request, "Invalid action specified.")
    
    # Redirect to admin login or landing page
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard:dashboard')
    else:
        return redirect('landing-page')

def workers_redirect(request):
    """Redirect to worker list"""
    return redirect('worker-list')

class WorkerDetailView(DetailView):
    model = Worker
    template_name = 'jobs/worker_detail.html'

    def get_queryset(self):
        return Worker.objects.all()

    def get_object(self, queryset=None):
        worker = super().get_object(queryset)
        # Remove authentication check - allow public access
        return worker

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker = self.get_object()

        bayesian_rating = worker.bayesian_average_rating()
        total_ratings = worker.ratings.count()
        has_ratings = total_ratings > 0
        
        if has_ratings:
            full_stars = int(bayesian_rating)
            half_star = 1 if bayesian_rating % 1 >= 0.5 else 0
            empty_stars = 5 - (full_stars + half_star)
        else:
            full_stars = 0
            half_star = 0
            empty_stars = 5
        
        # Get rating breakdown only if there are ratings
        rating_breakdown = {}
        if has_ratings:
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
            'average_rating': bayesian_rating,
            'total_ratings': total_ratings,
            'has_ratings': has_ratings,  # ✅ NEW: Add this flag
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
    """Enhanced login handler with cached location tracking"""
    
    if not request.user.is_authenticated:
        return redirect('account_login')
    
    client_ip = get_client_ip(request)
    
    # Check cache first for existing location
    cached_location = get_cached_user_location(request.user.id)
    if cached_location:
        logger.info(f"Using cached location for user {request.user.username}")
        # Update session from cache
        request.session['current_latitude'] = cached_location['latitude']
        request.session['current_longitude'] = cached_location['longitude']
        request.session['location_accuracy'] = cached_location.get('accuracy')
        request.session['location_updated_at'] = cached_location.get('timestamp')
    
    else:
        # Check for pending location data from login form
        pending_location = request.session.get('pending_location')
        
        if pending_location and isinstance(pending_location, dict):
            try:
                lat_float = float(pending_location['latitude'])
                lon_float = float(pending_location['longitude'])
                acc_float = pending_location.get('accuracy')
                
                # Store in session and cache
                request.session['current_latitude'] = lat_float
                request.session['current_longitude'] = lon_float
                request.session['location_accuracy'] = acc_float
                request.session['location_updated_at'] = timezone.now().isoformat()
                
                # Update user profile with caching
                update_user_location_with_coords(
                    request.user, lat_float, lon_float, acc_float, 'browser'
                )
                
                # Clear pending location
                del request.session['pending_location']
                
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Error processing pending location for user {request.user.username}: {e}")
                # Fallback to IP-based location with caching
                update_user_location_with_ip(request.user, client_ip)
        else:
            # No browser location - use IP-based geolocation as fallback with caching
            logger.info(f"No browser location for user {request.user.username}, trying IP-based location")
            update_user_location_with_ip(request.user, client_ip)
    
    # Rest of the handle_login function remains the same...
    if request.session.get('needs_login_otp'):
        user_id = request.session.get('login_user_id')
        if user_id:
            return redirect('verify_login_otp', user_id=user_id)
    
    try:
        worker = request.user.worker
        messages.success(request, f"Welcome back, {worker.name}! Your location has been updated.")
        return redirect('worker_dashboard')
    except Worker.DoesNotExist:
        pass

    try:
        customer = request.user.customer
        messages.success(request, f"Welcome back, {customer.name}! Your location has been updated.")
        return redirect('worker-list')
    except Customer.DoesNotExist:
        pass

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
    API endpoint to update user's current location from browser - with caching
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
            
            # Update session for immediate use
            request.session['current_latitude'] = float(latitude)
            request.session['current_longitude'] = float(longitude)
            request.session['location_accuracy'] = float(accuracy) if accuracy else None
            request.session['location_updated_at'] = timezone.now().isoformat()
            
            # Update user profile with caching
            update_user_location_with_coords(
                request.user, latitude, longitude, accuracy, 'browser'
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Location updated successfully',
                'latitude': latitude,
                'longitude': longitude,
                'accuracy': accuracy,
                'cached': True  # Indicate that location was cached
            })
            
        except Exception as e:
            logger.error(f"Error updating current location: {e}")
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

# NEW: Cache management views
@login_required
def clear_location_cache(request):
    """Clear cached location data for the current user"""
    try:
        cache_key = get_location_cache_key(request.user.id)
        cache.delete(cache_key)
        
        # Also clear session location
        if 'current_latitude' in request.session:
            del request.session['current_latitude']
        if 'current_longitude' in request.session:
            del request.session['current_longitude']
        if 'landing_location' in request.session:
            del request.session['landing_location']
            
        return JsonResponse({
            'success': True,
            'message': 'Location cache cleared successfully'
        })
    except Exception as e:
        logger.error(f"Error clearing location cache: {e}")
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def get_cached_location(request):
    """Get cached location data for the current user"""
    try:
        cached_location = get_cached_user_location(request.user.id)
        if cached_location:
            return JsonResponse({
                'success': True,
                'location': cached_location
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No cached location found'
            })
    except Exception as e:
        logger.error(f"Error getting cached location: {e}")
        return JsonResponse({'error': str(e)}, status=400)



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
    
    # Refresh worker from database to ensure we have latest data
    worker = Worker.objects.get(id=worker.id)
    
    # Get all appointments for this worker
    appointments = Appointment.objects.filter(worker=worker).select_related(
        'customer', 'service_subtask', 'service_subtask__subtask'
    ).only(
        'id', 'customer', 'worker', 'appointment_date', 'status', 
        'service_subtask', 'location', 'special_instructions',
        'customer_completed', 'worker_completed', 'created_at'
    ).order_by('-appointment_date')
    
    # Separate appointments by status
    pending_appointments = appointments.filter(status='pending')
    accepted_appointments = appointments.filter(status='accepted')
    completed_appointments = appointments.filter(status='completed')
    rejected_appointments = appointments.filter(status='rejected')
    
    # Calculate customer completed appointments
    customer_completed_appointments = accepted_appointments.filter(
        customer_completed=True, 
        worker_completed=False
    )
    
    # ✅ CRITICAL: Calculate resubmission data
    can_resubmit = worker.can_resubmit_verification()
    wait_time = worker.get_resubmission_wait_time()
    wait_time_display = worker.get_resubmission_wait_time_display()
    
    print(f"DEBUG - Worker: {worker.name}, Status: {worker.verification_status}, Can Resubmit: {can_resubmit}")  # Debug print
    
    context = {
        'worker': worker,
        'appointments': appointments,
        'pending_appointments': pending_appointments,
        'accepted_appointments': accepted_appointments,
        'completed_appointments': completed_appointments,
        'rejected_appointments': rejected_appointments,
        'customer_completed_appointments': customer_completed_appointments,  
        'today': timezone.now().date(),
        
        # ✅ VERIFICATION CONTEXT - MAKE SURE THESE ARE INCLUDED
        'can_resubmit': can_resubmit,
        'wait_time': wait_time,
        'wait_time_display': wait_time_display,
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
            
            # ✅ FIXED: Create notification for customer
            Notification.objects.create(
                customer=appointment.customer,
                notification_type='appointment_accepted',
                title='Appointment Accepted!',
                message=f'{appointment.worker.name} has accepted your appointment request for {appointment.service_subtask.subtask.name if appointment.service_subtask else "service"}.',
                appointment=appointment
            )
            
            # ✅ FIXED: Send email notification to customer with better error handling
            try:
                send_appointment_status_email(appointment, 'accepted')
                logger.info(f"✅ Appointment acceptance email sent for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"❌ FAILED to send acceptance email for appointment {appointment.id}: {str(email_error)}")
                # Add a message but don't fail the appointment acceptance
                messages.warning(request, "Appointment accepted but email notification failed to send.")
            
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
            
            # ✅ FIXED: Create notification for customer
            Notification.objects.create(
                customer=appointment.customer,
                notification_type='appointment_rejected',
                title='Appointment Declined',
                message=f'{appointment.worker.name} was unable to accept your appointment request.',
                appointment=appointment
            )
            
            # ✅ FIXED: Send email notification to customer with better error handling
            try:
                send_appointment_status_email(appointment, 'rejected')
                logger.info(f"✅ Appointment rejection email sent for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"❌ FAILED to send rejection email for appointment {appointment.id}: {str(email_error)}")
                # Add a message but don't fail the appointment rejection
                messages.warning(request, "Appointment rejected but email notification failed to send.")
            
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
    """Complete appointment and trigger final payment notification"""
    appointment = get_object_or_404(Appointment, id=appointment_id)

    if appointment.worker.owner != request.user:
        messages.error(request, "You are not allowed to complete this appointment.")
        return redirect('worker_dashboard')

    if request.method == 'POST':
        if appointment.status == 'accepted':
            appointment.status = 'completed'
            appointment.save()
            
            # Get payment info
            payment = get_object_or_404(Payment, appointment=appointment)
            
            # Create notification for customer to make final payment
            Notification.objects.create(
                customer=appointment.customer,
                notification_type='work_completed_final_payment',
                title='Work Completed - Final Payment Due',
                message=f'Your work with {appointment.worker.name} has been completed. Please complete your final payment of ₹{payment.remaining_amount}.',
                appointment=appointment
            )
            
            # Send completion email with final payment link
            try:
                send_work_completion_final_payment_email(appointment, payment)
                logger.info(f"Work completion and final payment email sent for appointment {appointment.id}")
            except Exception as email_error:
                logger.error(f"Failed to send completion email for appointment {appointment.id}: {email_error}")
            
            messages.success(request, f"Appointment marked as completed. Customer notified to make final payment of ₹{payment.remaining_amount}.")
        else:
            messages.warning(request, "This appointment cannot be marked as completed.")

    return redirect('worker_dashboard')



def send_work_completion_final_payment_email(appointment, payment):
    """Send email notification for work completion and final payment"""
    try:
        customer = appointment.customer
        worker = appointment.worker
        
        subject = f"Work Completed - Final Payment Due - {worker.name}"
        
        context = {
            'customer_name': customer.name,
            'worker_name': worker.name,
            'service_name': appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service',
            'total_amount': float(payment.amount),
            'initial_paid': float(payment.prepayment_amount),
            'remaining_amount': float(payment.remaining_amount),
            'appointment_date': appointment.appointment_date.strftime('%B %d, %Y') if appointment.appointment_date else 'Not specified',
            'final_payment_url': f"{settings.SITE_URL}/payments/final-payment/{appointment.id}/",
            'site_url': settings.SITE_URL,
        }
        
        html_message = render_to_string('emails/work_completion_final_payment.html', context)
        plain_message = strip_tags(html_message)
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecaller.com')
        recipients = [customer.owner.email]
        
        send_email_async(subject, plain_message, from_email, recipients, html_message)
        
        logger.info(f"Work completion final payment email sent to {customer.name}")
        
    except Exception as e:
        logger.error(f"Failed to send work completion final payment email: {str(e)}")


@login_required
def customer_notifications(request):
    """API endpoint to get customer notifications"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    # Get notifications from the last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    notifications = Notification.objects.filter(
        customer=customer,
        created_at__gte=thirty_days_ago
    ).select_related('appointment', 'appointment__worker').order_by('-created_at')
    
    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'is_read': notification.is_read,
            'time_ago': get_time_ago(notification.created_at),
            'notification_type': notification.notification_type,
            'appointment_id': notification.appointment.id if notification.appointment else None,
            'worker_name': notification.appointment.worker.name if notification.appointment else None,
            'created_at': notification.created_at.isoformat(),
        })
    
    # Also include real-time appointment status updates as notifications
    recent_appointments = Appointment.objects.filter(
        customer=customer,
        updated_at__gte=thirty_days_ago
    ).select_related('worker').order_by('-updated_at')
    
    for appointment in recent_appointments:
        if appointment.status in ['accepted', 'rejected', 'completed']:
            # Check if we already have a notification for this status change
            existing_notification = any(
                n.get('appointment_id') == appointment.id and 
                n.get('notification_type') == f'appointment_{appointment.status}'
                for n in notifications_data
            )
            
            if not existing_notification:
                if appointment.status == 'accepted':
                    notifications_data.append({
                        'id': f'appointment-{appointment.id}-accepted',
                        'title': 'Appointment Accepted!',
                        'message': f'{appointment.worker.name} has accepted your appointment request.',
                        'is_read': False,
                        'time_ago': get_time_ago(appointment.updated_at),
                        'notification_type': 'appointment_accepted',
                        'appointment_id': appointment.id,
                        'worker_name': appointment.worker.name,
                        'created_at': appointment.updated_at.isoformat(),
                    })
                elif appointment.status == 'rejected':
                    notifications_data.append({
                        'id': f'appointment-{appointment.id}-rejected',
                        'title': 'Appointment Declined',
                        'message': f'{appointment.worker.name} was unable to accept your appointment request.',
                        'is_read': False,
                        'time_ago': get_time_ago(appointment.updated_at),
                        'notification_type': 'appointment_rejected',
                        'appointment_id': appointment.id,
                        'worker_name': appointment.worker.name,
                        'created_at': appointment.updated_at.isoformat(),
                    })
                elif appointment.status == 'completed':
                    notifications_data.append({
                        'id': f'appointment-{appointment.id}-completed',
                        'title': 'Appointment Completed',
                        'message': f'Your appointment with {appointment.worker.name} has been completed.',
                        'is_read': False,
                        'time_ago': get_time_ago(appointment.updated_at),
                        'notification_type': 'appointment_completed',
                        'appointment_id': appointment.id,
                        'worker_name': appointment.worker.name,
                        'created_at': appointment.updated_at.isoformat(),
                    })
    
    # Sort all notifications by creation date (newest first)
    notifications_data.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Count unread notifications
    unread_count = len([n for n in notifications_data if not n['is_read']])
    
    return JsonResponse({
        'notifications': notifications_data[:20],  # Limit to 20 most recent
        'unread_count': unread_count
    })

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
        
        # ✅ FIXED: Force update worker's average rating using Bayesian algorithm
        worker = appointment.worker
        worker.update_average_rating()  # This now uses Bayesian average
        
        # Debug info - you can remove this later
        print(f"Rating submitted: {rating_value}")
        print(f"Worker {worker.name} new Bayesian average: {worker.average_rating}")
        print(f"Total ratings: {worker.rating_count}")
        
        return redirect('customer_dashboard')
    
    # For GET request, show the rating form
    context = {
        'appointment': appointment,
        'existing_rating': existing_rating
    }
    
    return render(request, 'jobs/rate_worker.html', context)


@login_required
def mark_customer_completed(request, pk):
    """Enhanced version that creates notifications when customer marks as completed"""
    appointment = get_object_or_404(Appointment, pk=pk)

    # Ensure the logged-in user is the customer who booked the appointment
    if not hasattr(request.user, 'customer') or appointment.customer != request.user.customer:
        return HttpResponseForbidden("Only the customer can mark this appointment as completed.")

    # Customer can only mark completed if the worker has accepted the job
    if appointment.status != 'accepted':
        messages.error(request, "You can only mark appointments as completed after they are accepted.")
        return redirect('customer_appointments')

    # Store previous state to check if we're changing from False to True
    was_completed = appointment.customer_completed
    
    # Mark as completed by customer
    appointment.customer_completed = True
    appointment.save()

    # ✅ NEW: Create notification for worker (only if it was just marked as completed)
    if not was_completed:
        Notification.objects.create(
            worker=appointment.worker,
            notification_type='customer_completed',
            title='Customer Marked Work as Completed',
            message=f'{appointment.customer.name} has marked the appointment as completed. Please confirm completion.',
            appointment=appointment
        )
        
        # Also send email notification to worker
        try:
            send_customer_completion_email(appointment)
            logger.info(f"Customer completion email sent for appointment {appointment.id}")
        except Exception as email_error:
            logger.error(f"Failed to send customer completion email for appointment {appointment.id}: {email_error}")

    messages.success(request, "You marked the appointment as completed. The worker has been notified to confirm.")
    return redirect('customer_appointments')

@login_required
def mark_worker_completed(request, pk):
    """Enhanced version that sends notification to customer when worker confirms completion"""
    appointment = get_object_or_404(Appointment, pk=pk)

    # Ensure the logged-in user is the assigned worker
    if not hasattr(request.user, 'worker') or appointment.worker != request.user.worker:
        return HttpResponseForbidden("Only the assigned worker can mark this appointment as completed.")

    # Prevent worker from marking complete before customer
    if not appointment.customer_completed:
        messages.error(request, "The customer must mark the appointment as completed first.")
        return redirect('worker_dashboard')

    # Store previous state
    was_completed = appointment.worker_completed
    
    # Worker confirms completion
    appointment.status = 'completed'
    appointment.worker_completed = True
    appointment.save()
    
    # ✅ NEW: Create notification for customer
    if not was_completed:
        Notification.objects.create(
            customer=appointment.customer,
            notification_type='worker_completed',
            title='Worker Confirmed Completion',
            message=f'{appointment.worker.name} has confirmed the appointment completion. Thank you for your business!',
            appointment=appointment
        )
        
        # Send email notification to customer
        try:
            send_worker_completion_email(appointment)
            logger.info(f"Worker completion email sent for appointment {appointment.id}")
        except Exception as email_error:
            logger.error(f"Failed to send worker completion email for appointment {appointment.id}: {email_error}")
            # Continue without failing
            messages.warning(request, "Completion confirmed but email notification may have failed.")

    messages.success(request, "You confirmed the appointment as completed. The customer has been notified.")
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
    
    # ✅ NEW: Get unread notification count for the template
    unread_notification_count = Notification.objects.filter(
        customer=customer,
        is_read=False
    ).count()
    
    # Ratings and Reviews Data
    customer_ratings = WorkerRating.objects.filter(customer=customer).select_related(
        'worker', 'appointment', 'appointment__service_subtask__subtask'
    ).order_by('-created_at')
    
    total_reviews = customer_ratings.count()
    
    # Calculate average rating
    if total_reviews > 0:
        ratings_list = [rating.rating for rating in customer_ratings]
        average_rating = sum(ratings_list) / len(ratings_list)
        average_rating_int = int(average_rating)
    else:
        average_rating = 0.0
        average_rating_int = 0
    
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
        'total_reviews': total_reviews,
        'average_rating': round(average_rating, 1),
        'average_rating_int': average_rating_int,
        # ✅ NEW: Notification context
        'unread_notification_count': unread_notification_count,
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

@login_required
def customer_reviews(request):
    """View for customers to see their reviews"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    # Get all ratings given by this customer, ordered by creation date (newest first)
    ratings = WorkerRating.objects.filter(customer=customer).select_related(
        'worker', 'appointment'
    ).order_by('-created_at')
    
    # ✅ CRITICAL: Get unread notification count for the template
    unread_notification_count = Notification.objects.filter(
        customer=customer,
        is_read=False
    ).count()
    
    context = {
        'ratings': ratings,
        'customer': customer,  # ✅ Make sure customer is passed to template
        'current_page': 'reviews',
        'unread_notification_count': unread_notification_count,  # ✅ Add notification count
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
    """Enhanced customer settings view with security features"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    if request.method == 'POST':
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            import json
            data = json.loads(request.body)
            
            # Toggle 2FA
            if data.get('toggle_2fa'):
                customer.two_factor_enabled = data.get('enable', False)
                customer.save()
                return JsonResponse({'success': True})
            
            # Verify security answers
            elif data.get('verify_security_answers'):
                # In a real implementation, you'd verify against stored answers
                stored_answers = customer.get_security_answers()
                if (data.get('answer1') == stored_answers.get('answer1') and
                    data.get('answer2') == stored_answers.get('answer2') and
                    data.get('answer3') == stored_answers.get('answer3')):
                    return JsonResponse({'success': True})
                else:
                    return JsonResponse({'success': False, 'error': 'Answers do not match'})
            
            # Get active sessions
            elif data.get('get_sessions'):
                sessions = get_active_sessions(request)
                return JsonResponse({'success': True, 'sessions': sessions})
            
            # Logout specific session
            elif data.get('logout_session'):
                success = logout_session(request, data.get('session_key'))
                return JsonResponse({'success': success})
            
            # Logout all sessions
            elif data.get('logout_all_sessions'):
                logout_all_sessions_except_current(request)
                return JsonResponse({'success': True})
        
        # Handle regular form submissions
        if 'change_password' in request.POST:
            current_password = request.POST.get('current_password')
            new_password1 = request.POST.get('new_password1')
            new_password2 = request.POST.get('new_password2')
            
            if not request.user.check_password(current_password):
                messages.error(request, "Current password is incorrect.")
            elif new_password1 != new_password2:
                messages.error(request, "New passwords do not match.")
            elif len(new_password1) < 8:
                messages.error(request, "Password must be at least 8 characters long.")
            else:
                request.user.set_password(new_password1)
                request.user.save()
                update_session_auth_hash(request, request.user)  # Keep user logged in
                messages.success(request, "Password changed successfully!")
        
        # Forgot password
        elif 'forgot_password' in request.POST:
            email = request.POST.get('forgot_password_email')
            # In a real implementation, you'd send a password reset email
            messages.info(request, "Password reset link has been sent to your email.")
        
        # Setup security questions
        elif 'setup_security_questions' in request.POST:
            customer.security_answers = {
                'answer1': request.POST.get('security_answer1', '').lower().strip(),
                'answer2': request.POST.get('security_answer2', '').lower().strip(),
                'answer3': request.POST.get('security_answer3', '').lower().strip()
            }
            customer.security_questions_set = True
            customer.save()
            messages.success(request, "Security questions setup successfully!")
        
        # Update privacy settings
        elif 'update_privacy' in request.POST:
            customer.profile_visible = 'profile_visibility' in request.POST
            customer.location_sharing_enabled = 'location_sharing' in request.POST
            customer.email_notifications = 'email_notifications' in request.POST
            customer.save()
            messages.success(request, "Privacy settings updated successfully!")
        
        return redirect('customer_settings')
    
    context = {
        'customer': customer,
        'current_page': 'settings'
    }
    
    return render(request, 'jobs/customer_settings.html', context)

def get_active_sessions(request):
    """Get active sessions for the current user"""
    # This is a simplified implementation
    # In a real app, you'd track sessions in your database
    sessions = [
        {
            'device': 'Chrome on Windows',
            'browser': 'Chrome 119.0',
            'location': 'New York, US',
            'last_active': '2 hours ago',
            'current': True,
            'session_key': 'current'
        },
        {
            'device': 'Safari on iPhone',
            'browser': 'Safari 16.0',
            'location': 'Boston, US',
            'last_active': '1 day ago',
            'current': False,
            'session_key': 'mobile_123'
        }
    ]
    return sessions

def logout_session(request, session_key):
    """Logout a specific session"""
    # In a real implementation, you'd invalidate the session
    # This is a placeholder
    return True

def logout_all_sessions_except_current(request):
    """Logout all sessions except current"""
    # In a real implementation, you'd invalidate all other sessions
    # This is a placeholder
    return True

@login_required
def customer_support(request):
    """View for customer support"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    context = {
        'customer': customer,
        'current_page': 'support'
    }
    return render(request, 'jobs/customer_support.html', context)

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
    
    # Get database notifications
    db_notifications = Notification.objects.filter(
        worker=worker,
        created_at__gte=seven_days_ago
    ).select_related('appointment', 'appointment__customer').order_by('-created_at')
    
    # Format notifications
    notifications = []
    
    for notification in db_notifications:
        notifications.append({
            'id': f'db-{notification.id}',
            'type': notification.notification_type,
            'title': notification.title,
            'message': notification.message,
            'is_read': notification.is_read,
            'created_at': notification.created_at.isoformat(),
            'time_ago': get_time_ago(notification.created_at),
            'appointment_id': notification.appointment.id if notification.appointment else None,
            'customer_name': notification.appointment.customer.name if notification.appointment else None
        })
    
    # Also include real-time notifications for pending appointments and customer completions
    pending_appointments = Appointment.objects.filter(
        worker=worker, 
        status='pending',
        created_at__gte=seven_days_ago
    ).select_related('customer').order_by('-created_at')
    
    for appointment in pending_appointments:
        notifications.append({
            'id': f'appointment-pending-{appointment.id}',
            'type': 'appointment_request',
            'title': 'New Appointment Request',
            'message': f'New appointment request from {appointment.customer.name}',
            'customer_name': appointment.customer.name,
            'appointment_id': appointment.id,
            'is_read': False,
            'created_at': appointment.created_at.isoformat(),
            'time_ago': get_time_ago(appointment.created_at)
        })
    
    # ✅ NEW: Include customer completion notifications
    customer_completed_appointments = Appointment.objects.filter(
        worker=worker,
        customer_completed=True,
        worker_completed=False,
        updated_at__gte=seven_days_ago
    ).select_related('customer').order_by('-updated_at')
    
    for appointment in customer_completed_appointments:
        notifications.append({
            'id': f'customer-completed-{appointment.id}',
            'type': 'customer_completed',
            'title': 'Customer Marked Work as Completed',
            'message': f'{appointment.customer.name} marked the appointment as completed. Please confirm completion.',
            'customer_name': appointment.customer.name,
            'appointment_id': appointment.id,
            'is_read': False,
            'created_at': appointment.updated_at.isoformat(),
            'time_ago': get_time_ago(appointment.updated_at)
        })
    
    # Count unread notifications
    unread_count = len([n for n in notifications if not n['is_read']])
    
    # Sort all notifications by creation date (newest first)
    notifications.sort(key=lambda x: x['created_at'], reverse=True)
    
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
    """API endpoint to mark all notifications as read for the current user"""
    try:
        # Handle both worker and customer notifications
        if hasattr(request.user, 'worker'):
            # Mark all worker notifications as read
            updated_count = Notification.objects.filter(
                worker=request.user.worker, 
                is_read=False
            ).update(is_read=True)
            
            # Also mark any appointment-based notifications
            worker_appointments = Appointment.objects.filter(worker=request.user.worker)
            for appointment in worker_appointments:
                # Mark customer completion notifications as read
                Notification.objects.filter(
                    appointment=appointment,
                    notification_type='customer_completed',
                    is_read=False
                ).update(is_read=True)
                
        elif hasattr(request.user, 'customer'):
            # Mark all customer notifications as read
            updated_count = Notification.objects.filter(
                customer=request.user.customer, 
                is_read=False
            ).update(is_read=True)
        else:
            return JsonResponse({'success': False, 'error': 'User profile not found'}, status=400)
        
        return JsonResponse({
            'success': True,
            'marked_read': updated_count
        })
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'An error occurred: {str(e)}'
        }, status=500)

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
    """View to handle appointment request form - supports both form and JSON"""
    worker = get_object_or_404(Worker, id=worker_id)
    
    # Check if user has a customer profile
    try:
        customer = request.user.customer
    except AttributeError:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({'error': 'You need a customer profile to book appointments.'}, status=403)
        messages.error(request, "You need a customer profile to book appointments.")
        return redirect('customer-create')

    if request.method == "POST":
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json'
        
        try:
            if is_ajax and request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST
                
            service_id = data.get("service_id")
            preferred_date = data.get("preferred_date")
            preferred_time = data.get("preferred_time")  # This is "14:00-16:00"
            address = data.get("address", "")
            special_instructions = data.get("special_instructions", "")
            customer_name = data.get("customer_name", "")
            customer_phone = data.get("customer_phone", "")
            latitude = data.get("latitude")
            longitude = data.get("longitude")

            print(f"📥 Received data - Date: {preferred_date}, Time: {preferred_time}")

            # Validate required fields
            if not all([preferred_date, preferred_time, address]):
                error_msg = "Please fill in all required fields."
                if is_ajax:
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('worker-detail', pk=worker_id)

            try:
                # ✅ FIXED: Extract start time from time range
                if '-' in preferred_time:
                    start_time_str = preferred_time.split('-')[0].strip()  # Gets "14:00"
                    print(f"🕒 Extracted start time: {start_time_str}")
                else:
                    start_time_str = preferred_time
                    print(f"🕒 Using single time: {start_time_str}")

                # Combine date with start time for appointment_date
                datetime_str = f"{preferred_date} {start_time_str}"
                print(f"🕒 Final datetime string: {datetime_str}")
                
                # Try different datetime formats for the start time
                datetime_formats = [
                    "%Y-%m-%d %H:%M",    # 2024-01-15 14:00
                    "%Y-%m-%d %H:%M:%S", # 2024-01-15 14:00:00
                    "%Y-%m-%d %I:%M %p", # 2024-01-15 02:00 PM
                ]
                
                appointment_datetime = None
                for fmt in datetime_formats:
                    try:
                        naive_datetime = datetime.strptime(datetime_str, fmt)
                        appointment_datetime = make_aware(naive_datetime)
                        print(f"✅ Successfully parsed with format: {fmt}")
                        break
                    except ValueError:
                        continue
                
                if not appointment_datetime:
                    error_msg = f"Invalid appointment date or time format. Received time range: {preferred_time}"
                    print(f"❌ {error_msg}")
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('worker-detail', pk=worker_id)
                
                # Check if appointment is in the future
                if appointment_datetime <= now():
                    error_msg = "You can only book appointments for future dates/times."
                    print(f"❌ {error_msg}")
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('worker-detail', pk=worker_id)

                # Check for conflicting appointments
                conflicting_appointments = Appointment.objects.filter(
                    worker=worker,
                    appointment_date=appointment_datetime,
                    status__in=['pending', 'accepted']
                )
                
                if conflicting_appointments.exists():
                    error_msg = "Worker already has an appointment at this time."
                    print(f"❌ {error_msg}")
                    if is_ajax:
                        return JsonResponse({'error': error_msg}, status=400)
                    messages.error(request, error_msg)
                    return redirect('worker-detail', pk=worker_id)

                # Get service subtask pricing if service_id is provided
                service_subtask = None
                if service_id and service_id not in ['default', 'consultation', 'null', '']:
                    try:
                        service_subtask = WorkerSubTaskPricing.objects.get(id=service_id)
                        print(f"✅ Found service subtask: {service_subtask}")
                    except (WorkerSubTaskPricing.DoesNotExist, ValueError) as e:
                        print(f"⚠️ Service subtask not found with ID: {service_id}, error: {e}")
                        pass

                # ✅ FIXED: Create appointment with BOTH time_slot and appointment_date
                appointment = Appointment.objects.create(
                    customer=customer,
                    worker=worker,
                    appointment_date=appointment_datetime,  # This is the start time
                    time_slot=preferred_time,  # ✅ Store the original time range
                    status="pending",
                    service_subtask=service_subtask,
                    location=address,
                    special_instructions=special_instructions,
                    customer_latitude=latitude,
                    customer_longitude=longitude
                )

                print(f"✅ Appointment created: {appointment.id}")

                # Update customer info if provided
                if customer_name and customer_name != customer.name:
                    customer.name = customer_name
                if customer_phone and customer_phone != str(customer.phone_number):
                    try:
                        customer.phone_number = customer_phone
                    except ValidationError:
                        print(f"⚠️ Invalid phone number provided: {customer_phone}")
                        pass
                customer.save()

                # Send email notification to worker
                try:
                    send_appointment_request_email(worker, appointment)
                    print(f"✅ Email sent for appointment {appointment.id}")
                except Exception as email_error:
                    print(f"⚠️ Email sending failed: {email_error}")

                # Return success response for AJAX
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': 'Appointment request sent successfully!',
                        'appointment_id': appointment.id
                    })

                messages.success(request, "Appointment request sent successfully!")
                return redirect('customer_appointments')

            except ValueError as e:
                error_msg = f"Invalid appointment date or time format: {str(e)}"
                print(f"❌ {error_msg}")
                if is_ajax:
                    return JsonResponse({'error': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('worker-detail', pk=worker_id)
                
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON data: {str(e)}"
            print(f"❌ {error_msg}")
            if is_ajax:
                return JsonResponse({'error': error_msg}, status=400)
            messages.error(request, "Invalid form data.")
            return redirect('worker-detail', pk=worker_id)
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"❌ {error_msg}")
            if is_ajax:
                return JsonResponse({'error': error_msg}, status=500)
            messages.error(request, "An error occurred while processing your request.")
            return redirect('worker-detail', pk=worker_id)
    
    # GET request - redirect to worker detail
    return redirect('worker-detail', pk=worker_id)


def worker_service_details(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)

    # Get dynamic time slots based on worker's shift preference
    time_slots = get_dynamic_time_slots(worker.shift)
    shift_display = get_shift_display_name(worker.shift)
    
    # Check for AJAX filter requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        search_query = request.GET.get('search', '').lower()
        price_filter = request.GET.get('price_filter', 'all')
        category_filter = request.GET.get('category_filter', 'all')
        
        # Return filtered results via AJAX
        return filter_services_ajax(worker, search_query, price_filter, category_filter)
    
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
        
        # ✅ NEW: Ensure base_price is properly set for all services for client-side filtering
        for category in categories_data:
            for service in category['services']:
                # Make sure base_price is properly set for filtering
                if service.get('base_price') is None:
                    # Extract numeric price from price_display if possible
                    price_display = service.get('price_display', '')
                    if '₹' in price_display:
                        try:
                            # Extract numeric value from price string like "₹500/hour"
                            import re
                            price_match = re.search(r'₹(\d+(?:\.\d+)?)', price_display)
                            if price_match:
                                service['base_price'] = float(price_match.group(1))
                            else:
                                service['base_price'] = 0.0
                        except (ValueError, TypeError):
                            service['base_price'] = 0.0
                    else:
                        service['base_price'] = 0.0
        
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
                'base_price': 0.0,  # ✅ Explicitly set base_price for filtering
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
    
    # Convert to JSON string for safe template rendering
    import json
    from datetime import date  
    categories_data_json = json.dumps(categories_data, ensure_ascii=False)
    
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

        'time_slots': time_slots,
        'shift_display': shift_display,
        'worker_shift': worker.shift,

          # ✅ ADD THIS LINE:
        'KHALTI_PUBLIC_KEY': settings.KHALTI_PUBLIC_KEY,
    }
    
    return render(request, 'jobs/worker_service_details.html', context)


def filter_services_ajax(worker, search_query, price_filter, category_filter):
    """AJAX endpoint for filtering services"""
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
            
            # Apply category filter
            if category_filter != 'all' and str(category.id) != category_filter:
                continue
                
            if category.id not in categories_dict:
                categories_dict[category.id] = {
                    'id': str(category.id),
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
                
                # Get base price for filtering
                try:
                    base_price = float(pricing.price) if pricing.price else 0.0
                except (ValueError, TypeError):
                    base_price = 0.0
                
                # Apply price filter
                matches_price = True
                if price_filter != 'all':
                    if price_filter == '0-500':
                        matches_price = base_price > 0 and base_price < 500
                    elif price_filter == '500-1000':
                        matches_price = base_price >= 500 and base_price <= 1000
                    elif price_filter == '1000+':
                        matches_price = base_price > 1000
                    elif price_filter == 'consultation':
                        matches_price = base_price == 0
                
                # Apply search filter
                matches_search = True
                if search_query:
                    searchable_text = f"{subtask.name} {subtask.description} {getattr(subtask, 'detailed_description', '')}".lower()
                    matches_search = search_query in searchable_text
                
                if matches_price and matches_search:
                    # Build service data (similar to main function)
                    service_data = {
                        'id': str(pricing.id),
                        'name': str(getattr(subtask, 'name', 'Service')),
                        'description': str(getattr(subtask, 'description', 'Professional service')),
                        'price_display': f"₹{base_price:.2f}" if base_price > 0 else "Contact for pricing",
                        'base_price': base_price,
                        'image': str(worker_service.service.image.url) if worker_service.service.image else None,
                    }
                    categories_dict[category.id]['services'].append(service_data)
        
        # Convert to list and remove empty categories
        filtered_categories = [cat for cat in categories_dict.values() if cat['services']]
        total_services = sum(len(cat['services']) for cat in filtered_categories)
        
        return JsonResponse({
            'categories': filtered_categories,
            'total_services': total_services,
            'has_results': total_services > 0
        })
        
    except Exception as e:
        logger.error(f"Error in filter_services_ajax: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)


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
    
    # Calculate distance for each favorite worker and add shift info
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
        
        # ✅ NEW: Add shift information and time slots
        worker.time_slots = get_dynamic_time_slots(worker.shift)
        worker.shift_display = get_shift_display_name(worker.shift)
        
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

from .forms import WorkerProfileForm as WorkerForm

@login_required
def debug_verification(request):
    """Temporary debug view to check verification status"""
    try:
        worker = request.user.worker
    except AttributeError:
        return JsonResponse({'error': 'No worker profile'})
    
    # Get context data that should be passed to template
    can_resubmit = worker.can_resubmit_verification()
    wait_time = worker.get_resubmission_wait_time()
    wait_time_display = worker.get_resubmission_wait_time_display()
    
    debug_data = {
        'worker_id': worker.id,
        'worker_name': worker.name,
        'verified': worker.verified,
        'verification_status': worker.verification_status,
        'rejection_reason': worker.rejection_reason,
        'last_rejection_date': str(worker.last_rejection_date),
        'can_resubmit': can_resubmit,
        'wait_time': wait_time,
        'wait_time_display': wait_time_display,
        
        # Template conditions
        'template_show_section': worker.verification_status == 'rejected',
        'template_show_button': worker.verification_status == 'rejected' and can_resubmit,
        'template_show_disabled_button': worker.verification_status == 'rejected' and not can_resubmit,
    }
    
    return JsonResponse(debug_data)

@login_required
def create_worker_profile(request):
    """DEBUG VERSION - Track exactly what's happening with email"""
    print("🔍 DEBUG: create_worker_profile CALLED")
    print(f"🔍 DEBUG: User: {request.user}, Method: {request.method}")
    
    # Check if user already has worker profile
    if hasattr(request.user, 'worker'):
        print("🔍 DEBUG: User already has worker profile - redirecting to dashboard")
        messages.info(request, "You already have a worker profile.")
        return redirect('worker_dashboard')
    
    if request.method == 'POST':
        print("🔍 DEBUG: POST request detected")
        print("🔍 DEBUG: POST data:", dict(request.POST))
        print("🔍 DEBUG: FILES data:", dict(request.FILES) if request.FILES else 'No files')
        
        form = WorkerForm(request.POST, request.FILES)
        print(f"🔍 DEBUG: Form is valid: {form.is_valid()}")
        
        if form.is_valid():
            print("✅ DEBUG: FORM IS VALID - Proceeding to save")
            try:
                worker = form.save(commit=False)
                worker.owner = request.user
                worker.verified = False
                worker.verification_status = 'pending'
                
                # Handle location
                latitude = request.POST.get('latitude')
                longitude = request.POST.get('longitude')
                print(f"🔍 DEBUG: Location data - lat: {latitude}, lon: {longitude}")
                
                if latitude and longitude:
                    worker.latitude = float(latitude)
                    worker.longitude = float(longitude)
                    print("✅ DEBUG: Location data saved")
                else:
                    print("❌ DEBUG: No location data provided")
                
                print(f"✅ DEBUG: Saving worker: {worker.name}")
                worker.save()
                print(f"✅ DEBUG: Worker saved with ID: {worker.id}")
                
                # 🧪 CRITICAL: Email sending block
                print("🧪 DEBUG: ========== ATTEMPTING TO SEND EMAIL ==========")
                try:
                    from jobs.views import send_verification_request_notification
                    
                    print("🔍 DEBUG: Calling send_verification_request_notification...")
                    email_result = send_verification_request_notification(worker)
                    print(f"🔍 DEBUG: Email function returned: {email_result}")
                    
                    if email_result:
                        print("✅✅✅ DEBUG: EMAIL SENT SUCCESSFULLY!")
                        messages.success(request, "Profile created and verification email sent to admin!")
                    else:
                        print("❌❌❌ DEBUG: EMAIL FUNCTION RETURNED FALSE")
                        messages.warning(request, "Profile created but email notification failed")
                        
                except Exception as email_error:
                    print(f"❌❌❌ DEBUG: EMAIL ERROR: {str(email_error)}")
                    import traceback
                    traceback.print_exc()
                    messages.warning(request, "Profile created but email notification failed")
                
                print("🔍 DEBUG: Redirecting to worker_dashboard")
                return redirect('worker_dashboard')
                
            except Exception as save_error:
                print(f"❌ DEBUG: Error saving worker: {str(save_error)}")
                import traceback
                traceback.print_exc()
                messages.error(request, f"Error saving profile: {str(save_error)}")
                return render(request, 'jobs/worker_form.html', {'form': form})
        else:
            print("❌ DEBUG: FORM INVALID - Errors below:")
            for field, errors in form.errors.items():
                print(f"❌ DEBUG: {field}: {errors}")
            
            # Check specific common issues
            if 'citizenship_image' in form.errors:
                print("❌ DEBUG: Citizenship image validation failed")
            if 'latitude' in form.errors or 'longitude' in form.errors:
                print("❌ DEBUG: Location validation failed")
            
            messages.error(request, "Please fix the errors below.")
            return render(request, 'jobs/worker_form.html', {'form': form})
    
    else:
        print("🔍 DEBUG: GET request - showing empty form")
        form = WorkerForm()
    
    return render(request, 'jobs/worker_form.html', {'form': form})


def send_verification_request_notification(worker):
    """Send email notification to admin about new worker verification request - FIXED"""
    try:
        logger.info(f"🔍 Starting verification email for worker: {worker.name}")
        
        # Use your admin email
        admin_email = 'rubythapa506@gmail.com'  # Change to your actual admin email
        
        subject = f"New Worker Verification Request - {worker.name}"
        
        # Generate secure tokens for verification links
        import hashlib
        approve_token = hashlib.md5(f"verify_{worker.id}_{worker.created_at}".encode()).hexdigest()
        reject_token = hashlib.md5(f"reject_{worker.id}_{worker.created_at}".encode()).hexdigest()
        
        # Create the context with verification links
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        
        # Public verification links (no login required)
        approve_url = f"{base_url}/public-verify-worker/{worker.id}/?action=approve&token={approve_token}"
        reject_url = f"{base_url}/public-verify-worker/{worker.id}/?action=reject&token={reject_token}"
        
        context = {
            'worker_name': worker.name,
            'worker_email': worker.owner.email,
            'worker_phone': str(worker.phone_number),
            'worker_tagline': worker.tagline,
            'worker_id': worker.id,
            'request_id': f"WR{worker.id:06d}",
            'submission_date': worker.created_at.strftime('%B %d, %Y at %I:%M %p') if worker.created_at else "Just now",
            'verification_url': f"{base_url}/admin-dashboard/",
            'admin_dashboard_url': f"{base_url}/admin-dashboard/",
            # ✅ CORRECTED: Use the same variable names as your email template
            'approve_url': approve_url,
            'reject_url': reject_url,
        }
        
        # Try to render the template
        try:
            html_message = render_to_string('emails/worker_verification_request.html', context)
            logger.info("✅ Used worker_verification_request.html template")
        except Exception as template_error:
            logger.warning(f"⚠️ Template error: {template_error}. Using fallback HTML.")
            html_message = create_fallback_email_html(context)
        
        # Plain text version
        plain_message = f"""
New Worker Verification Request - BlueCaller

Worker: {worker.name}
Email: {worker.owner.email}
Phone: {worker.phone_number}
Tagline: {worker.tagline}

APPROVE this worker: {approve_url}
REJECT this worker: {reject_url}

Or review in admin dashboard: {base_url}/admin-dashboard/

Best regards,
BlueCaller System
        """
        
        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[admin_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"✅ Verification email sent to: {admin_email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ FAILED to send verification email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def create_fallback_email_html(context):
    """Create fallback HTML email"""
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #4f46e5; color: white; padding: 20px; text-align: center; }}
        .worker-info {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>New Worker Verification Request</h1>
        </div>
        <div class="content">
            <p>Hello Admin,</p>
            <p>A new worker has submitted their profile for verification:</p>
            
            <div class="worker-info">
                <h3>Worker Details:</h3>
                <p><strong>Name:</strong> {context['worker_name']}</p>
                <p><strong>Email:</strong> {context['worker_email']}</p>
                <p><strong>Phone:</strong> {context['worker_phone']}</p>
                <p><strong>Tagline:</strong> {context['worker_tagline']}</p>
                <p><strong>Request ID:</strong> {context['request_id']}</p>
            </div>
            
            <p>Please review this worker in the admin dashboard.</p>
        </div>
    </div>
</body>
</html>
    """

@login_required
@user_passes_test(admin_required)
def verify_worker_from_dashboard(request, worker_id):
    """Handle worker verification directly from admin dashboard"""
    worker = get_object_or_404(Worker, id=worker_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            worker.verify_worker()
            
            # Send verification email to worker
            try:
                send_worker_verification_email(worker, True)
                messages.success(request, f"Worker {worker.name} approved successfully! Verification email sent.")
            except Exception as e:
                logger.error(f"Failed to send verification email: {e}")
                messages.success(request, f"Worker {worker.name} approved successfully! (Email notification failed)")
            
        elif action == 'reject':
            reason = request.POST.get('reason', 'Profile does not meet verification requirements')
            worker.reject_worker(reason)
            
            # Send rejection email to worker
            try:
                send_worker_verification_email(worker, False, reason)
                messages.info(request, f"Worker {worker.name} rejected. Notification sent.")
            except Exception as e:
                logger.error(f"Failed to send rejection email: {e}")
                messages.info(request, f"Worker {worker.name} rejected.")
        
        else:
            messages.error(request, "Invalid action specified.")
    
    return redirect('admin_dashboard:dashboard')


@login_required
def debug_worker_create(request):
    """Temporary debug view to test form submission"""
    if request.method == 'POST':
        print("🔍 DEBUG: Raw POST data:")
        for key, value in request.POST.items():
            print(f"  {key}: {value}")
        
        print("🔍 DEBUG: Files:")
        for key, file in request.FILES.items():
            print(f"  {key}: {file.name}")
        
        form = WorkerForm(request.POST, request.FILES)
        if form.is_valid():
            print("✅ DEBUG: Form is valid!")
            # Continue with your existing logic
            return redirect('worker_dashboard')
        else:
            print("❌ DEBUG: Form invalid:", form.errors)
            return render(request, 'jobs/worker_form.html', {'form': form})
    
    return redirect('worker-create')


@login_required
def worker_calendar(request):
    """Worker calendar view with dynamic data"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get today's date for the template
    today = timezone.now().date()
    
    # Get appointments for the calendar and stats
    appointments = Appointment.objects.filter(worker=worker).select_related(
        'customer', 'service_subtask', 'service_subtask__subtask'
    ).order_by('appointment_date')
    
    # Calculate statistics for the dashboard
    today_appointments = appointments.filter(
        appointment_date__date=today,
        status__in=['pending', 'accepted']
    )
    
    # This week's appointments (next 7 days)
    week_start = today
    week_end = today + timedelta(days=7)
    week_appointments = appointments.filter(
        appointment_date__date__range=[week_start, week_end],
        status__in=['pending', 'accepted']
    )
    
    # Count pending appointments
    pending_count = appointments.filter(status='pending').count()
    
    # Calculate completion rate (this month)
    month_start = today.replace(day=1)
    month_appointments = appointments.filter(
        appointment_date__date__gte=month_start
    )
    completed_this_month = month_appointments.filter(status='completed').count()
    total_this_month = month_appointments.count()
    completion_rate = round((completed_this_month / total_this_month * 100) if total_this_month > 0 else 0)
    
    # Format appointments for FullCalendar
    calendar_events = []
    for appointment in appointments:
        # Determine event color based on status
        status_colors = {
            'pending': '#f59e0b',    # amber
            'accepted': '#22c55e',   # green  
            'completed': '#6366f1',  # indigo
            'rejected': '#ef4444',   # red
        }
        
        # Calculate end time (2 hours duration by default)
        end_time = appointment.appointment_date + timedelta(hours=2)
        
        calendar_events.append({
            'id': appointment.id,
            'title': f"{appointment.customer.name} - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}",
            'start': appointment.appointment_date.isoformat(),
            'end': end_time.isoformat(),
            'color': status_colors.get(appointment.status, '#6b7280'),
            'textColor': '#ffffff',
            'extendedProps': {
                'status': appointment.status,
                'customer': appointment.customer.name,
                'service': appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service',
                'location': appointment.location or 'No location specified',
                'special_instructions': appointment.special_instructions or 'No special instructions',
                'phone': str(appointment.customer.phone_number),
            }
        })
    
    context = {
        'worker': worker,
        'appointments': appointments,  # Pass queryset for template
        'today_appointments': today_appointments,
        'week_appointments': week_appointments,
        'pending_count': pending_count,
        'completion_rate': completion_rate,
        'today': today,
        'calendar_events_json': json.dumps(calendar_events),  # JSON for JavaScript
    }
    
    # AJAX request - return only calendar events
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'events': calendar_events})
    
    return render(request, 'jobs/worker_calendar.html', context)

@login_required
def worker_reviews(request):
    """Worker reviews view with comprehensive statistics"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get all ratings for this worker with related data
    reviews = WorkerRating.objects.filter(worker=worker).select_related(
        'customer', 'appointment', 'appointment__service_subtask__subtask'
    ).order_by('-created_at')
    
    # Calculate rating statistics
    total_reviews = reviews.count()
    average_rating = worker.bayesian_average_rating()
    
    # Rating distribution (1-5 stars)
    rating_distribution = []
    for i in range(5, 0, -1):  # 5 to 1
        count = reviews.filter(rating=i).count()
        percentage = (count / total_reviews * 100) if total_reviews > 0 else 0
        rating_distribution.append({
            'stars': i,
            'count': count,
            'percentage': round(percentage, 1)
        })
    
    # Count 5-star reviews
    five_star_count = reviews.filter(rating=5).count()
    
    # Calculate response rate - Since there's no reply field, set to 0 for now
    response_rate = 0
    
    # Monthly reviews count
    current_month = timezone.now().month
    current_year = timezone.now().year
    monthly_reviews = reviews.filter(
        created_at__month=current_month,
        created_at__year=current_year
    ).count()
    
    # Prepare reviews data for template
    reviews_data = []
    for review in reviews:
        reviews_data.append({
            'id': review.id,
            'customer': {
                'name': review.customer.name,
                'profile_pic': review.customer.profile_pic
            },
            'rating': review.rating,
            'comment': review.comment,
            'reply': None,  # No reply field exists
            'replied_at': None,  # No reply field exists
            'created_at': review.created_at,
            'appointment': review.appointment,
        })
    
    context = {
        'worker': worker,
        'reviews': reviews_data,
        'total_reviews': total_reviews,
        'average_rating': round(average_rating, 1),
        'rating_distribution': rating_distribution,
        'five_star_count': five_star_count,
        'response_rate': round(response_rate, 1),
        'monthly_reviews': monthly_reviews,
        'current_section': 'reviews'
    }
    
    # AJAX response for filtering
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        rating_filter = request.GET.get('rating')
        if rating_filter and rating_filter != 'all':
            filtered_reviews = reviews.filter(rating=int(rating_filter))
            filtered_data = []
            for review in filtered_reviews:
                filtered_data.append({
                    'id': review.id,
                    'customer_name': review.customer.name,
                    'rating': review.rating,
                    'comment': review.comment,
                    'reply': None,  # No reply field exists
                    'created_at': review.created_at.strftime('%b %d, %Y'),
                    'service_name': review.appointment.service_subtask.subtask.name if review.appointment and review.appointment.service_subtask else 'General Service',
                })
            return JsonResponse({
                'reviews': filtered_data,
                'count': filtered_reviews.count()
            })
        
        return JsonResponse({
            'reviews': [{
                'id': review.id,
                'customer_name': review.customer.name,
                'rating': review.rating,
                'comment': review.comment,
                'reply': None,  # No reply field exists
                'created_at': review.created_at.strftime('%b %d, %Y'),
                'service_name': review.appointment.service_subtask.subtask.name if review.appointment and review.appointment.service_subtask else 'General Service',
            } for review in reviews],
            'average_rating': round(average_rating, 1),
            'total_reviews': total_reviews
        })
    
    return render(request, 'jobs/worker_reviews.html', context)


@require_POST
@login_required
def reply_to_review(request):
    """Handle worker replies to customer reviews"""
    try:
        review_id = request.POST.get('review_id')
        reply_message = request.POST.get('reply_message', '').strip()
        
        if not review_id or not reply_message:
            return JsonResponse({
                'success': False,
                'error': 'Review ID and reply message are required'
            })
        
        # Get the review
        review = get_object_or_404(WorkerRating, id=review_id)
        
        # Verify the worker owns this review
        if review.worker != request.user.worker:
            return JsonResponse({
                'success': False,
                'error': 'You can only reply to reviews for your services'
            })
        
        # Update the review with reply
        review.reply = reply_message
        review.replied_at = timezone.now()
        review.save()
        
        # Create notification for customer
        Notification.objects.create(
            customer=review.customer,
            notification_type='review_reply',
            title='Worker Replied to Your Review',
            message=f'{review.worker.name} has replied to your review.',
            appointment=review.appointment
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Reply posted successfully',
            'reply': reply_message,
            'replied_at': review.replied_at.strftime('%b %d, %Y')
        })
        
    except Exception as e:
        logger.error(f"Error replying to review: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        })

@login_required
def worker_analytics(request):
    """Enhanced worker analytics view with dynamic data"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get time range from request (default: 30 days)
    days = int(request.GET.get('days', 30))
    metric = request.GET.get('metric', 'count')
    
    # Calculate date range
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Get appointments in date range
    appointments = Appointment.objects.filter(
        worker=worker,
        appointment_date__range=[start_date, end_date]
    ).select_related('service_subtask', 'customer')
    
    # Calculate metrics
    total_appointments = appointments.count()
    completed_appointments = appointments.filter(status='completed').count()
    completion_rate = (completed_appointments / total_appointments * 100) if total_appointments > 0 else 0
    
    # Calculate earnings
    total_earnings = sum(
        appointment.service_subtask.price 
        for appointment in appointments.filter(status='completed') 
        if appointment.service_subtask and appointment.service_subtask.price
    )
    
    # Get reviews and satisfaction rate
    reviews = WorkerRating.objects.filter(worker=worker)
    total_reviews = reviews.count()
    satisfaction_rate = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    satisfaction_rate = (satisfaction_rate / 5) * 100  # Convert to percentage
    
    # Service distribution data
    service_stats = []
    worker_services = WorkerService.objects.filter(worker=worker)
    
    for worker_service in worker_services:
        service_appointments = appointments.filter(
            service_subtask__worker_service=worker_service
        ).count()
        
        if service_appointments > 0:
            service_stats.append({
                'name': worker_service.service.name,
                'count': service_appointments,
                'percentage': (service_appointments / total_appointments * 100) if total_appointments > 0 else 0
            })
    
    # Sort by count and get top 5
    service_stats.sort(key=lambda x: x['count'], reverse=True)
    top_services = service_stats[:5]
    
    # Appointments trend data (last 30 days by default)
    trend_data = []
    trend_labels = []
    
    for i in range(days, 0, -1):
        date = end_date - timedelta(days=i)
        date_appointments = appointments.filter(
            appointment_date__date=date.date()
        )
        
        if metric == 'count':
            value = date_appointments.count()
        else:  # revenue
            value = sum(
                appointment.service_subtask.price 
                for appointment in date_appointments.filter(status='completed')
                if appointment.service_subtask and appointment.service_subtask.price
            )
        
        trend_data.append(value)
        trend_labels.append(date.strftime('%b %d'))
    
    # Performance insights
    performance_insights = [
        {
            'title': 'Strong Performance',
            'subtitle': f'Completion rate: {completion_rate:.1f}%',
            'description': f'Your job completion rate of {completion_rate:.1f}% is above the platform average. Keep up the good work!',
            'icon': 'fas fa-trending-up',
            'icon_color': 'text-green-600',
            'icon_bg': 'bg-green-100',
            'background': 'from-green-50 to-emerald-50',
            'border': 'border-green-200'
        },
        {
            'title': 'Revenue Growth',
            'subtitle': f'₹{total_earnings:.2f} earned',
            'description': f'You have earned ₹{total_earnings:.2f} from {completed_appointments} completed appointments in the last {days} days.',
            'icon': 'fas fa-rupee-sign',
            'icon_color': 'text-blue-600',
            'icon_bg': 'bg-blue-100',
            'background': 'from-blue-50 to-indigo-50',
            'border': 'border-blue-200'
        }
    ]
    
    # Category breakdown
    category_breakdown = []
    for service in top_services:
        category_breakdown.append({
            'name': service['name'],
            'count': service['count'],
            'percentage': round(service['percentage'], 1),
            'trend': 5.2  # This would be calculated from previous period
        })
    
    context = {
        'worker': worker,
        'total_appointments': total_appointments,
        'completed_appointments': completed_appointments,
        'completion_rate': round(completion_rate, 1),
        'total_earnings': round(total_earnings, 2),
        'satisfaction_rate': round(satisfaction_rate, 1),
        'total_reviews': total_reviews,
        'total_services': len(service_stats),
        
        # Chart data
        'appointments_trend': {
            'labels': json.dumps(trend_labels),
            'data': json.dumps(trend_data)
        },
        'service_distribution': {
            'labels': json.dumps([s['name'] for s in top_services]),
            'data': json.dumps([s['count'] for s in top_services]),
            'colors': json.dumps(['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'][:len(top_services)])
        },
        
        # Additional metrics
        'peak_hours': '10 AM - 2 PM',
        'busiest_day': 'Wednesday',
        'avg_job_duration': '2.5 hours',
        
        # Dynamic insights
        'performance_insights': json.dumps(performance_insights),
        'category_breakdown': json.dumps(category_breakdown),
        
        'current_section': 'analytics'
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'appointments_trend': {
                'labels': trend_labels,
                'data': trend_data
            },
            'service_distribution': {
                'labels': [s['name'] for s in top_services],
                'data': [s['count'] for s in top_services]
            },
            'metrics': {
                'completion_rate': round(completion_rate, 1),
                'total_earnings': round(total_earnings, 2),
                'satisfaction_rate': round(satisfaction_rate, 1),
                'total_appointments': total_appointments,
                'peak_hours': '10 AM - 2 PM',
                'busiest_day': 'Wednesday',
                'avg_job_duration': '2.5 hours'
            },
            'insights': performance_insights
        })
    
    return render(request, 'jobs/worker_analytics.html', context)

@login_required
def worker_earnings(request):
    """Worker earnings view with proper calculations and JSON serialization"""
    try:
        worker = request.user.worker
    except AttributeError:
        messages.error(request, "You don't have a worker profile.")
        return redirect('worker-list')
    
    # Get completed appointments with pricing
    completed_appointments = Appointment.objects.filter(
        worker=worker,
        status='completed'
    ).select_related('service_subtask', 'customer', 'service_subtask__subtask').order_by('-appointment_date')
    
    # ✅ FIXED: Convert Decimal to float for calculations
    def decimal_to_float(value):
        """Safely convert Decimal to float, return 0 if None"""
        if value is None:
            return 0.0
        return float(value)
    
    # Calculate total earnings from completed appointments
    total_earnings = 0.0
    for appointment in completed_appointments:
        if appointment.service_subtask and appointment.service_subtask.price:
            total_earnings += decimal_to_float(appointment.service_subtask.price)
    
    # Calculate current month earnings
    current_month = timezone.now().month
    current_year = timezone.now().year
    current_month_appointments = completed_appointments.filter(
        appointment_date__month=current_month,
        appointment_date__year=current_year
    )
    
    current_month_earnings = 0.0
    for appointment in current_month_appointments:
        if appointment.service_subtask and appointment.service_subtask.price:
            current_month_earnings += decimal_to_float(appointment.service_subtask.price)
    
    # Calculate pending earnings (accepted but not completed appointments)
    pending_appointments = Appointment.objects.filter(
        worker=worker,
        status='accepted'
    ).select_related('service_subtask')
    
    pending_earnings = 0.0
    for appointment in pending_appointments:
        if appointment.service_subtask and appointment.service_subtask.price:
            pending_earnings += decimal_to_float(appointment.service_subtask.price)
    
    # Recent transactions (last 10 completed appointments)
    recent_transactions = completed_appointments[:10]
    
    # Service performance statistics
    service_stats = []
    worker_services = WorkerService.objects.filter(worker=worker)
    
    for worker_service in worker_services:
        service_appointments = completed_appointments.filter(
            service_subtask__worker_service=worker_service
        )
        
        service_earnings = 0.0
        for appointment in service_appointments:
            if appointment.service_subtask and appointment.service_subtask.price:
                service_earnings += decimal_to_float(appointment.service_subtask.price)
        
        avg_earning = service_earnings / len(service_appointments) if service_appointments else 0.0
        
        service_stats.append({
            'service_name': worker_service.service.name,
            'appointment_count': len(service_appointments),
            'total_earnings': round(service_earnings, 2),
            'average_earning': round(avg_earning, 2)
        })
    
    # Monthly earnings for chart (last 6 months)
    monthly_earnings = []
    for i in range(5, -1, -1):  # Last 6 months including current
        month = timezone.now() - timedelta(days=30*i)
        month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if i == 0:
            # Current month - get appointments from month start to now
            month_appointments = completed_appointments.filter(
                appointment_date__gte=month_start
            )
        else:
            # Previous months - get appointments for the entire month
            next_month = month_start + timedelta(days=32)
            next_month = next_month.replace(day=1)
            month_appointments = completed_appointments.filter(
                appointment_date__gte=month_start,
                appointment_date__lt=next_month
            )
        
        month_income = 0.0
        for appointment in month_appointments:
            if appointment.service_subtask and appointment.service_subtask.price:
                month_income += decimal_to_float(appointment.service_subtask.price)
        
        monthly_earnings.append({
            'month': month.strftime('%b %Y'),
            'income': round(month_income, 2)  # ✅ Convert to float and round
        })
    
    # ✅ FIXED: Convert all Decimal values to float for JSON serialization
    monthly_earnings_json = json.dumps(monthly_earnings)
    
    context = {
        'worker': worker,
        'total_earnings': round(total_earnings, 2),
        'current_month_earnings': round(current_month_earnings, 2),
        'pending_earnings': round(pending_earnings, 2),
        'completed_appointments_count': completed_appointments.count(),
        'recent_transactions': recent_transactions,
        'service_stats': service_stats,
        'monthly_earnings': monthly_earnings,
        'monthly_earnings_json': monthly_earnings_json,
        'current_section': 'earnings'
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # ✅ FIXED: Convert all Decimal values to float for AJAX response
        return JsonResponse({
            'total_earnings': round(total_earnings, 2),
            'current_month_earnings': round(current_month_earnings, 2),
            'pending_earnings': round(pending_earnings, 2),
            'monthly_earnings': monthly_earnings,
            'recent_transactions': [
                {
                    'customer_name': t.customer.name,
                    'service_name': t.service_subtask.subtask.name if t.service_subtask and t.service_subtask.subtask else 'General Service',
                    'amount': decimal_to_float(t.service_subtask.price) if t.service_subtask else 0.0,
                    'date': t.appointment_date.strftime('%b %d, %Y') if t.appointment_date else 'Date not set'
                } for t in recent_transactions
            ]
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
    """Delete a worker review and update worker ratings"""
    try:
        # Handle both POST data and JSON body
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            review_id = data.get('review_id') 
            print(f"🟢 JSON data received - review_id: {review_id}")
        else:
            review_id = request.POST.get('review_id')
            print(f"🟢 Form data received - review_id: {review_id}")
        
        if not review_id:
            print("🔴 No review_id provided")
            return JsonResponse({
                'success': False, 
                'error': 'Review ID is required'
            }, status=400)
        
        # Get the review
        try:
            review = WorkerRating.objects.get(id=review_id)
            print(f"🟢 Review found - ID: {review.id}, Worker: {review.worker.name}")
        except WorkerRating.DoesNotExist:
            print(f"🔴 Review with ID {review_id} not found")
            return JsonResponse({
                'success': False, 
                'error': 'Review not found'
            }, status=404)
        
        # ✅ CRITICAL FIX: Check if the current user is the customer who wrote this review
        if not hasattr(request.user, 'customer'):
            print("🔴 User is not a customer")
            return JsonResponse({
                'success': False, 
                'error': 'You must be a customer to delete reviews'
            }, status=403)
        
        if review.customer != request.user.customer:
            print(f"🔴 Review customer mismatch. Review customer: {review.customer.id}, Current user customer: {request.user.customer.id}")
            return JsonResponse({
                'success': False, 
                'error': 'You can only delete your own reviews'
            }, status=403)
        
        # Store worker reference before deletion for rating update
        worker = review.worker
        worker_name = worker.name
        
        print(f"🟢 Deleting review {review_id} for worker {worker_name}")
        
        # Delete the review
        review.delete()
        
        # ✅ IMPORTANT: Update worker's average rating after deletion
        worker.update_average_rating()
        
        print(f"🟢 Review {review_id} deleted successfully. Worker ratings updated.")
        
        return JsonResponse({
            'success': True, 
            'message': f'Review for {worker_name} deleted successfully'
        })
        
    except Exception as e:
        print(f"🔴 Unexpected error in delete_worker_review: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False, 
            'error': f'An error occurred: {str(e)}'
        }, status=500)
    


# Add these new views to your existing views.py

@login_required
def customer_notifications(request):
    """API endpoint to get customer notifications"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    notifications = Notification.objects.filter(
        customer=customer
    ).order_by('-created_at')[:10]
    
    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'is_read': notification.is_read,
            'time_ago': get_time_ago(notification.created_at),
            'notification_type': notification.notification_type
        })
    
    return JsonResponse({
        'notifications': notifications_data
    })

@login_required
def check_appointment_updates(request):
    """Check for appointment status updates"""
    customer = get_object_or_404(Customer, owner=request.user)
    last_checked = request.GET.get('last_checked')
    
    if last_checked:
        try:
            last_checked_date = timezone.datetime.fromisoformat(last_checked.replace('Z', '+00:00'))
            updates = Appointment.objects.filter(
                customer=customer,
                updated_at__gt=last_checked_date,
                status__in=['accepted', 'rejected', 'completed']
            ).select_related('worker')
            
            updates_data = []
            for appointment in updates:
                updates_data.append({
                    'appointment_id': appointment.id,
                    'new_status': appointment.status,
                    'worker_name': appointment.worker.name,
                    'updated_at': appointment.updated_at.isoformat()
                })
            
            return JsonResponse({
                'updates': updates_data,
                'has_updates': len(updates_data) > 0
            })
            
        except ValueError:
            pass
    
    return JsonResponse({'updates': [], 'has_updates': False})

@require_POST
@login_required
def mark_notification_read(request, notification_id):
    """Mark a single notification as read"""
    try:
        notification = Notification.objects.get(id=notification_id, customer__owner=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'success': True})
    except Notification.DoesNotExist:
        return JsonResponse({'error': 'Notification not found'}, status=404)

@require_POST
@login_required
def mark_all_notifications_read(request):
    """API endpoint to mark all notifications as read for the current user"""
    try:
        updated_count = 0
        
        # Handle both worker and customer notifications
        if hasattr(request.user, 'worker'):
            # Mark all worker notifications as read
            updated_count = Notification.objects.filter(
                worker=request.user.worker, 
                is_read=False
            ).update(is_read=True)
            
            logger.info(f"Marked {updated_count} worker notifications as read for {request.user.username}")
            
        elif hasattr(request.user, 'customer'):
            # Mark all customer notifications as read
            updated_count = Notification.objects.filter(
                customer=request.user.customer, 
                is_read=False
            ).update(is_read=True)
            
            logger.info(f"Marked {updated_count} customer notifications as read for {request.user.username}")
        else:
            logger.warning(f"User {request.user.username} has no worker or customer profile")
            return JsonResponse({
                'success': False, 
                'error': 'User profile not found'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'marked_read': updated_count
        })
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False, 
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@login_required
def get_notification_count(request):
    """Get unread notification count for customer"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            customer = request.user.customer
            count = Notification.objects.filter(
                customer=customer, 
                is_read=False
            ).count()
            
            return JsonResponse({'count': count})
        except AttributeError:
            return JsonResponse({'count': 0})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

def send_customer_completion_email(appointment):
    """Send email notification to worker when customer marks work as completed"""
    try:
        worker = appointment.worker
        customer = appointment.customer
        
        subject = f"Customer Marked Work as Completed - {customer.name}"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Work Marked as Completed by Customer</h2>
                
                <div style="background: #28a745; color: white; padding: 15px; 
                           border-radius: 8px; text-align: center; margin: 20px 0;">
                    <h3 style="margin: 0;">Customer Confirmed Completion</h3>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #007bff; margin-top: 0;">Appointment Details</h3>
                    <p><strong>Customer:</strong> {customer.name}</p>
                    <p><strong>Service:</strong> {appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service'}</p>
                    <p><strong>Date:</strong> {appointment.appointment_date.strftime('%B %d, %Y') if appointment.appointment_date else 'Not specified'}</p>
                    <p><strong>Location:</strong> {appointment.location or 'Not specified'}</p>
                </div>
                
                <div style="background: #e8f4f8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h4 style="color: #17a2b8; margin-top: 0;">Action Required</h4>
                    <p>Please log in to your dashboard to confirm the completion and finalize the appointment.</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{settings.SITE_URL}/worker/dashboard/" 
                       style="background: #007bff; color: white; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Confirm Completion
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
Work Marked as Completed by Customer

Dear {worker.name},

{customer.name} has marked your appointment as completed.

Appointment Details:
- Customer: {customer.name}
- Service: {appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service'}
- Date: {appointment.appointment_date.strftime('%B %d, %Y') if appointment.appointment_date else 'Not specified'}
- Location: {appointment.location or 'Not specified'}

Please log in to your dashboard to confirm the completion: {settings.SITE_URL}/worker/dashboard/

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
        
        logger.info(f"Customer completion email sent to worker {worker.name} ({worker.owner.email})")
        
    except Exception as e:
        logger.error(f"Failed to send customer completion email to worker {worker.name}: {str(e)}")
        # Don't raise exception to avoid breaking the main functionality

def send_worker_confirmation_email(appointment):
    """Send email notification to customer when worker confirms completion"""
    try:
        worker = appointment.worker
        customer = appointment.customer
        
        subject = f"Appointment Completed - {worker.name}"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Appointment Confirmed as Completed</h2>
                
                <div style="background: #28a745; color: white; padding: 15px; 
                           border-radius: 8px; text-align: center; margin: 20px 0;">
                    <h3 style="margin: 0;">✓ Work Completed Successfully</h3>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #007bff; margin-top: 0;">Appointment Details</h3>
                    <p><strong>Worker:</strong> {worker.name}</p>
                    <p><strong>Service:</strong> {appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service'}</p>
                    <p><strong>Date:</strong> {appointment.appointment_date.strftime('%B %d, %Y') if appointment.appointment_date else 'Not specified'}</p>
                    <p><strong>Location:</strong> {appointment.location or 'Not specified'}</p>
                </div>
                
                <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                    <h4 style="color: #856404; margin-top: 0;">Please Rate Your Experience</h4>
                    <p style="color: #856404;">
                        Your feedback helps us maintain quality service. Please take a moment to rate your experience with {worker.name}.
                    </p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{settings.SITE_URL}/rate-worker/{appointment.id}/" 
                       style="background: #ffc107; color: #333; padding: 12px 30px; 
                              text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                        ⭐ Rate & Review
                    </a>
                    <br><br>
                    <a href="{settings.SITE_URL}/customer/dashboard/" 
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
Appointment Confirmed as Completed

Dear {customer.name},

{worker.name} has confirmed that your appointment has been completed successfully.

Appointment Details:
- Worker: {worker.name}
- Service: {appointment.service_subtask.subtask.name if appointment.service_subtask else 'General Service'}
- Date: {appointment.appointment_date.strftime('%B %d, %Y') if appointment.appointment_date else 'Not specified'}
- Location: {appointment.location or 'Not specified'}

Please rate your experience: {settings.SITE_URL}/rate-worker/{appointment.id}/
View dashboard: {settings.SITE_URL}/customer/dashboard/

Thank you for using BlueCaller!

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
        
        logger.info(f"Worker confirmation email sent to customer {customer.name} ({customer.owner.email})")
        
    except Exception as e:
        logger.error(f"Failed to send worker confirmation email to customer {customer.name}: {str(e)}")

@login_required
@require_http_methods(["POST"])
def resubmit_verification(request):
    """Allow worker to resubmit for verification after rejection"""
    try:
        worker = get_object_or_404(Worker, owner=request.user)
        
        # Check if worker can resubmit (15-minute waiting period)
        if not worker.can_resubmit_verification():
            minutes_left = worker.get_resubmission_wait_time()
            return JsonResponse({
                'success': False,
                'error': f'Please wait {minutes_left} minutes before resubmitting'
            })
        
        # Reset verification status to pending
        worker.verification_status = 'pending'
        worker.verification_submitted_at = timezone.now()
        # Keep rejection reason for admin reference, but worker can't see it after resubmission
        worker.save()
        
        # Create notification for admin
        try:
            from admin_dashboard.models import AdminActivityLog
            from django.contrib.auth.models import User
            
            # Get first available admin user for logging
            admin_user = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).first()
            if admin_user:
                AdminActivityLog.objects.create(
                    admin_user=admin_user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Worker {worker.name} resubmitted for verification after rejection'
                )
        except Exception as e:
            logger.error(f"Failed to log admin activity: {e}")
        
        # Send email to admin about resubmission
        try:
            from admin_dashboard.views import send_verification_resubmission_email
            send_verification_resubmission_email(worker)
        except Exception as e:
            logger.error(f"Failed to send resubmission email: {e}")
        
        # Send notification to worker
        try:
            Notification.objects.create(
                worker=worker,
                notification_type='verification_resubmitted',
                title='Verification Resubmitted',
                message='Your profile has been resubmitted for verification. Admin will review it again shortly.',
                appointment=None
            )
        except Exception as e:
            logger.error(f"Failed to create resubmission notification: {e}")
        
        return JsonResponse({
            'success': True,
            'message': 'Verification resubmitted successfully! Admin will review your profile again.'
        })
        
    except Worker.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Worker profile not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error in resubmit_verification: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while processing your request'
        }, status=500)

# NEW: Add API endpoint to check resubmission status
@login_required
@require_http_methods(["GET"])
def check_resubmission_status(request):
    """Check if worker can resubmit and get wait time"""
    try:
        worker = get_object_or_404(Worker, owner=request.user)
        
        can_resubmit = worker.can_resubmit_verification()
        wait_time = worker.get_resubmission_wait_time()
        wait_time_display = worker.get_resubmission_wait_time_display()
        
        return JsonResponse({
            'success': True,
            'can_resubmit': can_resubmit,
            'wait_time': wait_time,
            'wait_time_display': wait_time_display,
            'verification_status': worker.verification_status,
            'rejection_reason': worker.rejection_reason if worker.verification_status == 'rejected' else None
        })
        
    except Worker.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Worker profile not found'
        }, status=404)


@login_required
def add_custom_subtask(request, worker_service_id):
    """View for workers to add custom subtasks to their services"""
    try:
        worker_service = get_object_or_404(WorkerService, id=worker_service_id, worker__owner=request.user)
    except WorkerService.DoesNotExist:
        return JsonResponse({'error': 'Worker service not found or access denied'}, status=404)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Create new subtask
            subtask = SubTask.objects.create(
                service=worker_service.service,
                name=data.get('name'),
                description=data.get('description', ''),
                detailed_description=data.get('detailed_description', ''),
                default_pricing_type=data.get('pricing_type', 'fixed'),
                duration=data.get('duration', ''),
                materials_included=data.get('materials_included', False),
                requirements=data.get('requirements', ''),
                created_by=request.user,
                is_custom=True
            )
            
            # Create pricing for this subtask
            pricing = WorkerSubTaskPricing.objects.create(
                worker_service=worker_service,
                subtask=subtask,
                pricing_type=data.get('pricing_type', 'fixed'),
                price=data.get('price', 0),
                experience_level=data.get('experience_level', 'intermediate'),
                night_shift_extra=data.get('night_shift_extra', 0),
                min_hours=data.get('min_hours', 1)
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Custom subtask added successfully',
                'subtask_id': subtask.id,
                'pricing_id': pricing.id
            })
            
        except Exception as e:
            logger.error(f"Error creating custom subtask: {str(e)}")
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def get_worker_services_for_subtask(request):
    """Get worker's services for adding custom subtasks"""
    try:
        worker = request.user.worker
        worker_services = WorkerService.objects.filter(
            worker=worker, 
            is_available=True
        ).select_related('service', 'service__category')
        
        services_data = []
        for ws in worker_services:
            services_data.append({
                'id': ws.id,
                'service_name': ws.service.name,
                'category_name': ws.service.category.name,
                'category_id': ws.service.category.id
            })
        
        return JsonResponse({'services': services_data})
        
    except Worker.DoesNotExist:
        return JsonResponse({'error': 'Worker profile not found'}, status=404)

@csrf_exempt
@require_POST
def get_worker_address(request):
    """Get human-readable address from worker coordinates using reverse geocoding"""
    try:
        worker_id = request.POST.get('worker_id')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        
        print(f"🔍 DEBUG: Processing worker {worker_id} - Lat: {latitude}, Lon: {longitude}")
        
        if not all([worker_id, latitude, longitude]):
            return JsonResponse({'error': 'Missing required parameters'}, status=400)
        
        # Convert to float
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            print(f"❌ DEBUG: Invalid coordinates for worker {worker_id}")
            return JsonResponse({'error': 'Invalid coordinates'}, status=400)
        
        # Validate coordinate ranges
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            print(f"❌ DEBUG: Coordinate out of range for worker {worker_id}")
            return JsonResponse({'error': 'Invalid coordinate ranges'}, status=400)
        
        # Check for default/invalid coordinates
        if lat == 0.0 and lon == 0.0:
            print(f"❌ DEBUG: Default coordinates (0,0) for worker {worker_id}")
            return JsonResponse({'error': 'Default coordinates not valid'}, status=400)
        
        # Use OpenStreetMap Nominatim for reverse geocoding
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': lat,
            'lon': lon,
            'format': 'json',
            'addressdetails': 1,
            'zoom': 18
        }
        
        headers = {
            'User-Agent': 'BlueCaller/1.0 (contact@bluecaller.com)'
        }
        
        print(f"🔍 DEBUG: Making API request for worker {worker_id}")
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        print(f"🔍 DEBUG: API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if we got a valid response
            if data.get('error'):
                print(f"❌ DEBUG: API returned error for worker {worker_id}: {data.get('error')}")
                return JsonResponse({'error': data.get('error')}, status=400)
            
            address = data.get('display_name', 'Address not available')
            
            # Use the helper function to format address
            address_components = data.get('address', {})
            simplified_address = format_simplified_address(address_components)
            
            print(f"✅ DEBUG: Success for worker {worker_id}: {simplified_address}")
            
            return JsonResponse({
                'success': True,
                'address': simplified_address or address,
                'full_address': address,
                'worker_id': worker_id
            })
        else:
            print(f"❌ DEBUG: API failed with status {response.status_code} for worker {worker_id}")
            return JsonResponse({
                'error': 'Geocoding service unavailable',
                'status_code': response.status_code
            }, status=500)
            
    except requests.exceptions.Timeout:
        print(f"❌ DEBUG: Timeout for worker {worker_id}")
        logger.error("Reverse geocoding request timed out")
        return JsonResponse({'error': 'Geocoding service timeout'}, status=500)
    except requests.exceptions.RequestException as e:
        print(f"❌ DEBUG: Request exception for worker {worker_id}: {str(e)}")
        logger.error(f"Reverse geocoding request failed: {str(e)}")
        return JsonResponse({'error': f'Geocoding service error: {str(e)}'}, status=500)
    except Exception as e:
        print(f"❌ DEBUG: Unexpected error for worker {worker_id}: {str(e)}")
        logger.error(f"Unexpected error in get_worker_address: {str(e)}")
        return JsonResponse({'error': f'Internal server error: {str(e)}'}, status=500)

def format_simplified_address(address_components):
    """Format a simplified address from address components"""
    parts = []
    
    # Add house number and road (street address)
    if address_components.get('house_number'):
        parts.append(address_components['house_number'])
    if address_components.get('road'):
        parts.append(address_components['road'])
    
    # Add suburb or neighbourhood
    if address_components.get('suburb'):
        parts.append(address_components['suburb'])
    elif address_components.get('neighbourhood'):
        parts.append(address_components['neighbourhood'])
    
    # Add city/town
    if address_components.get('city'):
        parts.append(address_components['city'])
    elif address_components.get('town'):
        parts.append(address_components['town'])
    elif address_components.get('village'):
        parts.append(address_components['village'])
    
    # Add state and postcode
    if address_components.get('state'):
        parts.append(address_components['state'])
    if address_components.get('postcode'):
        parts.append(address_components['postcode'])
    
    return ', '.join(parts) if parts else None


def get_location_cache_key(user_id, ip_address=None):
    """Generate a unique cache key for user location"""
    if user_id:
        return f'user_location_{user_id}'
    elif ip_address:
        # Hash IP address for privacy
        ip_hash = hashlib.md5(ip_address.encode()).hexdigest()
        return f'ip_location_{ip_hash}'
    return 'anonymous_location'

def cache_user_location(user_id, latitude, longitude, accuracy=None, source='browser', expires=3600):
    """Cache user location data"""
    cache_key = get_location_cache_key(user_id)
    location_data = {
        'latitude': latitude,
        'longitude': longitude,
        'accuracy': accuracy,
        'source': source,
        'timestamp': timezone.now().isoformat(),
        'user_id': user_id
    }
    cache.set(cache_key, location_data, expires)
    return location_data

def get_cached_user_location(user_id):
    """Get cached user location"""
    cache_key = get_location_cache_key(user_id)
    return cache.get(cache_key)

def cache_ip_location(ip_address, latitude, longitude, expires=3600):
    """Cache IP-based location data"""
    cache_key = get_location_cache_key(None, ip_address)
    location_data = {
        'latitude': latitude,
        'longitude': longitude,
        'accuracy': 5000,  # IP geolocation is less accurate
        'source': 'ip_cached',
        'timestamp': timezone.now().isoformat(),
        'ip_address': ip_address
    }
    cache.set(cache_key, location_data, expires)
    return location_data

def get_cached_ip_location(ip_address):
    """Get cached IP location"""
    cache_key = get_location_cache_key(None, ip_address)
    return cache.get(cache_key)