import random
import string
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone

class OTP(models.Model):
    PURPOSE_CHOICES = [
        ("signup", "Signup"),
        ("login", "Login"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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
    def create_otp(cls, user, purpose):
        # Delete any existing OTPs for this user and purpose
        cls.objects.filter(user=user, purpose=purpose).delete()
        
        code = cls.generate_code()
        otp = cls.objects.create(
            user=user,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        return otp

    def __str__(self):
        return f"{self.user.email} - {self.code} ({self.purpose})"