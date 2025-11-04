# models.py - Enhanced with Bayesian Rating System
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
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

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

# In SubTask model, add:
class SubTask(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='subtasks')
    name = models.CharField(max_length=100)
    description = models.TextField()
    detailed_description = models.TextField(blank=True, null=True)
    default_pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES, default='fixed')
    duration = models.CharField(max_length=100, blank=True)
    materials_included = models.BooleanField(default=False)
    special_offer = models.BooleanField(default=False)
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    requirements = models.TextField(blank=True)
    image = models.ImageField(upload_to="subtask_images/", blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='created_subtasks')
    is_custom = models.BooleanField(default=False)  
    is_active = models.BooleanField(default=True)
    
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

class Worker(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    phone_number = PhoneNumberField(region="NP")
    tagline = models.CharField(max_length=200, blank=True, null=True)
    bio = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to="worker_profiles/", blank=True, null=True)
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        default='prefer_not_to_say',
        blank=True,
        null=True
    )
    
    # Verification fields
    verified = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected')
        ],
        default='pending'
    )
    rejection_reason = models.TextField(blank=True, null=True)
    last_rejection_date = models.DateTimeField(blank=True, null=True)  
    verification_submitted_at = models.DateTimeField(blank=True, null=True) 
    
    # Documents
    citizenship_image = models.ImageField(upload_to='citizenship/', blank=True, null=True)
    certificate_file = models.FileField(upload_to='certificates/', blank=True, null=True)
    
    # Appointment fields
    appointed = models.BooleanField(default=False)
    appointment_date = models.DateTimeField(null=True, blank=True)
    
    # ✅ FIXED: Remove redundant total_ratings field
    # Rating fields - keep only rating_count
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    rating_count = models.PositiveIntegerField(default=0)
    # REMOVED: total_ratings = models.PositiveIntegerField(default=0)
    
    # Availability
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default=SHIFT_ALL)
    is_available = models.BooleanField(default=True)
    
    # Enhanced location fields (current location)
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
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.tagline if self.tagline else 'Worker'}"

    def save(self, *args, **kwargs):
        """Override save to sync verification status"""
        # Don't auto-change status if it's explicitly rejected
        if self.verification_status != 'rejected':
            # Only auto-set verification status if not rejected
            if self.verified:
                self.verification_status = 'approved'
            elif not self.verified and self.verification_status == 'approved':
                self.verification_status = 'pending'
        
        super().save(*args, **kwargs)


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

    def can_resubmit_verification(self):
        """Check if worker can resubmit for verification after 15 minutes"""
        if not self.last_rejection_date:
            return True
        # Allow resubmission after 15 minutes
        return timezone.now() >= self.last_rejection_date + timedelta(minutes=15)
    
    def get_resubmission_wait_time(self):
        """Get remaining wait time in minutes for resubmission"""
        if not self.last_rejection_date or self.can_resubmit_verification():
            return 0
        
        wait_until = self.last_rejection_date + timedelta(minutes=15)
        time_left = wait_until - timezone.now()
        minutes_left = max(0, int(time_left.total_seconds() // 60))
        return minutes_left
    
    def get_resubmission_wait_time_display(self):  #for displaying wait time to user
        """Get formatted wait time for display"""
        minutes = self.get_resubmission_wait_time()
        if minutes == 0:
            return "Ready to resubmit"
        elif minutes < 60:
            return f"{minutes} minutes"
        else:
            hours = minutes // 60
            remaining_minutes = minutes % 60
            return f"{hours}h {remaining_minutes}m"

    def bayesian_average_rating(self, confidence=5.0, default_rating=0.0):
        """
        Calculate Bayesian average rating for a worker.
        confidence: number of "dummy" ratings to consider
        default_rating: the default rating to use when there are no ratings (0 means no rating)
        """
        try:
            # Get all ratings for this worker
            ratings = self.ratings.all()
            total_ratings = ratings.count()

            # If no ratings, return 0 (no rating)
            if total_ratings == 0:
                return default_rating

            # Calculate average rating for this worker
            avg_rating = ratings.aggregate(Avg('rating'))['rating__avg']
            if avg_rating is None:
                return default_rating

            # Calculate global average (across all workers)
            global_stats = WorkerRating.objects.aggregate(
                global_avg=Avg('rating'),
                global_count=Count('id')
            )
            global_avg = global_stats['global_avg'] or 3.0  # Use 3.0 as global average

            # Apply Bayesian formula:
            # (confidence * global_avg + total_ratings * actual_avg) / (confidence + total_ratings)
            bayesian_avg = (confidence * global_avg + total_ratings * avg_rating) 
            bayesian_avg /= (confidence + total_ratings)

            return round(bayesian_avg, 2)
            
        except Exception as e:
            logger.error(f"Error calculating Bayesian average for worker {self.id}: {e}")
            return default_rating

    def get_rating_display_data(self):
        """Get rating display data for templates"""
        bayesian_rating = self.bayesian_average_rating()
        
        full_stars = int(bayesian_rating)
        half_star = 1 if bayesian_rating % 1 >= 0.5 else 0
        empty_stars = 5 - (full_stars + half_star)
        
        return {
            'bayesian_rating': bayesian_rating,
            'total_ratings': self.rating_count,
            'has_ratings': self.rating_count > 0,
            'full_stars': full_stars,
            'half_star': half_star,
            'empty_stars': empty_stars
        }

    def get_bayesian_rating_display(self):
        """Get Bayesian rating for display with rating count"""
        return {
            'rating': self.bayesian_average_rating(),
            'count': self.ratings.count(),
            'total_ratings': self.ratings.count()
        }

    def get_star_breakdown(self):
        """Get star breakdown for Bayesian rating display"""
        bayesian_rating = self.bayesian_average_rating()
        full_stars = int(bayesian_rating)
        half_star = (bayesian_rating - full_stars) >= 0.5
        empty_stars = 5 - full_stars - (1 if half_star else 0)
        
        return {
            'full_stars': range(full_stars),
            'half_star': half_star,
            'empty_stars': range(empty_stars),
            'rating': bayesian_rating
        }

    def update_average_rating(self):
        """Update the average rating using Bayesian algorithm"""
        try:
            ratings = self.ratings.all()
            self.rating_count = ratings.count()

            if self.rating_count > 0:
                # Use Bayesian average instead of simple average
                self.average_rating = self.bayesian_average_rating()
            else:
                self.average_rating = 0

            self.save(update_fields=['average_rating', 'rating_count'])
            
        except Exception as e:
            logger.error(f"Error updating average rating for worker {self.id}: {e}")

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

    @property
    def services(self):
        """Property to access services through worker_services"""
        return Service.objects.filter(
            workerservice__worker=self,
            workerservice__is_available=True
        ).distinct()
    
    def get_available_services(self):
        """Get available services with their WorkerService objects"""
        return self.worker_services.filter(is_available=True).select_related('service')

    def verify_worker(self):
        """Verify worker and update status"""
        self.verified = True
        self.verification_status = 'approved'
        # Clear rejection data when verifying
        self.rejection_reason = ''
        self.last_rejection_date = None
        self.save()
        
        # Create notification for worker
        Notification.objects.create(
            worker=self,
            notification_type='worker_verified',
            title='Profile Verified!',
            message='Your worker profile has been verified by admin. You can now receive appointments.',
            appointment=None
        )
        
        # Log the verification
        try:
            from admin_dashboard.models import AdminActivityLog
            AdminActivityLog.objects.create(
                admin_user=None,  # System action
                action='UPDATE',
                model_name='Worker',
                object_id=self.id,
                description=f'Worker {self.name} verified via email link'
            )
        except:
            pass  # Skip if admin dashboard not available
        
        return True

    def reject_worker(self, reason="Profile does not meet requirements"):
        """Reject worker with reason AND set rejection date"""
        self.verified = False
        self.verification_status = 'rejected'
        self.rejection_reason = reason
        self.last_rejection_date = timezone.now()
        self.save()
        
        # Create notification for worker
        Notification.objects.create(
            worker=self,
            notification_type='worker_rejected',
            title='Profile Verification Failed',
            message=f'Your worker profile verification was rejected. Reason: {reason}',
            appointment=None
        )
        
        logger.info(f"Worker {self.name} rejected at {self.last_rejection_date}")
        return True
        
    @classmethod
    def get_visible_workers(cls):
        """Get all workers that should be visible to customers"""
        return cls.objects.filter(
            verified=True,
            verification_status='approved',
            is_available=True
        ).select_related('owner').prefetch_related('ratings')



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
    max_hours = models.PositiveIntegerField(default=8, help_text="Maximum hours per day")
    unit_label = models.CharField(max_length=50, blank=True, help_text="Label for unit (e.g., 'sq ft', 'rooms', 'items')")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('worker_service', 'subtask')
        ordering = ['subtask__name']
    
    def __str__(self):
        return f"{self.worker_service.worker.name} - {self.subtask.name}: Rs{self.price}"
    
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
    
    def get_unit_label(self):
        """Get appropriate unit label based on pricing type"""
        if self.unit_label:
            return self.unit_label
            
        unit_labels = {
            'sqft': 'sq ft',
            'unit': 'units',
            'hourly': 'hours',
            'shift': 'shifts',
            'inspection': 'inspections',
            'fixed': 'service',
        }
        return unit_labels.get(self.pricing_type, 'units')
    
    def get_price_display(self):
        """Get formatted price display with unit"""
        base_price = f"Rs{self.price}"
        
        if self.pricing_type == 'hourly':
            return f"{base_price}/hour (min {self.min_hours} hrs)"
        elif self.pricing_type == 'sqft':
            return f"{base_price}/sq ft"
        elif self.pricing_type == 'unit':
            return f"{base_price}/{self.get_unit_label()}"
        elif self.pricing_type == 'shift':
            return f"{base_price}/shift"
        elif self.pricing_type == 'inspection':
            return f"{base_price}/inspection"
        else:  # fixed
            return f"{base_price} (fixed)"
    
    def calculate_total_price(self, quantity=1, is_night_shift=False, custom_inputs=None):
        """
        Enhanced price calculation with support for all pricing types
        """
        custom_inputs = custom_inputs or {}
        
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
        if self.pricing_type == 'sqft':
            # For square footage, use quantity as area
            total = total * qty
            
        elif self.pricing_type == 'unit':
            # For per-unit pricing
            total = total * qty
            
        elif self.pricing_type == 'hourly':
            # For hourly, use maximum of min_hours or quantity
            min_hrs = Decimal(str(self.min_hours))
            hours = max(min_hrs, qty)
            # Apply maximum hour limit
            max_hrs = Decimal(str(self.max_hours))
            hours = min(hours, max_hrs)
            total = total * hours
            
        elif self.pricing_type == 'shift':
            # Shift-based pricing (8-hour shifts typically)
            shift_hours = Decimal('8.0')  # Standard shift duration
            total_shifts = qty
            total = total * total_shifts
            
        elif self.pricing_type == 'inspection':
            # Per inspection - quantity is number of inspections
            total = total * qty
            
        # For 'fixed' pricing, return base total without quantity multiplier
        
        # Handle custom inputs for complex calculations
        if custom_inputs:
            total = self._apply_custom_calculations(total, custom_inputs)
        
        # Round to 2 decimal places and return
        return total.quantize(Decimal('0.01'))
    
    def _apply_custom_calculations(self, base_total, custom_inputs):
        """Apply custom calculation logic based on service type"""
        # Example: For painting, you might have room size, number of coats, etc.
        # This can be extended based on specific service requirements
        return base_total
    
    def get_pricing_input_config(self):
        """Get configuration for pricing input fields based on pricing type"""
        configs = {
            'fixed': {
                'show_quantity': False,
                'input_type': 'none',
                'label': 'Fixed Price',
                'min_value': 1,
                'max_value': 1,
                'step': 1
            },
            'hourly': {
                'show_quantity': True,
                'input_type': 'number',
                'label': 'Hours Required',
                'min_value': self.min_hours,
                'max_value': self.max_hours,
                'step': 0.5,
                'help_text': f'Minimum {self.min_hours} hours'
            },
            'sqft': {
                'show_quantity': True,
                'input_type': 'number',
                'label': 'Area (sq ft)',
                'min_value': 1,
                'max_value': 10000,
                'step': 1,
                'help_text': 'Enter the area in square feet'
            },
            'unit': {
                'show_quantity': True,
                'input_type': 'number',
                'label': f'Number of {self.get_unit_label()}',
                'min_value': 1,
                'max_value': 1000,
                'step': 1,
                'help_text': f'Enter number of {self.get_unit_label()}'
            },
            'shift': {
                'show_quantity': True,
                'input_type': 'number',
                'label': 'Number of Shifts',
                'min_value': 1,
                'max_value': 10,
                'step': 1,
                'help_text': 'Each shift is typically 8 hours'
            },
            'inspection': {
                'show_quantity': True,
                'input_type': 'number',
                'label': 'Number of Inspections',
                'min_value': 1,
                'max_value': 10,
                'step': 1,
                'help_text': 'Enter number of inspections needed'
            }
        }
        return configs.get(self.pricing_type, configs['fixed'])
    
    def get_total_price(self, quantity=1, is_night_shift=False, custom_inputs=None):
        """Alias for calculate_total_price for backward compatibility"""
        return self.calculate_total_price(quantity, is_night_shift, custom_inputs)


# Customer Model
class Customer(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone_number = PhoneNumberField(region="NP")
    profile_pic = models.ImageField(upload_to="customer_profiles/", blank=True, null=True)
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        default='prefer_not_to_say',
        blank=True,
        null=True
    )
    
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


    class Meta:
        ordering = ['name']

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
    
    # ✅ ADD THIS FIELD to store time ranges
    time_slot = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Time slot in format '14:00-16:00'"
    )
    
    # Add these delay-related fields
    estimated_completion_time = models.DateTimeField(null=True, blank=True)
    delay_reason = models.TextField(blank=True, null=True)
    delay_reported_at = models.DateTimeField(null=True, blank=True)
    original_end_time = models.DateTimeField(null=True, blank=True) 
    is_delayed = models.BooleanField(default=False) 
    
    # ✅ UPDATED: Status choices - differentiate between cancelled and rejected
    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected by Worker'),      # Worker rejects request
        ('cancelled', 'Cancelled by Customer'),  # Customer cancels appointment
        ('completed', 'Completed'),
        ('expired', 'Expired'),                  # System auto-cancelled
    ]
    
    # Shift type choices
    SHIFT_TYPES = [
        ('day', 'Day Shift'),
        ('night', 'Night Shift'),
    ]
    
    # ✅ ADD: Cancellation/Rejection tracking fields
    cancelled_by = models.CharField(
        max_length=20, 
        choices=[('customer', 'Customer'), ('worker', 'Worker'), ('system', 'System')],
        blank=True, null=True,
        help_text="Who cancelled the appointment"
    )
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, null=True)
    
    rejected_by = models.CharField(
        max_length=20, 
        blank=True, null=True,
        help_text="Who rejected the appointment"
    )
    rejected_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
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
        max_length=30, 
        choices=STATUS_CHOICES, 
        default='pending_payment'
    )
    shift_type = models.CharField(
        max_length=20, 
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
    
    # Pricing fields
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
            # ✅ ADD: Index for cancellation/rejection tracking
            models.Index(fields=['cancelled_by', 'cancelled_at']),
            models.Index(fields=['rejected_by', 'rejected_at']),
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
        
        # ✅ FIXED: Use the correct method name calculate_total_price
        return self.service_subtask.calculate_total_price(
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

    # ✅ ADD THESE METHODS to handle time slot parsing
    def get_start_time_from_slot(self):
        """Extract start time from time slot format '14:00-16:00'"""
        if self.time_slot and '-' in self.time_slot:
            return self.time_slot.split('-')[0].strip()
        return None

    def get_end_time_from_slot(self):
        """Extract end time from time slot format '14:00-16:00'"""
        if self.time_slot and '-' in self.time_slot:
            return self.time_slot.split('-')[1].strip()
        return None

    def get_status_display_color(self):
        """Return Bootstrap color class for status"""
        status_colors = {
            'pending_payment': 'warning',
            'pending': 'warning',
            'accepted': 'info',
            'rejected': 'danger',
            'cancelled': 'secondary',
            'completed': 'success',
            'expired': 'dark',
        }
        return status_colors.get(self.status, 'secondary')

    def can_be_completed(self):
        """Check if appointment can be marked as completed"""
        return (
            self.status == 'accepted' and 
            self.appointment_date and 
            self.appointment_date < timezone.now()
        )

    # ✅ UPDATED: Separate cancellation and rejection logic
    def can_be_cancelled_by_customer(self):
        """Check if customer can cancel this appointment"""
        return self.status in ['pending', 'accepted', 'pending_payment']

    def can_be_rejected_by_worker(self):
        """Check if worker can reject this appointment"""
        return self.status == 'pending'

    def cancel_by_customer(self, reason=""):
        """Cancel appointment by customer"""
        if not self.can_be_cancelled_by_customer():
            return False
        
        self.status = 'cancelled'
        self.cancelled_by = 'customer'
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save()
        return True

    def reject_by_worker(self, reason=""):
        """Reject appointment by worker"""
        if not self.can_be_rejected_by_worker():
            return False
        
        self.status = 'rejected'
        self.rejected_by = 'worker'
        self.rejected_at = timezone.now()
        self.rejection_reason = reason
        self.save()
        return True

    def accept_by_worker(self):
        """Accept appointment by worker"""
        if self.status != 'pending':
            return False
        
        self.status = 'accepted'
        self.save()
        return True

    def get_service_name(self):
        """Get the service name safely"""
        if self.service_subtask and self.service_subtask.subtask:
            return self.service_subtask.subtask.name
        return "General Service"

    def get_price_display(self):
        """Get formatted price display"""
        if self.total_price:
            return f"Rs{float(self.total_price):,.2f}"
        elif self.service_subtask:
            return f"Rs{float(self.service_subtask.price):,.2f}"
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
    
    def requires_payment(self):
        """Check if appointment requires payment"""
        return self.status == 'pending_payment'
    
    def get_payment_info(self):
        """Get payment information for this appointment"""
        try:
            from payments.models import Payment
            return Payment.objects.get(appointment=self)
        except Payment.DoesNotExist:
            return None

    def has_rated(self, customer=None):
        """Check if this appointment has been rated by the customer"""
        if customer is None:
            # If no customer provided, check if we can get it from the relationship
            if hasattr(self, 'customer'):
                customer = self.customer
            else:
                return False
        
        return WorkerRating.objects.filter(
            appointment=self,
            customer=customer
        ).exists()

    # ✅ NEW: Get cancellation/rejection details
    def get_cancellation_details(self):
        """Get formatted cancellation details"""
        if self.status != 'cancelled':
            return None
        
        details = {
            'by': self.cancelled_by,
            'at': self.cancelled_at,
            'reason': self.cancellation_reason or 'No reason provided'
        }
        
        if self.cancelled_by == 'customer':
            details['display_text'] = f"Cancelled by customer on {self.cancelled_at.strftime('%b %d, %Y at %I:%M %p')}"
        elif self.cancelled_by == 'worker':
            details['display_text'] = f"Cancelled by worker on {self.cancelled_at.strftime('%b %d, %Y at %I:%M %p')}"
        else:
            details['display_text'] = f"Cancelled on {self.cancelled_at.strftime('%b %d, %Y at %I:%M %p')}"
        
        return details

    def get_rejection_details(self):
        """Get formatted rejection details"""
        if self.status != 'rejected':
            return None
        
        details = {
            'by': self.rejected_by,
            'at': self.rejected_at,
            'reason': self.rejection_reason or 'No reason provided'
        }
        
        if self.rejected_by == 'worker':
            details['display_text'] = f"Rejected by worker on {self.rejected_at.strftime('%b %d, %Y at %I:%M %p')}"
        else:
            details['display_text'] = f"Rejected on {self.rejected_at.strftime('%b %d, %Y at %I:%M %p')}"
        
        return details

    # ✅ NEW: Check who can take action
    def can_customer_take_action(self, user):
        """Check if user (as customer) can take action on this appointment"""
        if not hasattr(user, 'customer'):
            return False
        return self.customer == user.customer and self.can_be_cancelled_by_customer()

    def can_worker_take_action(self, user):
        """Check if user (as worker) can take action on this appointment"""
        if not hasattr(user, 'worker'):
            return False
        return self.worker == user.worker and (
            self.can_be_rejected_by_worker() or 
            self.status == 'pending'
        )
# Worker Rating Model
class WorkerRating(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='ratings')
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='ratings')  # Remove null=True, blank=True
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='given_ratings')  # Remove null=True, blank=True
    rating = models.PositiveSmallIntegerField()  # Rating between 1 and 5
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # ✅ FIXED: One rating per customer per appointment
        unique_together = ('appointment', 'customer')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update worker's average rating when a new rating is added
        self.worker.update_average_rating()

    def __str__(self):
        return f"Rating {self.rating} by {self.customer.name} for {self.worker.name} (Appointment: {self.appointment.id})"

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('appointment_request', 'Appointment Request'),
        ('appointment_accepted', 'Appointment Accepted'),
        ('appointment_rejected', 'Appointment Rejected'),
        ('appointment_completed', 'Appointment Completed'),
        ('appointment_cancelled', 'Appointment Cancelled'),
        ('rating_received', 'Rating Received'),
        ('customer_completed', 'Customer Marked Completed'),
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

# ✅ NEW: Signal for customer completion notification
@receiver(post_save, sender=Appointment)
def create_customer_completion_notification(sender, instance, **kwargs):
    """
    Create notification when customer marks appointment as completed
    """
    # Check if customer_completed was just set to True
    if instance.customer_completed and instance.pk:
        try:
            # Get the previous state
            previous = Appointment.objects.get(pk=instance.pk)
            if not previous.customer_completed and instance.customer_completed:
                # Customer just marked as completed - notify worker
                Notification.objects.create(
                    worker=instance.worker,
                    notification_type='customer_completed',
                    title='Customer Marked Work as Completed',
                    message=f'{instance.customer.name} has marked the appointment as completed. Please confirm completion.',
                    appointment=instance
                )
                logger.info(f"Customer completion notification created for worker {instance.worker.name}")
        except Appointment.DoesNotExist:
            pass

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
        return f"{self.worker.name} - Rs{self.net_amount} - {self.payment_status}"

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