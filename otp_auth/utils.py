from django.core.mail import send_mail
from django.conf import settings

def send_otp_via_email(user, otp_code, purpose):
    if purpose == "signup":
        subject = "Verify Your Email - OTP Code"
        message = f"""
        Welcome to JobHub! 
        
        Your OTP code for email verification is: {otp_code}
        
        This code will expire in 5 minutes.
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
        message, 
        settings.DEFAULT_FROM_EMAIL, 
        [user.email],
        fail_silently=False
    )