from django.contrib import admin
from django.http import HttpRequest
from django.utils.html import format_html
from .models import Worker, Customer, Appointment, WorkerRating, Service, ServiceCategory, SubTask, WorkerService, WorkerSubTaskPricing, Notification

def verify_workers(modeladmin: admin.ModelAdmin, request: HttpRequest, queryset):
    queryset.update(verified=True)
verify_workers.short_description = "Verify selected workers"

@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'phone_number', 
        'tagline', 
        'verified', 
        'average_rating',
        'display_location',
        'display_previous_location',
        'location_updated_at',
        'location_source'
    ]
    list_filter = ['verified', 'shift', 'location_source']
    search_fields = ['name', 'tagline', 'phone_number']
    actions = [verify_workers]
    
    readonly_fields = [
        'location_updated_at', 
        'location_source', 
        'location_accuracy', 
        'average_rating', 
        'rating_count', 
        'previous_location_updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'profile_pic', 'tagline', 'phone_number', 'bio')
        }),
        ('Current Location Information', {
            'fields': ('latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'),
            'description': 'Location is automatically updated when worker logs in or moves'
        }),
        ('Previous Location Information', {
            'fields': ('previous_latitude', 'previous_longitude', 'previous_location_address', 'previous_location_updated_at'),
            'description': 'Automatically stores the previous location when location is updated',
            'classes': ('collapse',)
        }),
        ('Verification & Documents', {
            'fields': ('verified', 'citizenship_image', 'certificate_file')
        }),
        ('Work Details', {
            'fields': ('shift', 'average_rating', 'rating_count')
        }),
    )
    
    def display_location(self, obj):
        """Display formatted current location with link to Google Maps"""
        if obj.latitude and obj.longitude:
            try:
                lat_str = f"{float(obj.latitude):.6f}"
                lon_str = f"{float(obj.longitude):.6f}"
                map_url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
                
                return format_html(
                    '<a href="{}" target="_blank" style="color: #0066cc; text-decoration: none;">📍 {}, {}</a>',
                    map_url,
                    lat_str,
                    lon_str
                )
            except (ValueError, TypeError):
                return format_html('<span style="color: #999;">Invalid coordinates</span>')
        return format_html('<span style="color: #999;">No location</span>')
    display_location.short_description = 'Current Location'
    display_location.admin_order_field = 'latitude'

    def display_previous_location(self, obj):
        """Display formatted previous location with link to Google Maps"""
        if obj.previous_latitude and obj.previous_longitude:
            try:
                lat_str = f"{float(obj.previous_latitude):.6f}"
                lon_str = f"{float(obj.previous_longitude):.6f}"
                map_url = f"https://www.google.com/maps?q={obj.previous_latitude},{obj.previous_longitude}"
                
                return format_html(
                    '<a href="{}" target="_blank" style="color: #ff9900; text-decoration: none;">📌 {}, {}</a>',
                    map_url,
                    lat_str,
                    lon_str
                )
            except (ValueError, TypeError):
                return format_html('<span style="color: #999;">Invalid coordinates</span>')
        return format_html('<span style="color: #999;">No previous location</span>')
    display_previous_location.short_description = 'Previous Location'
    display_previous_location.admin_order_field = 'previous_latitude'

    def get_queryset(self, request):
        """Optimize queryset to prefetch related data"""
        return super().get_queryset(request).select_related('owner')


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'phone_number',
        'display_location',
        'display_previous_location',
        'location_updated_at',
        'location_source'
    ]
    list_filter = ['location_source']
    search_fields = ['name', 'phone_number']
    
    readonly_fields = [
        'location_updated_at', 
        'location_source', 
        'location_accuracy', 
        'previous_location_updated_at'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'profile_pic', 'phone_number')
        }),
        ('Current Location Information', {
            'fields': ('latitude', 'longitude', 'location_accuracy', 'location_source', 'location_updated_at'),
            'description': 'Location is automatically updated when customer logs in or moves'
        }),
        ('Previous Location Information', {
            'fields': ('previous_latitude', 'previous_longitude', 'previous_location_address', 'previous_location_updated_at'),
            'description': 'Automatically stores the previous location when location is updated',
            'classes': ('collapse',)
        }),
    )
    
    def display_location(self, obj):
        """Display formatted current location with link to Google Maps"""
        if obj.latitude and obj.longitude:
            try:
                lat_str = f"{float(obj.latitude):.6f}"
                lon_str = f"{float(obj.longitude):.6f}"
                map_url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
                
                return format_html(
                    '<a href="{}" target="_blank" style="color: #0066cc; text-decoration: none;">📍 {}, {}</a>',
                    map_url,
                    lat_str,
                    lon_str
                )
            except (ValueError, TypeError):
                return format_html('<span style="color: #999;">Invalid coordinates</span>')
        return format_html('<span style="color: #999;">No location</span>')
    display_location.short_description = 'Current Location'
    display_location.admin_order_field = 'latitude'

    def display_previous_location(self, obj):
        """Display formatted previous location with link to Google Maps"""
        if obj.previous_latitude and obj.previous_longitude:
            try:
                lat_str = f"{float(obj.previous_latitude):.6f}"
                lon_str = f"{float(obj.previous_longitude):.6f}"
                map_url = f"https://www.google.com/maps?q={obj.previous_latitude},{obj.previous_longitude}"
                
                return format_html(
                    '<a href="{}" target="_blank" style="color: #ff9900; text-decoration: none;">📌 {}, {}</a>',
                    map_url,
                    lat_str,
                    lon_str
                )
            except (ValueError, TypeError):
                return format_html('<span style="color: #999;">Invalid coordinates</span>')
        return format_html('<span style="color: #999;">No previous location</span>')
    display_previous_location.short_description = 'Previous Location'
    display_previous_location.admin_order_field = 'previous_latitude'

    def get_queryset(self, request):
        """Optimize queryset to prefetch related data"""
        return super().get_queryset(request).select_related('owner')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = [
        'customer', 
        'worker', 
        'appointment_date', 
        'status', 
        'shift_type', 
        'display_distance',
        'created_at'
    ]
    list_filter = ['status', 'shift_type', 'appointment_date', 'created_at']
    search_fields = ['customer__name', 'worker__name']
    readonly_fields = ['created_at']  # Removed 'updated_at' since it doesn't exist
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('customer', 'worker', 'appointment_date', 'status', 'shift_type')
        }),
        ('Service Information', {
            'fields': ('service_subtask', 'location', 'special_instructions'),
            'classes': ('collapse',)
        }),
        ('Completion Status', {
            'fields': ('customer_completed', 'worker_completed'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),  # Removed 'updated_at'
            'classes': ('collapse',)
        }),
    )
    
    def display_distance(self, obj):
        """Calculate and display distance between customer and worker"""
        if (obj.customer.latitude and obj.customer.longitude and 
            obj.worker.latitude and obj.worker.longitude):
            from math import radians, sin, cos, sqrt, asin
            
            try:
                lat1, lon1 = float(obj.customer.latitude), float(obj.customer.longitude)
                lat2, lon2 = float(obj.worker.latitude), float(obj.worker.longitude)
                
                # Validate coordinates
                if not (-90 <= lat1 <= 90) or not (-180 <= lon1 <= 180) or \
                   not (-90 <= lat2 <= 90) or not (-180 <= lon2 <= 180):
                    return format_html('<span style="color: #999;">Invalid coordinates</span>')
                
                lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = sin(dlat/2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon/2) ** 2
                c = 2 * asin(sqrt(a))
                distance = 6371.0 * c  # Earth radius in km
                
                distance_str = f"{distance:.2f} km"
                
                # Color code based on distance
                if distance < 5:
                    color = '#28a745'  # Green for very close
                elif distance < 20:
                    color = '#ffc107'  # Yellow for moderate distance
                else:
                    color = '#dc3545'  # Red for far away
                
                return format_html(
                    '<span style="color: {}; font-weight: bold;">{}</span>', 
                    color, 
                    distance_str
                )
            except (ValueError, TypeError, Exception):
                return format_html('<span style="color: #999;">Error calculating</span>')
        return format_html('<span style="color: #999;">No location data</span>')
    display_distance.short_description = 'Distance'

    def get_queryset(self, request):
        """Optimize queryset to prefetch related data"""
        return super().get_queryset(request).select_related('customer', 'worker', 'service_subtask')


@admin.register(WorkerRating)
class WorkerRatingAdmin(admin.ModelAdmin):
    list_display = [
        'worker', 
        'customer', 
        'rating', 
        'display_stars',
        'created_at'
        # Removed 'would_recommend' since it doesn't exist
    ]
    list_filter = ['rating', 'created_at']  # Removed 'would_recommend'
    search_fields = ['worker__name', 'customer__name', 'comment']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Rating Details', {
            'fields': ('worker', 'customer', 'appointment', 'rating')  # Removed 'would_recommend'
        }),
        ('Feedback', {
            'fields': ('comment', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def display_stars(self, obj):
        """Display rating as stars"""
        stars = '⭐' * obj.rating
        return format_html('<span style="font-size: 14px;">{}</span>', stars)
    display_stars.short_description = 'Stars'

    def get_queryset(self, request):
        """Optimize queryset to prefetch related data"""
        return super().get_queryset(request).select_related('worker', 'customer', 'appointment')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'category', 
        'base_pricing_type',
        'is_active'
        # Removed 'display_icon' since icon field might not exist
    ]
    list_filter = ['category', 'base_pricing_type', 'is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active']


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'description',
        'service_count'
        # Removed 'display_icon' since icon field might not exist
    ]
    search_fields = ['name', 'description']
    
    def service_count(self, obj):
        """Count services in this category"""
        return obj.services.count()
    service_count.short_description = 'Services Count'


@admin.register(SubTask)
class SubTaskAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'service', 
        'default_pricing_type',
        'duration',
        'materials_included',
        'special_offer'
    ]
    list_filter = ['service', 'default_pricing_type', 'materials_included', 'special_offer']
    search_fields = ['name', 'description']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'service', 'description', 'detailed_description')
        }),
        ('Pricing & Duration', {
            'fields': ('default_pricing_type', 'duration', 'requirements')
        }),
        ('Additional Options', {
            'fields': ('materials_included', 'special_offer', 'original_price', 'offer_price'),
            'classes': ('collapse',)
        }),
    )


@admin.register(WorkerService)
class WorkerServiceAdmin(admin.ModelAdmin):
    list_display = [
        'worker', 
        'service', 
        'is_available',
        'pricing_count'
        # Removed 'experience_years' since it doesn't exist
    ]
    list_filter = ['is_available', 'service']
    search_fields = ['worker__name', 'service__name']
    
    def pricing_count(self, obj):
        """Count pricing entries for this worker service"""
        return obj.pricing.count()
    pricing_count.short_description = 'Pricing Options'

    def get_queryset(self, request):
        """Optimize queryset to prefetch related data"""
        return super().get_queryset(request).select_related('worker', 'service').prefetch_related('pricing')


@admin.register(WorkerSubTaskPricing)
class WorkerSubTaskPricingAdmin(admin.ModelAdmin):
    list_display = [
        'worker_service', 
        'subtask', 
        'pricing_type', 
        'price', 
        'experience_level',
        'min_hours',
        'night_shift_extra'
    ]
    list_filter = ['pricing_type', 'experience_level']
    search_fields = [
        'worker_service__worker__name', 
        'subtask__name',
        'subtask__service__name'
    ]
    
    fieldsets = (
        ('Pricing Details', {
            'fields': ('worker_service', 'subtask', 'pricing_type', 'price')
        }),
        ('Experience & Timing', {
            'fields': ('experience_level', 'min_hours', 'night_shift_extra'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        """Optimize queryset to prefetch related data"""
        return super().get_queryset(request).select_related(
            'worker_service__worker', 
            'subtask',
            'subtask__service'
        )


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        'title', 
        'notification_type', 
        'is_read', 
        'created_at',
        'display_short_message'
        # Removed 'user' since it might not exist in your model
    ]
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['title', 'message']
    readonly_fields = ['created_at']
    list_editable = ['is_read']
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('title', 'message', 'notification_type', 'is_read')  # Removed 'user'
        }),
        ('Related Data', {
            'fields': ('appointment', 'related_id'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def display_short_message(self, obj):
        """Display shortened message"""
        if obj.message:
            if len(obj.message) > 50:
                return f"{obj.message[:50]}..."
            return obj.message
        return format_html('<span style="color: #999;">No message</span>')
    display_short_message.short_description = 'Message'


# Custom admin site header and title
admin.site.site_header = "BlueCaller Administration"
admin.site.site_title = "BlueCaller Admin Portal"
admin.site.index_title = "Welcome to BlueCaller Administration"