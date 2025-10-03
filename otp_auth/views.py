from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_protect
from .models import OTP
from .forms import OTPVerificationForm
from .utils import send_otp_via_email

@csrf_protect
def verify_signup_otp(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        otp_code = form.cleaned_data["otp"]
        
        # Get the latest OTP for this user and purpose
        otp_obj = OTP.objects.filter(user=user, purpose="signup").order_by('-created_at').first()
        
        if otp_obj and otp_obj.is_valid() and otp_obj.code == otp_code:
            # OTP is valid - activate user and log them in
            user.is_active = True
            user.save()
            
            # Delete the used OTP
            otp_obj.delete()
            
            # Log the user in
            login(request, user)
            messages.success(request, "Signup successful! You are now logged in.")
            return redirect("landing-page")
        else:
            messages.error(request, "Invalid or expired OTP. Please try again.")
    
    # If GET request or invalid form, show the verification page
    context = {
        'form': form,
        'user_email': user.email
    }
    return render(request, "otp_auth/verify_signup_otp.html", context)

@csrf_protect
def verify_login_otp(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        otp_code = form.cleaned_data["otp"]
        
        # Get the latest OTP for this user and purpose
        otp_obj = OTP.objects.filter(user=user, purpose="login").order_by('-created_at').first()
        
        if otp_obj and otp_obj.is_valid() and otp_obj.code == otp_code:
            # OTP is valid - log the user in
            login(request, user)
            
            # Delete the used OTP
            otp_obj.delete()
            
            messages.success(request, "Login successful!")
            return redirect("landing-page")
        else:
            messages.error(request, "Invalid or expired OTP. Please try again.")
    
    context = {
        'form': form,
        'user_email': user.email
    }
    return render(request, "otp_auth/verify_login_otp.html", context)

# Helper function to initiate OTP flow
def send_otp_and_redirect(user, purpose, request):
    """Create OTP, send email, and redirect to verification page"""
    otp = OTP.create_otp(user, purpose)
    send_otp_via_email(user, otp.code, purpose)
    
    if purpose == "signup":
        return redirect('otp_auth:verify_signup_otp', user_id=user.id)
    else:  # login
        return redirect('otp_auth:verify_login_otp', user_id=user.id)