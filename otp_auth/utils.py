from django.core.mail import send_mail
from django.conf import settings
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

def send_otp_via_email(email, otp_code, purpose):
    try:
        if purpose == "signup":
            subject = "Verify Your Email - OTP Code"
            message = f"""
            Welcome to HomeServices! 
            
            Your OTP code for email verification is: {otp_code}
            
            This code will expire in 5 minutes.
            
            If you didn't request this signup, please ignore this email.
            """
        else:  # login
            subject = "Login Verification - OTP Code"
            message = f"""
            Your OTP code for login is: {otp_code}
            
            This code will expire in 5 minutes.
            
            If you didn't request this login, please secure your account.
            """
        
        send_mail(
            subject, 
            message.strip(),
            settings.DEFAULT_FROM_EMAIL, 
            [email],
            fail_silently=False
        )
        logger.info(f"OTP email sent successfully to {email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send OTP email to {email}: {e}")
        return False

def is_rate_limited(key, limit=3, window=300):
    """
    Check if a request should be rate limited
    """
    cache_key = f"rate_limit_{key}"
    attempts = cache.get(cache_key, 0)
    
    if attempts >= limit:
        return True
    
    cache.set(cache_key, attempts + 1, window)
    return False

def get_remaining_attempts(key, limit=3):
    """
    Get remaining attempts for a key
    """
    cache_key = f"rate_limit_{key}"
    attempts = cache.get(cache_key, 0)
    return max(0, limit - attempts)

def clear_rate_limit(key):
    """
    Clear rate limit for a key
    """
    cache_key = f"rate_limit_{key}"
    cache.delete(cache_key)