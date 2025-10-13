import random
import string
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)

class OTP(models.Model):
    PURPOSE_CHOICES = [
        ("signup", "Signup"),
        ("login", "Login"),
    ]

    # Make user optional for signup OTP
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField()  # Add email field for signup OTP
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=10, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return timezone.now() < self.expires_at

    @staticmethod
    def generate_code():
        return "".join(random.choices(string.digits, k=6))

    @classmethod
    def create_otp(cls, email, purpose, user=None):
        # IMPORTANT: Check if user already exists for signup OTP
        User = get_user_model()
        email = email.lower().strip()
        
        # For signup OTP, verify that no user exists with this email
        if purpose == "signup":
            if User.objects.filter(email=email).exists():
                logger.error(f"Attempt to create signup OTP for existing user: {email}")
                raise ValueError(f"A user with email {email} already exists. Cannot create signup OTP.")
        
        # Delete any existing OTPs for this email and purpose
        deleted_count = cls.objects.filter(email=email, purpose=purpose).delete()[0]
        logger.info(f"Deleted {deleted_count} existing OTPs for {email} ({purpose})")
        
        code = cls.generate_code()
        otp = cls.objects.create(
            user=user,
            email=email,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        logger.info(f"Created OTP for {email} ({purpose}): {code}")
        return otp

    def __str__(self):
        return f"{self.email} - {self.code} ({self.purpose})"

    class Meta:
        # Add index for better performance
        indexes = [
            models.Index(fields=['email', 'purpose', 'created_at']),
            models.Index(fields=['expires_at']),
        ]