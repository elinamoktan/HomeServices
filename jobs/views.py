from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from jobs.models import Worker, Customer, Appointment, WorkerRating, Service, WorkerService, WorkerSubTaskPricing
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
import json
from datetime import date
from math import radians, sin, cos, sqrt, asin
from django.core.paginator import Paginator
from django.template.defaultfilters import register
from django.contrib.auth import logout
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

# Configure logging for email failures
logger = logging.getLogger(__name__)

def index(request):
    return HttpResponse("<h1>BlueCaller</h1>")

# Enhanced email functions with better formatting and error handling
def send_appointment_request_email(worker, appointment):
    """Send email notification to worker when customer requests an appointment"""
    try:
        subject = f"New Appointment Request - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}"
        
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
        raise

def send_appointment_status_email(appointment, status):
    """Send email notification to customer when appointment status changes"""
    try:
        customer = appointment.customer
        worker = appointment.worker
        
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

# Class-based view for listing workers
class WorkerListView(ListView):
    model = Worker
    template_name = 'jobs/worker_list.html'

    def get_queryset(self):
        query = self.request.GET.get('q')
        filter_param = self.request.GET.get('filter')
        service_filter = self.request.GET.get('service')

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
        
        # Add services for filtering
        context['all_services'] = Service.objects.all()
        context['selected_service'] = service_filter

        # Get the base queryset
        workers_qs = context.get('object_list', self.get_queryset())

        # Get customer info if available
        customer = getattr(self.request.user, 'customer', None)
        cust_lat = None
        cust_lon = None
        
        if customer and customer.latitude and customer.longitude:
            try:
                cust_lat = float(customer.latitude)
                cust_lon = float(customer.longitude)
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
        })
        
        return context

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

@login_required
def handle_login(request):
    # If user is already authenticated, redirect based on their profile type
    if request.user.is_authenticated:
        # Try to detect worker profile
        try:
            worker = request.user.worker
            return redirect('worker_dashboard')  # Redirect workers to their dashboard
        except Worker.DoesNotExist:
            pass

        # Try to detect customer profile
        try:
            customer = request.user.customer
            return redirect('worker-list')  # Redirect customers to worker list
        except Customer.DoesNotExist:
            pass

        # If neither exists, show account setup screen
        return render(request, 'jobs/choose_account.html', {})
    
    # If user is not authenticated, redirect to login page
    return redirect('login')  # Assuming you have a login URL named 'login'

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
    
    return render(request, 'jobs/customer_appointments.html', context)

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
    
    # Get all appointments for this worker, ordered by date
    appointments = Appointment.objects.filter(worker=worker).order_by('-appointment_date')
    
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
    
    if request.user.customer != appointment.customer:
        messages.error(request, "You can only rate workers for your own appointments.")
        return redirect('worker-list')
    
    if appointment.status != 'completed':
        messages.error(request, "You can only rate workers after the appointment is completed.")
        return redirect('worker-list')
    
    if request.method == 'POST':
        rating_value = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()
        
        if not rating_value:
            messages.error(request, "Please provide a rating.")
            return redirect('customer_appointments') # Redirect to the appointments list
        
        try:
            rating_value = int(rating_value)
            if not 1 <= rating_value <= 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError:
            messages.error(request, "Invalid rating value.")
            return redirect('customer_appointments') # Redirect to the appointments list
        
        existing_rating = WorkerRating.objects.filter(
            worker=appointment.worker,
            appointment=appointment,
            customer=request.user.customer
        ).first()
        
        if existing_rating:
            existing_rating.rating = rating_value
            existing_rating.comment = comment
            existing_rating.save()
            messages.success(request, "Your rating has been updated.")
        else:
            WorkerRating.objects.create(
                worker=appointment.worker,
                appointment=appointment,
                customer=request.user.customer,
                rating=rating_value,
                comment=comment
            )
            messages.success(request, "Thank you for rating the worker!")
        
        appointment.worker.update_average_rating()
        
        # After a rating is submitted, mark this appointment as rated in the session
        request.session[f'rated_appointment_{appointment.id}'] = True
        
        return redirect('customer_appointments')
    
    return render(request, 'jobs/rate_worker.html', {
        'appointment': appointment,
        'worker': appointment.worker
    })

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
    """Customer dashboard view with stats and appointments"""
    customer = get_object_or_404(Customer, owner=request.user)
    
    # Get appointments
    appointments_list = Appointment.objects.filter(customer=customer).order_by('-appointment_date')
    
    # Add rating status to each appointment (this is done in Python, not in the query)
    for appointment in appointments_list:
        appointment.has_rated = WorkerRating.objects.filter(
            appointment=appointment,
            customer=customer
        ).exists()
    
    # Count rated appointments
    rated_appointments_count = sum(1 for appointment in appointments_list if appointment.has_rated)
    
    # Count appointments by status
    pending_count = appointments_list.filter(status='pending').count()
    accepted_count = appointments_list.filter(status='accepted').count()
    completed_count = appointments_list.filter(status='completed').count()
    
    # Pagination
    paginator = Paginator(appointments_list, 10)  # Show 10 appointments per page
    page = request.GET.get('page')
    appointments = paginator.get_page(page)
    
    context = {
        'appointments': appointments,
        'rated_appointments_count': rated_appointments_count,
        'pending_count': pending_count,
        'accepted_count': accepted_count,
        'completed_count': completed_count,
        'total_appointments': appointments_list.count(),
        'current_page': 'dashboard'
    }
    
    return render(request, 'jobs/customer_dashboard.html', context)


def custom_logout(request):
    if request.method == 'POST':
        logout(request)
        return redirect('landing-page')
    # If someone tries to access via GET, just redirect them
    return redirect('landing-page')

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