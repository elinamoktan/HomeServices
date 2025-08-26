from django.db import models
from django.contrib.auth import get_user_model
from phonenumber_field.modelfields import PhoneNumberField
from django.utils import timezone
from django.db.models import Count, Sum, Q, Avg  # Added Avg import
from django.contrib.auth.models import User  # Moved this import up

User = get_user_model()

# Create your models here.
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
    latitude = models.CharField(max_length=20, null=True, blank=True)
    longitude = models.CharField(max_length=20, null=True, blank=True)
    appointed = models.BooleanField(default=False)
    appointment_date = models.DateTimeField(null=True, blank=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_ratings = models.PositiveIntegerField(default=0)
    rating_count = models.PositiveIntegerField(default=0)

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
        from .models import WorkerRating  # Import here to avoid circular import
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

    def __str__(self):
        return f"{self.name} - {self.tagline}"


class Customer(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    phone_number = PhoneNumberField(region="NP", unique=True)
    profile_pic = models.ImageField(upload_to="profiles/", blank=True)
    latitude = models.CharField(max_length=20, null=True, blank=True)
    longitude = models.CharField(max_length=20, null=True, blank=True)

    def __str__(self):
        return f"{self.id} | {self.name}"


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='customer_appointments')
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name='worker_appointments')
    appointment_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Appointment with {self.worker} on {self.appointment_date}"


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


SERVICE_CATEGORIES = [
    ('PL', 'Plumber'),
    ('EL', 'Electrician'),
    ('CA', 'Carpenter'),
    ('CL', 'Cleaner'),
    ('ME', 'Mechanic'),
    ('PA', 'Painter'),
    ('AC', 'AC Repair'),
    ('IT', 'IT Support'),
    ('D', 'Driver'),
]

class Service(models.Model):
    title = models.CharField(max_length=100)
    category = models.CharField(choices=SERVICE_CATEGORIES, max_length=2)
    description = models.TextField()
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, help_text="Cost per hour in INR")
    estimated_time_hours = models.DecimalField(max_digits=4, decimal_places=2, help_text="Approximate time required in hours")
    image = models.ImageField(upload_to='service_images/', blank=True, null=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} - {self.get_category_display()}"

    @property
    def total_estimated_cost(self):
        return round(self.hourly_rate * self.estimated_time_hours, 2)