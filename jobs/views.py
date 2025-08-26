from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from jobs.models import Worker, Customer, Appointment, WorkerRating
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.utils.timezone import make_aware, now
from django.core.mail import send_mail
from django.db.models import Avg, QuerySet, Count
from jobs.templatetags.distance import calculate_distance
from django.db.models import F, ExpressionWrapper, FloatField
from datetime import datetime
from phonenumber_field.formfields import PhoneNumberField

def index(request):
    return HttpResponse("<h1>BlueCaller</h1>")

# Function to send appointment request email to the worker
def send_appointment_request_email(worker, appointment):
    subject = "New Appointment Request"
    message = (
        f"Dear {worker.name},\n\n"
        f"You have received a new appointment request from {appointment.customer.name}.\n"
        f"Appointment Date: {appointment.appointment_date.strftime('%Y-%m-%d %H:%M')}\n\n" # Added time formatting
        f"Please log in to your dashboard to accept or reject this request.\n"
        f"Thank you!"
    )
    from_email = "mitas.player@gmail.com" # Ensure this is configured in your settings
    recipients = [worker.owner.email] # Assuming worker.owner is the User object and has an email
    send_mail(subject, message, from_email, recipients, fail_silently=False)

# Class-based view for listing workers
class WorkerListView(ListView):
    model = Worker
    template_name = 'jobs/worker_list.html'

    def get_queryset(self):
        query = self.request.GET.get('q')  # Search query
        filter_param = self.request.GET.get('filter')  # Filter parameter

        queryset = Worker.objects.all()

        # Apply search functionality (by tagline) first
        if query:
            queryset = queryset.filter(tagline__icontains=query)

        # Filter by Rating
        if filter_param == 'rating':
            # Annotate with average rating and order by it
            queryset = queryset.annotate(
                avg_rating=Avg('ratings__rating'),
                total_ratings_count=Count('ratings')
            ).order_by('-avg_rating', '-total_ratings_count')

        # Filter by Distance
        elif filter_param == 'distance':
            customer = getattr(self.request.user, 'customer', None)
            if customer and customer.latitude and customer.longitude:
                customer_lat = float(customer.latitude)
                customer_lon = float(customer.longitude)

                # Annotate workers with calculated distance
                queryset = queryset.annotate(
                    distance=ExpressionWrapper(
                        (F('latitude') - customer_lat) ** 2 + (F('longitude') - customer_lon) ** 2,
                        output_field=FloatField()
                    )
                ).order_by('distance')

        return queryset

# In your WorkerListView
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        query = self.request.GET.get('q')
        context['q'] = query

        # Add worker appointments if the user is a worker
        if hasattr(self.request.user, 'worker'):
            appointments = Appointment.objects.filter(worker=self.request.user.worker).select_related('customer')
            context['appointments'] = appointments

        # Add rating information for each worker
        workers = context.get('worker_list', self.get_queryset())
        for worker in workers:
            # Calculate Bayesian average rating
            average_rating = worker.bayesian_average_rating()
            worker.average_rating = average_rating

            # Get total number of ratings
            worker.total_ratings = worker.ratings.count()

            # Calculate rating breakdown
            breakdown = worker.get_rating_breakdown()
            worker.rating_breakdown = breakdown

            # Calculate star representation
            full_stars = int(average_rating)
            half_star = 1 if average_rating % 1 >= 0.5 else 0
            empty_stars = 5 - (full_stars + half_star)

            worker.full_stars = range(full_stars)
            worker.half_star = half_star
            worker.empty_stars = range(empty_stars)

        context['worker_list'] = workers
        return context

# Class-based view for worker detail
# In your views.py
class WorkerDetailView(LoginRequiredMixin, DetailView):
    model = Worker
    template_name = 'jobs/worker_detail.html'

    def get_queryset(self):
        return Worker.objects.all()

    def get_object(self, queryset=None):
        worker = super().get_object(queryset)
        
        # Ensure that the user is either the owner of the worker or a customer
        if self.request.user != worker.owner and not hasattr(self.request.user, 'customer'):
            raise PermissionDenied("You do not have permission to view this worker's details.")
        return worker

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker = self.get_object()

        # Calculate ratings using Bayesian average
        average_rating = worker.bayesian_average_rating()
        total_ratings = worker.ratings.count()
        
        # Calculate star breakdown for display
        full_stars = int(average_rating)
        half_star = 1 if average_rating % 1 >= 0.5 else 0
        empty_stars = 5 - (full_stars + half_star)

        # Add to context
        context.update({
            'average_rating': average_rating,
            'total_ratings': total_ratings,
            'full_stars': range(full_stars),
            'half_star': half_star,
            'empty_stars': range(empty_stars),
            'rating_breakdown': worker.get_rating_breakdown(),
        })
        
        return context

# Class-based view for creating a worker profile
class WorkerCreateView(LoginRequiredMixin, CreateView):
    model = Worker
    fields = ['name', 'profile_pic', 'tagline', 'phone_number', 'bio', 'citizenship_image', 'certificate_file']
    success_url = reverse_lazy('worker-list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.latitude = self.request.POST.get('latitude')
        form.instance.longitude = self.request.POST.get('longitude')
        return super(WorkerCreateView, self).form_valid(form)

# Class-based view for creating a customer profile
class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer
    fields = ['name', 'profile_pic', 'phone_number']
    success_url = reverse_lazy('worker-list')

    def form_valid(self, form):    
        form.instance.latitude = self.request.POST.get('latitude')
        form.instance.longitude = self.request.POST.get('longitude')
        form.instance.owner = self.request.user
        return super(CustomerCreateView, self).form_valid(form)    

@login_required
def handle_login(request):
    # Check if user has a worker/customer account, redirect to worker-list
    if request.user.get_worker() or request.user.get_customer():
        return redirect(reverse_lazy('worker-list'))
        
    # If they don't, render a template where they can select one or the other
    return render(request, 'jobs/choose_account.html', {})

@login_required
def appoint_worker(request, worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    customer = get_object_or_404(Customer, owner=request.user)

    if request.method == "POST":
        appointment_date_str = request.POST.get("appointment_date")
        appointment_time_str = request.POST.get("appointment_time")  # Add time field

        try:
            # Combine date and time into a single datetime object
            datetime_str = f"{appointment_date_str} {appointment_time_str}"
            appointment_datetime = make_aware(datetime.strptime(datetime_str, "%Y-%m-%d %H:%M"))
            
            # Check if the selected datetime is in the future
            if appointment_datetime <= now():
                messages.error(request, "You can only book appointments for future dates/times.")
                return redirect('worker-list')

            # Check if worker is available at this time
            conflicting_appointments = Appointment.objects.filter(
                worker=worker,
                appointment_date=appointment_datetime,
                status__in=['pending', 'accepted']
            )
            
            if conflicting_appointments.exists():
                messages.error(request, "Worker already has an appointment at this time.")
                return redirect('worker-list')

            # Create new appointment
            appointment = Appointment.objects.create(
                customer=customer,
                worker=worker,
                appointment_date=appointment_datetime,
                status="pending"
            )

            # # Send email notification to worker
            # send_appointment_request_email(worker, customer, appointment)
            send_appointment_request_email(worker,appointment)
            
            messages.success(request, "Appointment request sent to worker successfully.")
            return redirect('customer_appointments')

        except ValueError as e:
            print(f"Error parsing datetime: {e}")  # For debugging
            messages.error(request, "Invalid appointment date or time format. Please use the correct format.")
        except Exception as e:
            print(f"Unexpected error: {e}")  # For debugging
            messages.error(request, "An error occurred while processing your request.")
    
    # For GET requests or if there's an error
    return render(request, 'jobs/appointment_request.html', {
        'worker': worker,
        'min_date': datetime.now().strftime('%Y-%m-%d'),  # Set min date for date picker
    })

from .models import Appointment

from django.views.decorators.http import require_POST

@login_required
def customer_appointments(request):
    customer = get_object_or_404(Customer, owner=request.user)
    appointments = Appointment.objects.filter(customer=customer).order_by('-appointment_date')
    return render(request, 'jobs/customer_appointments.html', {'appointments': appointments})


@require_POST
@login_required
def request_new_worker(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)

    # Optionally mark appointment as handled or archived
    appointment.status = 'archived'
    appointment.save()

    # Redirect to appointment form or worker list page
    return redirect('create_appointment')  # Update this to your actual appointment form URL name

@login_required
def worker_appointments(request,worker_id):
    worker = get_object_or_404(Worker, id=worker_id)
    appointments = Appointment.objects.filter(worker=worker).order_by('-appointment_date')
    return render(request, 'jobs/worker_appointments.html', {'appointments': appointments})

@login_required
def accept_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Ensure only the assigned worker can accept the appointment
    if appointment.worker.owner != request.user:
        messages.error(request, "You are not authorized to accept this appointment.")
        return redirect('worker_appointments', worker_id=appointment.worker.id)  # Added worker_id

    if request.method == 'POST':
        if appointment.status == 'pending':
            appointment.status = 'accepted'
            appointment.save()
            messages.success(request, "Appointment accepted successfully.")
        else:
            messages.warning(request, "This appointment is not in a pending state.")
    return redirect('worker_appointments', worker_id=appointment.worker.id)  # Added worker_id

@login_required
def reject_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Ensure only the assigned worker can reject the appointment
    if appointment.worker.owner != request.user:
        messages.error(request, "You are not authorized to reject this appointment.")
        return redirect('worker_appointments')

    if request.method == 'POST':
        if appointment.status == 'pending':
            appointment.status = 'rejected'
            appointment.save()
            messages.info(request, "Appointment rejected.")
            # Optionally send email to customer about rejection
        else:
            messages.warning(request, "This appointment is not in a pending state.")
    return redirect('worker_appointments')


@login_required
def delete_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Ensure that only the customer who booked or the worker associated can delete it
    if request.user == appointment.customer.owner or request.user == appointment.worker.owner:
        worker_id = appointment.worker.id  # capture before deleting
        appointment.delete()
        messages.success(request, "Appointment deleted successfully.")

        if request.user == appointment.customer.owner:
            return redirect('customer_appointments')
        elif request.user == appointment.worker.owner:
            return redirect('worker_appointments', worker_id=worker_id)  # ✅ pass worker_id
    else:
        messages.error(request, "You are not authorized to delete this appointment.")
        
    return redirect('worker_appointments', worker_id=worker_id)
 # Fallback redirect

@login_required
def complete_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)

    # Ensure only the assigned worker can mark as completed
    if appointment.worker.owner != request.user:
        messages.error(request, "You are not allowed to complete this appointment.")
        return redirect('worker_appointments')

    if request.method == 'POST':
        if appointment.status == 'accepted': # Only accepted appointments can be completed
            appointment.status = 'completed'
            appointment.save()
            messages.success(request, "Appointment marked as completed.")
        else:
            messages.warning(request, "This appointment cannot be marked as completed (status not accepted).")

    return redirect('worker_appointments', worker_id=appointment.worker.id)


@login_required
def rate_worker(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id)
    
    # Ensure the user is the customer who made the appointment
    if request.user.customer != appointment.customer:
        messages.error(request, "You can only rate workers for your own appointments.")
        return redirect('worker-list')
    
    # Ensure the appointment is completed
    if appointment.status != 'completed':
        messages.error(request, "You can only rate workers after the appointment is completed.")
        return redirect('worker-list')
    
    if request.method == 'POST':
        rating_value = request.POST.get('rating')
        comment = request.POST.get('comment', '').strip()
        
        if not rating_value:
            messages.error(request, "Please provide a rating.")
            return redirect('worker-detail', pk=appointment.worker.id)
        
        try:
            rating_value = int(rating_value)
            if not 1 <= rating_value <= 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError:
            messages.error(request, "Invalid rating value.")
            return redirect('worker-detail', pk=appointment.worker.id)
        
        # Check if rating already exists
        existing_rating = WorkerRating.objects.filter(
            worker=appointment.worker,
            appointment=appointment,
            customer=request.user.customer
        ).first()
        
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
        
        # Update worker's average rating
        appointment.worker.update_average_rating()
        
        return redirect('worker-detail', pk=appointment.worker.id)
    
    # For GET requests, show the rating form
    return render(request, 'jobs/rate_worker.html', {
        'appointment': appointment,
        'worker': appointment.worker
    })






from .models import Service

def service_list(request, category=None):
    if category:
        services = Service.objects.filter(category=category, is_available=True)
    else:
        services = Service.objects.filter(is_available=True)
    return render(request, 'app/services.html', {'services': services, 'category': category})

def service_filtered(request, category, filter_type):
    services = Service.objects.filter(category=category, is_available=True)

    if filter_type == 'below':
        services = services.filter(hourly_rate__lt=500)
    elif filter_type == 'above':
        services = services.filter(hourly_rate__gte=500)
    elif filter_type == 'low':
        services = services.order_by('hourly_rate')
    elif filter_type == 'high':
        services = services.order_by('-hourly_rate')

    return render(request, 'app/services.html', {'services': services, 'category': category})