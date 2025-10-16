from django.db import models
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

# Configure logging
logger = logging.getLogger(__name__)

User = get_user_model()

class AdminDashboardSettings(models.Model):
    site_name = models.CharField(max_length=100, default="BlueCollar Admin")
    maintenance_mode = models.BooleanField(default=False)
    max_workers_per_customer = models.PositiveIntegerField(default=5)
    platform_commission = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    
    # Email settings for notifications
    email_notifications_enabled = models.BooleanField(default=True)
    admin_email = models.EmailField(default='admin@bluecaller.com')
    support_email = models.EmailField(default='support@bluecaller.com')
    email_from_name = models.CharField(max_length=100, default='BlueCaller Team')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Admin Dashboard Settings"
    
    def send_worker_verification_email(self, worker, approved, rejection_reason=None):
        """Send verification email to worker"""
        if not self.email_notifications_enabled:
            logger.info("Email notifications are disabled in settings")
            return False
            
        try:
            if approved:
                subject = f"🎉 Your {self.site_name} Worker Profile Has Been Approved!"
                template_name = 'admin_dashboard/emails/worker_approved.html'
            else:
                subject = f"📋 Update on Your {self.site_name} Worker Profile Verification"
                template_name = 'admin_dashboard/emails/worker_rejected.html'
            
            context = {
                'worker': worker,
                'approved': approved,
                'rejection_reason': rejection_reason,
                'site_name': self.site_name,
                'support_email': self.support_email,
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            }
            
            # Render HTML email template
            html_message = render_to_string(template_name, context)
            plain_message = strip_tags(html_message)
            
            from_email = f"{self.email_from_name} <{self.admin_email}>"
            recipient_list = [worker.owner.email]
            
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
            )
            
            logger.info(f"Verification email sent to {worker.name} ({worker.owner.email}) - Approved: {approved}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send verification email to {worker.name}: {str(e)}")
            return False

class AdminActivityLog(models.Model):
    # ✅ FIXED: Changed to UPPERCASE to match what views.py is using
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('VERIFY', 'Verify'),
        ('REJECT', 'Reject'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE)
    # ✅ FIXED: Increased max_length to 20 to accommodate longer action names
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    
    # Additional fields for better tracking
    email_sent = models.BooleanField(default=False)
    email_recipient = models.EmailField(blank=True, null=True)
    metadata = models.JSONField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin_user', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def __str__(self):
        return f"{self.admin_user.username} - {self.action} - {self.model_name}"

class EmailTemplate(models.Model):
    TEMPLATE_TYPES = [
        ('worker_approved', 'Worker Approved'),
        ('worker_rejected', 'Worker Rejected'),
        ('appointment_confirmed', 'Appointment Confirmed'),
        ('appointment_cancelled', 'Appointment Cancelled'),
    ]
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES, unique=True)
    subject = models.CharField(max_length=200)
    html_content = models.TextField()
    plain_text_content = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.template_type})"

class WorkerNotificationSettings(models.Model):
    worker = models.OneToOneField('jobs.Worker', on_delete=models.CASCADE, related_name='notification_settings')
    email_verification_updates = models.BooleanField(default=True)
    email_appointment_requests = models.BooleanField(default=True)
    email_appointment_updates = models.BooleanField(default=True)
    email_promotions = models.BooleanField(default=False)
    sms_notifications = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Notification Settings - {self.worker.name}"