# models.py - Enhanced with Notification System and Dynamic Pricing (Without GIS)
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Avg, Count
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
import math
import logging
from decimal import Decimal
logger = logging.getLogger(__name__)

User = get_user_model()

# Create your models here.
SHIFT_DAY = 'day'
SHIFT_NIGHT = 'night'
SHIFT_ALL = 'all'
SHIFT_CHOICES = [
    (SHIFT_DAY, 'Day'),
    (SHIFT_NIGHT, 'Night'),
    (SHIFT_ALL, 'All'),
]

# Service Pricing Types
PRICING_TYPES = [
    ('hourly', 'Hourly Rate'),
    ('sqft', 'Per Square Foot'),
    ('unit', 'Per Unit/Item'),
    ('inspection', 'Per Inspection'),
    ('shift', 'Shift-based'),
    ('fixed', 'Fixed Price'),
]

# Service Categories
class ServiceCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to='category_images/', blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Service Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name

class Service(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=100)
    description = models.TextField()
    base_pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES, default='fixed')
    image = models.ImageField(upload_to='service_images/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.category.name} - {self.name}"

class SubTask(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='subtasks')
    name = models.CharField(max_length=100)
    description = models.TextField()
    detailed_description = models.TextField(blank=True, null=True)
    default_pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES, default='fixed')
    duration = models.CharField(max_length=100, blank=True)  # e.g., "1 day", "2 hours"
    materials_included = models.BooleanField(default=False)
    special_offer = models.BooleanField(default=False)
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    requirements = models.TextField(blank=True)
    image = models.ImageField(upload_to="subtask_images/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return f"{self.service.name} - {self.name}"

def _haversine_km(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    Returns distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

# Worker Model
class Worker(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone_number = PhoneNumberField(region="NP")
    tagline = models.CharField(max_length=200, blank=True, null=True)
    bio = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to="worker_profiles/", blank=True, null=True)
    verified = models.BooleanField(default=False)
    citizenship_image = models.ImageField(upload_to='citizenship/', blank=True, null=True)
    certificate_file = models.FileField(upload_to='certificates/', blank=True, null=True)
    appointed = models.BooleanField(default=False)
    appointment_date = models.DateTimeField(null=True, blank=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_ratings = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default=SHIFT_ALL)

    previous_latitude = models.FloatField(null=True, blank=True)
    previous_longitude = models.FloatField(null=True, blank=True)
    previous_location_address = models.TextField(blank=True, null=True)
    previous_location_updated_at = models.DateTimeField(null=True, blank=True)
    
    # Enhanced location fields (without GIS)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_address = models.TextField(blank=True, null=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)
    location_accuracy = models.FloatField(null=True, blank=True)  # Accuracy in meters
    location_source = models.CharField(
        max_length=20, 
        choices=[
            ('browser', 'Browser Geolocation'),
            ('ip', 'IP Address'),
            ('manual', 'Manual Entry'),
            ('unknown', 'Unknown')
        ],
        default='unknown'
    )
    
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def update_location(self, latitude, longitude, accuracy=None, source='browser', address=None):
        """Update worker location with coordinates"""
        try:
            self.latitude = float(latitude)
            self.longitude = float(longitude)
            self.location_accuracy = accuracy
            self.location_source = source
            self.location_updated_at = timezone.now()
            
            # If address is provided, use it directly
            if address:
                self.location_address = address
            else:
                # Simple location string if no address
                self.location_address = f"Location: {latitude:.4f}, {longitude:.4f}"
            
            self.save()
            logger.info(f"Updated worker {self.name} location to ({latitude}, {longitude})")
            return True
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error updating location for worker {self.name}: {e}")
            return False
            """Get previous location data"""
    def get_previous_location(self):
            if self.previous_latitude and self.previous_longitude:
                return {
                    'latitude': self.previous_latitude,
                    'longitude': self.previous_longitude,
                    'address': self.previous_location_address,
                    'updated_at': self.previous_location_updated_at
                }
            return None

    def has_previous_location(self):
        """Check if previous location exists"""
        return self.previous_latitude is not None and self.previous_longitude is not None

    def get_current_location(self):
        """Get current location with fallback"""
        if self.latitude and self.longitude:
            return {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'address': self.location_address,
                'updated_at': self.location_updated_at,
                'accuracy': self.location_accuracy,
                'source': self.location_source
            }
        return None


    def calculate_distance(self, other_lat, other_lon):
        """Calculate distance to another point in kilometers"""
        if not all([self.latitude, self.longitude, other_lat, other_lon]):
            return None
            
        return _haversine_km(self.latitude, self.longitude, other_lat, other_lon)

    def bayesian_average_rating(self, confidence=5.0):
        """
        Calculate Bayesian average rating for a worker.
        confidence represents the number of "dummy" ratings to consider
        """
        # Get all ratings for this worker
        ratings = self.ratings.all()
        total_ratings = ratings.count()

        if total_ratings == 0:
            return 0

        # Calculate average rating
        avg_rating = ratings.aggregate(Avg('rating'))['rating__avg']

        # Calculate global average (across all workers)
        from .models import WorkerRating
        global_avg = WorkerRating.objects.aggregate(Avg('rating'))['rating__avg'] or 3.0

        # Apply Bayesian formula
        bayesian_avg = (confidence * global_avg + total_ratings * avg_rating) / (confidence + total_ratings)

        return round(bayesian_avg, 2)

    def update_average_rating(self):
        """Update the average rating and rating count for the worker"""
        ratings = self.ratings.all()
        self.rating_count = ratings.count()

        if self.rating_count > 0:
            # Use Bayesian average for more accurate representation
            self.average_rating = self.bayesian_average_rating()
        else:
            self.average_rating = 0

        self.save()

    def get_rating_breakdown(self):
        """Get the breakdown of ratings (how many of each star)"""
        breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for rating in self.ratings.all():
            if 1 <= rating.rating <= 5:
                breakdown[rating.rating] += 1

        return breakdown

    def get_unread_notification_count(self):
        """Get count of unread notifications for this worker"""
        return self.notifications.filter(is_read=False).count()

    def __str__(self):
        return f"{self.name} - {self.tagline}"

# Worker Services (Many-to-Many through model)
class WorkerService(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='worker_services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('worker', 'service')
        ordering = ['service__name']
    
    def __str__(self):
        return f"{self.worker.name} - {self.service.name}"

# Worker SubTask Pricing
class WorkerSubTaskPricing(models.Model):
    EXPERIENCE_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]
    
    worker_service = models.ForeignKey(WorkerService, on_delete=models.CASCADE, related_name='pricing')
    subtask = models.ForeignKey(SubTask, on_delete=models.CASCADE)
    pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVELS, blank=True)
    night_shift_extra = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_hours = models.PositiveIntegerField(default=1, help_text="Minimum hours for hourly pricing")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('worker_service', 'subtask')
        ordering = ['subtask__name']
    
    def __str__(self):
        return f"{self.worker_service.worker.name} - {self.subtask.name}: ₹{self.price}"
    
    def get_pricing_type_display(self):
        types_dict = {
            'hourly': 'Hourly Rate',
            'sqft': 'Per Square Foot',
            'unit': 'Per Unit/Item',
            'inspection': 'Per Inspection',
            'shift': 'Shift-based',
            'fixed': 'Fixed Price',
        }
        return types_dict.get(self.pricing_type, self.pricing_type)
    
    def get_experience_level_display(self):
        return dict(self.EXPERIENCE_LEVELS).get(self.experience_level, self.experience_level)
    
    def get_total_price(self, quantity=1, is_night_shift=False):
        """
        ✅ FIXED: Calculate total price with proper Decimal handling
        All calculations use Decimal to avoid float/Decimal conflicts
        """
        # Ensure base price is Decimal
        total = Decimal(str(self.price)) if self.price else Decimal('0.00')
        
        # Add night shift extra if applicable
        if is_night_shift and self.night_shift_extra:
            night_extra = Decimal(str(self.night_shift_extra))
            total += night_extra
        
        # Convert quantity to Decimal for safe arithmetic
        try:
            qty = Decimal(str(quantity))
        except (ValueError, TypeError):
            qty = Decimal('1.00')
        
        # Calculate based on pricing type
        if self.pricing_type in ['sqft', 'unit']:
            # Multiply by quantity for per-unit pricing
            total = total * qty
            
        elif self.pricing_type == 'hourly':
            # For hourly, use maximum of min_hours or quantity
            min_hrs = Decimal(str(self.min_hours))
            hours = max(min_hrs, qty)
            total = total * hours
        
        # For 'fixed', 'shift', 'inspection' types, return base total
        
        # Round to 2 decimal places and return
        return total.quantize(Decimal('0.01'))

# Customer Model
class Customer(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone_number = PhoneNumberField(region="NP")
    profile_pic = models.ImageField(upload_to="customer_profiles/", blank=True, null=True)
    
    # Enhanced location fields
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_address = models.TextField(blank=True, null=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)
    location_accuracy = models.FloatField(null=True, blank=True)
    location_source = models.CharField(
        max_length=20, 
        choices=[
            ('browser', 'Browser Geolocation'),
            ('ip', 'IP Address'),
            ('manual', 'Manual Entry'),
            ('unknown', 'Unknown')
        ],
        default='unknown'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    previous_latitude = models.FloatField(null=True, blank=True)
    previous_longitude = models.FloatField(null=True, blank=True)
    previous_location_address = models.TextField(blank=True, null=True)
    previous_location_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def update_location(self, latitude, longitude, accuracy=None, source='browser', address=None):
        """Update customer location with coordinates - stores previous location"""
        try:
            # Store current location as previous before updating
            if self.latitude and self.longitude:
                self.previous_latitude = self.latitude
                self.previous_longitude = self.longitude
                self.previous_location_address = self.location_address
                self.previous_location_updated_at = self.location_updated_at
            
            # Update current location
            self.latitude = float(latitude)
            self.longitude = float(longitude)
            self.location_accuracy = accuracy
            self.location_source = source
            self.location_updated_at = timezone.now()
            
            # If address is provided, use it directly
            if address:
                self.location_address = address
            else:
                # Simple location string if no address
                self.location_address = f"Location: {latitude:.4f}, {longitude:.4f}"
            
            self.save()
            logger.info(f"Updated customer {self.name} location to ({latitude}, {longitude}) - Previous location stored")
            return True
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error updating location for customer {self.name}: {e}")
            return False

    def get_previous_location(self):
            """Get previous location data"""
            if self.previous_latitude and self.previous_longitude:
                return {
                    'latitude': self.previous_latitude,
                    'longitude': self.previous_longitude,
                    'address': self.previous_location_address,
                    'updated_at': self.previous_location_updated_at
                }
            return None

    def has_previous_location(self):
        """Check if previous location exists"""
        return self.previous_latitude is not None and self.previous_longitude is not None

    def get_current_location(self):
        """Get current location with fallback"""
        if self.latitude and self.longitude:
            return {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'address': self.location_address,
                'updated_at': self.location_updated_at,
                'accuracy': self.location_accuracy,
                'source': self.location_source
            }
        return None

    def find_nearby_workers(self, max_distance_km=50, limit=20):
        """Find workers within specified distance using efficient query"""
        if not self.latitude or not self.longitude:
            return Worker.objects.none()
        
        # Get all workers with location data
        workers_with_location = Worker.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        )
        
        nearby_workers = []
        for worker in workers_with_location:
            distance = _haversine_km(
                self.latitude, self.longitude,
                worker.latitude, worker.longitude
            )
            
            if distance is not None and distance <= max_distance_km:
                worker.distance_km = distance
                nearby_workers.append(worker)
        
        # Sort by distance and limit results
        nearby_workers.sort(key=lambda x: x.distance_km)
        return nearby_workers[:limit]

    def get_unread_notification_count(self):
        """Get count of unread notifications for this customer"""
        return self.notifications.filter(is_read=False).count()

    def __str__(self):
        return f"{self.name}"


class Appointment(models.Model):
    """
    Appointment model for booking services between customers and workers
    """
    # Primary key
    id = models.BigAutoField(primary_key=True)
    
    # Status choices
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Shift type choices
    SHIFT_TYPES = [
        ('day', 'Day Shift'),
        ('night', 'Night Shift'),
    ]
    
    # Foreign Keys
    customer = models.ForeignKey(
        'Customer', 
        on_delete=models.CASCADE, 
        related_name='customer_appointments'
    )
    worker = models.ForeignKey(
        'Worker', 
        on_delete=models.CASCADE, 
        related_name='worker_appointments'
    )
    service_subtask = models.ForeignKey(
        'WorkerSubTaskPricing', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Selected service and pricing"
    )
    
    # Appointment details
    appointment_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    shift_type = models.CharField(
        max_length=10, 
        choices=SHIFT_TYPES, 
        default='day'
    )
    
    # Location and instructions
    location = models.TextField(blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    
    # Completion tracking
    customer_completed = models.BooleanField(default=False)
    worker_completed = models.BooleanField(default=False)
    
    # Customer location at time of booking
    customer_latitude = models.FloatField(null=True, blank=True)
    customer_longitude = models.FloatField(null=True, blank=True)
    
    # Pricing fields - REQUIRED TO FIX THE ERROR
    total_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Total calculated price for the service"
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Quantity/hours for pricing calculation"
    )
    is_night_shift = models.BooleanField(
        default=False,
        help_text="Whether night shift extra charges apply"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-appointment_date']
        indexes = [
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['worker', 'status']),
            models.Index(fields=['appointment_date']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = 'Appointment'
        verbose_name_plural = 'Appointments'

    def __str__(self):
        date_str = self.appointment_date.strftime('%Y-%m-%d %H:%M') if self.appointment_date else 'No date'
        return f"{self.customer.name} → {self.worker.name} on {date_str}"

    def calculate_total_price(self):
        """
        Calculate total price based on service subtask pricing
        Returns Decimal value or 0 if service_subtask is not set
        """
        if not self.service_subtask:
            return 0
        
        # Determine if night shift applies
        night_shift = self.is_night_shift or (self.shift_type == 'night')
        
        # Use the get_total_price method from WorkerSubTaskPricing
        return self.service_subtask.get_total_price(
            quantity=self.quantity,
            is_night_shift=night_shift
        )
    
    def save(self, *args, **kwargs):
        """
        Override save to auto-calculate total_price if not manually set
        """
        # Auto-calculate total_price if service_subtask exists and total_price not set
        if self.service_subtask and not self.total_price:
            self.total_price = self.calculate_total_price()
        
        # Set is_night_shift based on shift_type if not manually set
        if self.shift_type == 'night' and not self.is_night_shift:
            self.is_night_shift = True
        
        super().save(*args, **kwargs)

    def get_status_display_color(self):
        """Return Bootstrap color class for status"""
        status_colors = {
            'pending': 'warning',
            'accepted': 'info',
            'rejected': 'danger',
            'completed': 'success',
            'cancelled': 'secondary',
        }
        return status_colors.get(self.status, 'secondary')

    def can_be_completed(self):
        """Check if appointment can be marked as completed"""
        return (
            self.status == 'accepted' and 
            self.appointment_date and 
            self.appointment_date < timezone.now()
        )

    def can_be_cancelled(self):
        """Check if appointment can be cancelled"""
        return self.status in ['pending', 'accepted']

    def get_service_name(self):
        """Get the service name safely"""
        if self.service_subtask and self.service_subtask.subtask:
            return self.service_subtask.subtask.name
        return "General Service"

    def get_price_display(self):
        """Get formatted price display"""
        if self.total_price:
            return f"₹{self.total_price:,.2f}"
        elif self.service_subtask:
            return f"₹{self.service_subtask.price:,.2f}"
        return "Contact for pricing"

    @property
    def is_past(self):
        """Check if appointment date is in the past"""
        if not self.appointment_date:
            return False
        return self.appointment_date < timezone.now()

    @property
    def is_today(self):
        """Check if appointment is today"""
        if not self.appointment_date:
            return False
        return self.appointment_date.date() == timezone.now().date()

    @property
    def is_upcoming(self):
        """Check if appointment is in the future"""
        if not self.appointment_date:
            return False
        return self.appointment_date > timezone.now()
# Worker Rating Model
class WorkerRating(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='ratings')
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='given_ratings')
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('appointment', 'customer')
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update worker's average rating when a new rating is added
        self.worker.update_average_rating()

    def __str__(self):
        return f"Rating {self.rating} by {self.customer.name} for {self.worker.name}"

# Notification Model
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('appointment_request', 'Appointment Request'),
        ('appointment_accepted', 'Appointment Accepted'),
        ('appointment_rejected', 'Appointment Rejected'),
        ('appointment_completed', 'Appointment Completed'),
        ('appointment_cancelled', 'Appointment Cancelled'),
        ('rating_received', 'Rating Received'),
    ]

    # Generic foreign keys to handle both Worker and Customer
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        recipient = self.worker.name if self.worker else self.customer.name
        return f"Notification for {recipient} - {self.title}"

    def mark_as_read(self):
        self.is_read = True
        self.save()

class FavoriteWorker(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='favorite_workers')
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'worker')
        ordering = ['-created_at']
        verbose_name = 'Favorite Worker'
        verbose_name_plural = 'Favorite Workers'

    def __str__(self):
        return f"{self.customer.name} favorites {self.worker.name}"

# NEW MODELS FOR ADVANCED FEATURES

class WorkerAvailability(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='availability')
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['worker', 'day_of_week']
        ordering = ['day_of_week', 'start_time']
        verbose_name_plural = "Worker Availabilities"

    def __str__(self):
        return f"{self.worker.name} - {self.get_day_of_week_display()} {self.start_time}-{self.end_time}"

class WorkerEarning(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='earnings')
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_date = models.DateTimeField(blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['worker', 'payment_status']),
            models.Index(fields=['payment_date']),
        ]

    def __str__(self):
        return f"{self.worker.name} - ₹{self.net_amount} - {self.payment_status}"

    def save(self, *args, **kwargs):
        if not self.net_amount:
            self.net_amount = self.amount - self.platform_fee
        super().save(*args, **kwargs)

class WorkerAnalytics(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='analytics')
    date = models.DateField()
    
    # Performance metrics
    total_appointments = models.PositiveIntegerField(default=0)
    completed_appointments = models.PositiveIntegerField(default=0)
    cancelled_appointments = models.PositiveIntegerField(default=0)
    
    # Financial metrics
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    
    # Customer metrics
    new_customers = models.PositiveIntegerField(default=0)
    repeat_customers = models.PositiveIntegerField(default=0)
    
    # Response metrics
    average_response_time = models.PositiveIntegerField(default=0)  # in minutes
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['worker', 'date']
        ordering = ['-date']
        verbose_name_plural = "Worker Analytics"

    def __str__(self):
        return f"{self.worker.name} - {self.date}"

    @property
    def completion_rate(self):
        if self.total_appointments > 0:
            return round((self.completed_appointments / self.total_appointments) * 100, 1)
        return 0

    @property
    def cancellation_rate(self):
        if self.total_appointments > 0:
            return round((self.cancelled_appointments / self.total_appointments) * 100, 1)
        return 0

class WorkerSettings(models.Model):
    worker = models.OneToOneField(Worker, on_delete=models.CASCADE, related_name='settings')
    
    # Notification preferences
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    appointment_reminders = models.BooleanField(default=True)
    review_notifications = models.BooleanField(default=True)
    
    # Working preferences
    working_hours_start = models.TimeField(default='09:00')
    working_hours_end = models.TimeField(default='18:00')
    service_radius_km = models.PositiveIntegerField(default=25)
    auto_accept_appointments = models.BooleanField(default=False)
    
    # Payment preferences
    preferred_payment_method = models.CharField(
        max_length=50,
        default='bank_transfer',
        choices=[
            ('bank_transfer', 'Bank Transfer'),
            ('upi', 'UPI'),
            ('cash', 'Cash'),
        ]
    )
    
    # Display preferences
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Worker Settings"

    def __str__(self):
        return f"Settings for {self.worker.name}"

class ServiceArea(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='service_areas')
    area_name = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['worker', 'area_name']
        ordering = ['area_name']

    def __str__(self):
        return f"{self.worker.name} - {self.area_name}"

class WorkerPortfolio(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='portfolio')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='worker_portfolio/')
    service_category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, blank=True, null=True)
    before_image = models.ImageField(upload_to='portfolio/before/', blank=True, null=True)
    after_image = models.ImageField(upload_to='portfolio/after/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Worker Portfolios"

    def __str__(self):
        return f"{self.worker.name} - {self.title}"

# Signal handlers for automatic creation of related objects
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Worker)
def create_worker_settings(sender, instance, created, **kwargs):
    if created:
        WorkerSettings.objects.create(worker=instance)

from decimal import Decimal

@receiver(post_save, sender=Appointment)
def create_worker_earning(sender, instance, created, **kwargs):
    """✅ FIXED: Create worker earning with proper Decimal handling"""
    if created and instance.service_subtask:
        # Get amount as Decimal
        amount = instance.total_price if instance.total_price else instance.calculate_total_price()
        
        # Ensure it's a Decimal
        if amount:
            amount = Decimal(str(amount))
            
            if amount > Decimal('0.00'):
                # ✅ Calculate platform fee using Decimal (not 0.10 which is float)
                platform_fee = amount * Decimal('0.10')
                
                WorkerEarning.objects.create(
                    worker=instance.worker,
                    appointment=instance,
                    amount=amount,
                    platform_fee=platform_fee,
                )
                
@receiver(post_save, sender=Appointment)
def create_appointment_notification(sender, instance, created, **kwargs):
    if created:
        # Notification for worker
        Notification.objects.create(
            worker=instance.worker,
            notification_type='appointment_request',
            title='New Appointment Request',
            message=f'You have a new appointment request from {instance.customer.name}',
            appointment=instance
        )
        
        # Notification for customer
        Notification.objects.create(
            customer=instance.customer,
            notification_type='appointment_request',
            title='Appointment Request Sent',
            message=f'Your appointment request to {instance.worker.name} has been sent',
            appointment=instance
        )

@receiver(post_save, sender=WorkerRating)
def create_review_notification(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            worker=instance.worker,
            notification_type='rating_received',
            title='New Review Received',
            message=f'You received a {instance.rating}★ review from {instance.customer.name}',
        )