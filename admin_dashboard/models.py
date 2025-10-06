from django.db import models
from django.contrib.auth import get_user_model
from jobs.models import Worker, Customer, Appointment, WorkerRating, Service, WorkerService, WorkerSubTaskPricing, ServiceCategory, SubTask, Notification, FavoriteWorker

User = get_user_model()

class AdminDashboardSettings(models.Model):
    site_name = models.CharField(max_length=100, default="BlueCollar Admin")
    maintenance_mode = models.BooleanField(default=False)
    max_workers_per_customer = models.PositiveIntegerField(default=5)
    platform_commission = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Admin Dashboard Settings"

class AdminActivityLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.admin_user.username} - {self.action} - {self.model_name}"