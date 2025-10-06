from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from datetime import datetime, timedelta
import json
import csv

from jobs.models import (
    Worker, Customer, Appointment, WorkerRating, Service, 
    WorkerService, WorkerSubTaskPricing, ServiceCategory, SubTask,
    Notification, FavoriteWorker
)
from .models import AdminDashboardSettings, AdminActivityLog

def admin_required(user):
    """Check if user is admin/staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@login_required
@user_passes_test(admin_required)
def admin_dashboard(request):
    """Main admin dashboard view"""
    # Calculate statistics
    total_workers = Worker.objects.count()
    total_customers = Customer.objects.count()
    total_appointments = Appointment.objects.count()
    total_services = Service.objects.count()
    
    # Recent appointments
    recent_appointments = Appointment.objects.select_related('worker', 'customer').order_by('-created_at')[:10]
    
    # Pending approvals
    pending_workers = Worker.objects.filter(verified=False).count()
    pending_appointments = Appointment.objects.filter(status='pending').count()
    
    # Revenue statistics
    completed_appointments = Appointment.objects.filter(status='completed')
    total_revenue = sum(app.total_price or 0 for app in completed_appointments if app.total_price)
    
    # Chart data - appointments by status
    status_counts = list(Appointment.objects.values('status').annotate(count=Count('id')))
    
    context = {
        'total_workers': total_workers,
        'total_customers': total_customers,
        'total_appointments': total_appointments,
        'total_services': total_services,
        'pending_workers': pending_workers,
        'pending_appointments': pending_appointments,
        'total_revenue': total_revenue,
        'recent_appointments': recent_appointments,
        'status_counts': status_counts,
    }
    return render(request, 'admin_dashboard/dashboard.html', context)

@login_required
@user_passes_test(admin_required)
def worker_management(request):
    """Worker management view"""
    workers = Worker.objects.select_related('owner').annotate(
        appointment_count=Count('worker_appointments'),
        avg_rating=Avg('ratings__rating')
    ).order_by('-created_at')
    
    # Calculate statistics
    total_workers = workers.count()
    verified_workers = workers.filter(verified=True).count()
    unverified_workers = workers.filter(verified=False).count()
    available_workers = workers.filter(is_available=True).count()
    unavailable_workers = workers.filter(is_available=False).count()
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter == 'verified':
        workers = workers.filter(verified=True)
    elif status_filter == 'unverified':
        workers = workers.filter(verified=False)
    elif status_filter == 'available':
        workers = workers.filter(is_available=True)
    elif status_filter == 'unavailable':
        workers = workers.filter(is_available=False)
    
    # Pagination
    paginator = Paginator(workers, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'workers': page_obj,
        'current_filter': status_filter,
        'total_workers': total_workers,
        'verified_workers': verified_workers,
        'unverified_workers': unverified_workers,
        'available_workers': available_workers,
        'unavailable_workers': unavailable_workers,
    }
    return render(request, 'admin_dashboard/worker_management.html', context)

@login_required
@user_passes_test(admin_required)
def customer_management(request):
    """Customer management view"""
    customers = Customer.objects.select_related('owner').annotate(
        appointment_count=Count('customer_appointments'),
        total_spent=Sum('customer_appointments__total_price')
    ).order_by('-created_at')
    
    # Calculate stats
    total_customers = customers.count()
    active_customers = customers.filter(appointment_count__gt=0).count()
    total_revenue = customers.aggregate(total=Sum('total_spent'))['total'] or 0
    avg_appointments = customers.aggregate(avg=Avg('appointment_count'))['avg'] or 0
    
    context = {
        'customers': customers,
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_revenue': total_revenue,
        'avg_appointments': round(avg_appointments, 1),
    }
    return render(request, 'admin_dashboard/customer_management.html', context)

@login_required
@user_passes_test(admin_required)
def appointment_management(request):
    """Appointment management view"""
    appointments = Appointment.objects.select_related(
        'customer', 'worker', 'service_subtask'
    ).order_by('-created_at')
    
    # Calculate stats
    total_appointments = appointments.count()
    pending_appointments = appointments.filter(status='pending').count()
    completed_appointments = appointments.filter(status='completed').count()
    total_revenue = appointments.filter(status='completed').aggregate(
        total=Sum('total_price')
    )['total'] or 0
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter:
        appointments = appointments.filter(status=status_filter)
    
    context = {
        'appointments': appointments,
        'current_filter': status_filter,
        'total_appointments': total_appointments,
        'pending_appointments': pending_appointments,
        'completed_appointments': completed_appointments,
        'total_revenue': total_revenue,
    }
    return render(request, 'admin_dashboard/appointment_management.html', context)

@login_required
@user_passes_test(admin_required)
def service_management(request):
    """Service management view - safe version"""
    # Get services with basic information
    services = Service.objects.select_related('category').order_by('-created_at')
    
    # Get worker counts using the correct related name
    # Let's try different possible related names
    try:
        # Try to get worker counts - we'll handle any errors
        from django.db.models import Count
        services_with_counts = Service.objects.annotate(
            worker_count=Count('workerservice')
        )
        worker_count_dict = {s.id: s.worker_count for s in services_with_counts}
    except Exception as e:
        print(f"Error getting worker counts: {e}")
        # If that fails, use a safe fallback
        worker_count_dict = {}
    
    # Add counts to services
    for service in services:
        service.worker_count = worker_count_dict.get(service.id, 0)
        service.subtask_count = service.subtasks.count()  # This should work
    
    categories = ServiceCategory.objects.annotate(
        service_count=Count('services')
    ).order_by('name')
    
    # Calculate statistics
    total_services = services.count()
    active_services = services.filter(is_active=True).count()
    inactive_services = services.filter(is_active=False).count()
    
    context = {
        'services': services,
        'categories': categories,
        'total_services': total_services,
        'active_services': active_services,
        'inactive_services': inactive_services,
    }
    return render(request, 'admin_dashboard/service_management.html', context)

@login_required
@user_passes_test(admin_required)
def admin_analytics(request):
    """Advanced analytics view"""
    # Time period filter
    period = request.GET.get('period', '7')
    end_date = timezone.now()
    
    if period == '7':
        start_date = end_date - timedelta(days=7)
    elif period == '30':
        start_date = end_date - timedelta(days=30)
    else:  # 90 days
        start_date = end_date - timedelta(days=90)
    
    # Registration analytics
    worker_registrations = Worker.objects.filter(
        created_at__range=[start_date, end_date]
    ).extra({'date': "date(created_at)"}).values('date').annotate(count=Count('id')).order_by('date')
    
    customer_registrations = Customer.objects.filter(
        created_at__range=[start_date, end_date]
    ).extra({'date': "date(created_at)"}).values('date').annotate(count=Count('id')).order_by('date')
    
    # Appointment analytics
    appointment_stats = Appointment.objects.filter(
        created_at__range=[start_date, end_date]
    ).values('status').annotate(count=Count('id'))
    
    # Revenue analytics
    revenue_data = Appointment.objects.filter(
        status='completed',
        created_at__range=[start_date, end_date]
    ).extra({'date': "date(created_at)"}).values('date').annotate(
        revenue=Sum('total_price')
    ).order_by('date')
    
    context = {
        'period': period,
        'worker_registrations': list(worker_registrations),
        'customer_registrations': list(customer_registrations),
        'appointment_stats': list(appointment_stats),
        'revenue_data': list(revenue_data),
    }
    return render(request, 'admin_dashboard/analytics.html', context)

@login_required
@user_passes_test(admin_required)
def admin_reports(request):
    """Comprehensive reports view"""
    # Top performers
    top_workers = Worker.objects.annotate(
        total_appointments=Count('worker_appointments'),
        avg_rating=Avg('ratings__rating'),
        completed_appointments=Count('worker_appointments', filter=Q(worker_appointments__status='completed'))
    ).order_by('-total_appointments')[:10]
    
    # Popular services
    popular_services = Service.objects.annotate(
        appointment_count=Count('subtasks__workersubtaskpricing__appointment')
    ).order_by('-appointment_count')[:10]
    
    # Active customers
    active_customers = Customer.objects.annotate(
        appointment_count=Count('customer_appointments'),
        total_spent=Sum('customer_appointments__total_price')
    ).order_by('-appointment_count')[:10]
    
    context = {
        'top_workers': top_workers,
        'popular_services': popular_services,
        'active_customers': active_customers,
    }
    return render(request, 'admin_dashboard/reports.html', context)

@login_required
@user_passes_test(admin_required)
def bulk_actions(request):
    """Handle bulk actions from admin"""
    if request.method == 'POST':
        action = request.POST.get('action')
        selected_ids = request.POST.getlist('selected_ids')
        
        if action == 'verify_workers':
            Worker.objects.filter(id__in=selected_ids).update(verified=True)
            messages.success(request, f'{len(selected_ids)} workers verified successfully.')
        
        elif action == 'unverify_workers':
            Worker.objects.filter(id__in=selected_ids).update(verified=False)
            messages.success(request, f'{len(selected_ids)} workers unverified.')
        
        elif action == 'activate_services':
            Service.objects.filter(id__in=selected_ids).update(is_active=True)
            messages.success(request, f'{len(selected_ids)} services activated.')
        
        elif action == 'deactivate_services':
            Service.objects.filter(id__in=selected_ids).update(is_active=False)
            messages.success(request, f'{len(selected_ids)} services deactivated.')
        
        elif action == 'complete_appointments':
            Appointment.objects.filter(id__in=selected_ids).update(status='completed')
            messages.success(request, f'{len(selected_ids)} appointments marked as completed.')
        
        elif action == 'cancel_appointments':
            Appointment.objects.filter(id__in=selected_ids).update(status='cancelled')
            messages.success(request, f'{len(selected_ids)} appointments cancelled.')
    
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard:dashboard'))

@login_required
@user_passes_test(admin_required)
def quick_stats_api(request):
    """API endpoint for quick stats (AJAX)"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        today = timezone.now().date()
        
        # Today's stats
        today_appointments = Appointment.objects.filter(
            created_at__date=today
        ).count()
        
        today_registrations = Worker.objects.filter(
            created_at__date=today
        ).count() + Customer.objects.filter(
            created_at__date=today
        ).count()
        
        today_revenue = Appointment.objects.filter(
            status='completed',
            created_at__date=today
        ).aggregate(Sum('total_price'))['total_price__sum'] or 0
        
        data = {
            'today_appointments': today_appointments,
            'today_registrations': today_registrations,
            'today_revenue': float(today_revenue),
        }
        
        return JsonResponse(data)
    
    return JsonResponse({'error': 'Invalid request'})

@login_required
@user_passes_test(admin_required)
def export_data(request, model_type):
    """Export data to various formats"""
    from django.http import HttpResponse
    import csv
    import json
    
    format_type = request.GET.get('format', 'csv')
    
    if model_type == 'workers':
        data = Worker.objects.all().values('name', 'phone_number', 'verified', 'average_rating', 'created_at')
        filename = 'workers_export'
    
    elif model_type == 'customers':
        data = Customer.objects.all().values('name', 'phone_number', 'created_at')
        filename = 'customers_export'
    
    elif model_type == 'appointments':
        data = Appointment.objects.all().values(
            'customer__name', 'worker__name', 'appointment_date', 'status', 'total_price'
        )
        filename = 'appointments_export'
    
    else:
        messages.error(request, 'Invalid export type')
        return redirect('admin_dashboard:dashboard')
    
    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        if data:
            # Write headers
            writer.writerow(data[0].keys())
            # Write data
            for item in data:
                writer.writerow(item.values())
        
        return response
    
    elif format_type == 'json':
        response = HttpResponse(content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}.json"'
        response.write(json.dumps(list(data), indent=2, default=str))
        return response
    
    messages.error(request, 'Invalid format type')
    return redirect('admin_dashboard:dashboard')