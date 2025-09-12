# models.py - Enhanced with Notification System and Dynamic Pricing
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Avg, Count
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

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
    
    def __str__(self):
        return self.name

# Services
class Service(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=100)
    description = models.TextField()
    base_pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES)
    image = models.ImageField(upload_to='service_images/', blank=True, null=True)
    
    def __str__(self):
        return f"{self.category.name} - {self.name}"

# Service SubTasks
class SubTask(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='subtasks')
    name = models.CharField(max_length=100)
    description = models.TextField()
    default_pricing_type = models.CharField(max_length=20, choices=PRICING_TYPES)
    
    def __str__(self):
        return f"{self.service.name} - {self.name}"

# Worker Model
class Worker(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    phone_number = PhoneNumberField(region="NP", unique=True)
    tagline = models.CharField(max_length=100)
    bio = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to="profiles/", blank=True)
    verified = models.BooleanField(default=False)
    citizenship_image = models.ImageField(upload_to='citizenship/', blank=True, null=True)
    certificate_file = models.FileField(upload_to='certificates/', blank=True, null=True)
    appointed = models.BooleanField(default=False)
    appointment_date = models.DateTimeField(null=True, blank=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_ratings = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default=SHIFT_ALL)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

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
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('worker', 'service')
    
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
    
    class Meta:
        unique_together = ('worker_service', 'subtask')
    
    def __str__(self):
        return f"{self.worker_service.worker.name} - {self.subtask.name}: ₹{self.price}"
    
    def get_pricing_type_display(self):
        return dict(PRICING_TYPES).get(self.pricing_type, self.pricing_type)

# Customer Model
class Customer(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    phone_number = PhoneNumberField(region="NP", unique=True)
    profile_pic = models.ImageField(upload_to="profiles/", blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def get_unread_notification_count(self):
        """Get count of unread notifications for this customer"""
        return self.notifications.filter(is_read=False).count()

    def __str__(self):
        return f"{self.id} | {self.name}"

# Appointment Model
class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    SHIFT_TYPES = [
        ('day', 'Day Shift'),
        ('night', 'Night Shift'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='customer_appointments')
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='worker_appointments')
    service_subtask = models.ForeignKey(WorkerSubTaskPricing, on_delete=models.SET_NULL, null=True, blank=True)
    appointment_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    shift_type = models.CharField(max_length=10, choices=SHIFT_TYPES, default='day')
    location = models.TextField(blank=True, null=True)
    special_instructions = models.TextField(blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    customer_completed = models.BooleanField(default=False)
    worker_completed = models.BooleanField(default=False)
    customer_latitude = models.FloatField(null=True, blank=True)
    customer_longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_worker_completed(self):
        """
        Business rule: worker can't mark completed until customer_completed is True.
        Use this helper from views instead of touching worker_completed directly.
        """
        if not self.customer_completed:
            raise ValueError("Customer must mark appointment completed first.")
        self.worker_completed = True
        self.save()

    def __str__(self):
        return f"Appointment with {self.worker} on {self.appointment_date}"

# Worker Rating Model
class WorkerRating(models.Model):
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='ratings')
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='given_ratings', null=True, blank=True)
    rating = models.PositiveSmallIntegerField()  # Rating between 1 and 5
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('worker', 'appointment', 'customer')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update worker's average rating when a new rating is added
        self.worker.update_average_rating()

    def __str__(self):
        return f"Rating {self.rating} by {self.customer.name if self.customer else 'Unknown'} for {self.worker.name}"

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
    title = models.CharField(max_length=100)
    message = models.TextField()
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        recipient = self.worker or self.customer
        return f"Notification for {recipient} - {self.title}"

    def mark_as_read(self):
        self.is_read = True
        self.save()