from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta
import json

from jobs.models import (
    Worker, Customer, Appointment, WorkerRating, Service, 
    WorkerService, WorkerSubTaskPricing, ServiceCategory, SubTask,
    Notification, FavoriteWorker
)
from .models import AdminDashboardSettings, AdminActivityLog

# Custom Admin Site
class BlueCollarAdminSite(admin.AdminSite):
    site_header = "BlueCollar Administration"
    site_title = "BlueCollar Admin Portal"
    index_title = "Dashboard Overview"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='admin_dashboard'),
            path('analytics/', self.admin_view(self.analytics_view), name='admin_analytics'),
            path('reports/', self.admin_view(self.reports_view), name='admin_reports'),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request):
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
        
        # Revenue statistics (simplified)
        completed_appointments = Appointment.objects.filter(status='completed')
        total_revenue = sum(app.total_price or 0 for app in completed_appointments if app.total_price)
        
        # Chart data - appointments by status
        status_counts = Appointment.objects.values('status').annotate(count=Count('id'))
        
        context = {
            **self.each_context(request),
            'total_workers': total_workers,
            'total_customers': total_customers,
            'total_appointments': total_appointments,
            'total_services': total_services,
            'pending_workers': pending_workers,
            'pending_appointments': pending_appointments,
            'total_revenue': total_revenue,
            'recent_appointments': recent_appointments,
            'status_counts': list(status_counts),
        }
        return render(request, 'admin_dashboard/dashboard.html', context)
    
    def analytics_view(self, request):
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
        ).extra({'date': "date(created_at)"}).values('date').annotate(count=Count('id'))
        
        customer_registrations = Customer.objects.filter(
            created_at__range=[start_date, end_date]
        ).extra({'date': "date(created_at)"}).values('date').annotate(count=Count('id'))
        
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
        )
        
        context = {
            **self.each_context(request),
            'period': period,
            'worker_registrations': list(worker_registrations),
            'customer_registrations': list(customer_registrations),
            'appointment_stats': list(appointment_stats),
            'revenue_data': list(revenue_data),
        }
        return render(request, 'admin_dashboard/analytics.html', context)
    
    def reports_view(self, request):
        # Generate various reports
        top_workers = Worker.objects.annotate(
            total_appointments=Count('worker_appointments'),
            avg_rating=Avg('ratings__rating')
        ).order_by('-total_appointments')[:10]
        
        popular_services = Service.objects.annotate(
            appointment_count=Count('subtasks__workersubtaskpricing__appointment')
        ).order_by('-appointment_count')[:10]
        
        active_customers = Customer.objects.annotate(
            appointment_count=Count('customer_appointments')
        ).order_by('-appointment_count')[:10]
        
        context = {
            **self.each_context(request),
            'top_workers': top_workers,
            'popular_services': popular_services,
            'active_customers': active_customers,
        }
        return render(request, 'admin_dashboard/reports.html', context)

# Create custom admin site instance
admin_site = BlueCollarAdminSite(name='bluecollar_admin')

# Custom ModelAdmin classes with enhanced features
@admin.register(Worker, site=admin_site)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'verified', 'average_rating', 'rating_count', 'is_available', 'created_at']
    list_filter = ['verified', 'is_available', 'shift', 'created_at']
    search_fields = ['name', 'phone_number', 'tagline']
    readonly_fields = ['average_rating', 'rating_count', 'created_at', 'updated_at']
    actions = ['verify_workers', 'unverify_workers', 'toggle_availability']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'phone_number', 'tagline', 'bio', 'profile_pic')
        }),
        ('Verification & Status', {
            'fields': ('verified', 'is_available', 'shift', 'average_rating', 'rating_count')
        }),
        ('Location Information', {
            'fields': ('latitude', 'longitude', 'location_address', 'location_updated_at')
        }),
        ('Documents', {
            'fields': ('citizenship_image', 'certificate_file')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def verify_workers(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f'{updated} workers verified successfully.')
    verify_workers.short_description = "Verify selected workers"
    
    def unverify_workers(self, request, queryset):
        updated = queryset.update(verified=False)
        self.message_user(request, f'{updated} workers unverified.')
    unverify_workers.short_description = "Unverify selected workers"
    
    def toggle_availability(self, request, queryset):
        for worker in queryset:
            worker.is_available = not worker.is_available
            worker.save()
        self.message_user(request, f'Availability toggled for {queryset.count()} workers.')
    toggle_availability.short_description = "Toggle availability"

@admin.register(Customer, site=admin_site)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'created_at', 'appointment_count']
    list_filter = ['created_at']
    search_fields = ['name', 'phone_number']
    readonly_fields = ['created_at', 'updated_at']
    
    def appointment_count(self, obj):
        return obj.customer_appointments.count()
    appointment_count.short_description = 'Appointments'

@admin.register(Appointment, site=admin_site)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'worker', 'appointment_date', 'status', 'total_price', 'created_at']
    list_filter = ['status', 'shift_type', 'appointment_date', 'created_at']
    search_fields = ['customer__name', 'worker__name', 'location']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['mark_as_completed', 'mark_as_cancelled', 'send_reminders']
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('customer', 'worker', 'service_subtask', 'appointment_date', 'status')
        }),
        ('Location & Instructions', {
            'fields': ('location', 'special_instructions', 'reason')
        }),
        ('Pricing & Completion', {
            'fields': ('total_price', 'quantity', 'is_night_shift', 'customer_completed', 'worker_completed')
        }),
        ('Customer Location', {
            'fields': ('customer_latitude', 'customer_longitude'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} appointments marked as completed.')
    mark_as_completed.short_description = "Mark selected as completed"
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} appointments marked as cancelled.')
    mark_as_cancelled.short_description = "Mark selected as cancelled"

@admin.register(WorkerRating, site=admin_site)
class WorkerRatingAdmin(admin.ModelAdmin):
    list_display = ['worker', 'customer', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['worker__name', 'customer__name', 'comment']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Service, site=admin_site)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'base_pricing_type', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'base_pricing_type']
    search_fields = ['name', 'description']
    list_editable = ['is_active']

@admin.register(ServiceCategory, site=admin_site)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'service_count']  # Remove 'created_at' since it doesn't exist
    search_fields = ['name', 'description']
    
    def service_count(self, obj):
        return obj.services.count()
    service_count.short_description = 'Services'
    
@admin.register(SubTask, site=admin_site)
class SubTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'service', 'default_pricing_type', 'special_offer', 'created_at']
    list_filter = ['service', 'special_offer', 'default_pricing_type']
    search_fields = ['name', 'description']
    list_editable = ['special_offer']

@admin.register(WorkerService, site=admin_site)
class WorkerServiceAdmin(admin.ModelAdmin):
    list_display = ['worker', 'service', 'is_available', 'created_at']
    list_filter = ['is_available', 'service']
    search_fields = ['worker__name', 'service__name']

@admin.register(WorkerSubTaskPricing, site=admin_site)
class WorkerSubTaskPricingAdmin(admin.ModelAdmin):
    list_display = ['worker_service', 'subtask', 'pricing_type', 'price', 'experience_level']
    list_filter = ['pricing_type', 'experience_level']
    search_fields = ['worker_service__worker__name', 'subtask__name']

@admin.register(Notification, site=admin_site)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message']
    readonly_fields = ['created_at']
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f'{updated} notifications marked as read.')
    mark_as_read.short_description = "Mark selected as read"
    
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f'{updated} notifications marked as unread.')
    mark_as_unread.short_description = "Mark selected as unread"

@admin.register(FavoriteWorker, site=admin_site)
class FavoriteWorkerAdmin(admin.ModelAdmin):
    list_display = ['customer', 'worker', 'created_at']
    list_filter = ['created_at']
    search_fields = ['customer__name', 'worker__name']

# Register User and Group from Django auth
admin_site.register(User)
admin_site.register(Group)

# Register admin dashboard models
@admin.register(AdminDashboardSettings, site=admin_site)
class AdminDashboardSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not AdminDashboardSettings.objects.exists()

@admin.register(AdminActivityLog, site=admin_site)
class AdminActivityLogAdmin(admin.ModelAdmin):
    list_display = ['admin_user', 'action', 'model_name', 'object_id', 'created_at']
    list_filter = ['action', 'model_name', 'created_at']
    search_fields = ['admin_user__username', 'description']
    readonly_fields = ['created_at']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser