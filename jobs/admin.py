from django.contrib import admin
from django.http import HttpRequest
from .models import Worker, Customer, Appointment, WorkerRating, Service, ServiceCategory, SubTask, WorkerService, WorkerSubTaskPricing, Notification

def verify_workers(modeladmin: admin.ModelAdmin, request: HttpRequest, queryset):
    queryset.update(verified=True)

@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'tagline', 'verified', 'average_rating']
    list_filter = ['verified', 'shift']
    search_fields = ['name', 'tagline', 'phone_number']
    actions = [verify_workers]

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number']
    search_fields = ['name', 'phone_number']

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['customer', 'worker', 'appointment_date', 'status', 'shift_type']
    list_filter = ['status', 'shift_type', 'appointment_date']
    search_fields = ['customer__name', 'worker__name']

@admin.register(WorkerRating)
class WorkerRatingAdmin(admin.ModelAdmin):
    list_display = ['worker', 'customer', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['worker__name', 'customer__name']

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'base_pricing_type']
    list_filter = ['category', 'base_pricing_type']
    search_fields = ['name', 'description']

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']

@admin.register(SubTask)
class SubTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'service', 'default_pricing_type']
    list_filter = ['service', 'default_pricing_type']
    search_fields = ['name', 'description']

@admin.register(WorkerService)
class WorkerServiceAdmin(admin.ModelAdmin):
    list_display = ['worker', 'service', 'is_available']
    list_filter = ['is_available', 'service']
    search_fields = ['worker__name', 'service__name']

@admin.register(WorkerSubTaskPricing)
class WorkerSubTaskPricingAdmin(admin.ModelAdmin):
    list_display = ['worker_service', 'subtask', 'pricing_type', 'price', 'experience_level']
    list_filter = ['pricing_type', 'experience_level']
    search_fields = ['worker_service__worker__name', 'subtask__name']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message']