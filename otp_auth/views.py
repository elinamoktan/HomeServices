from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_protect
from django.http import JsonResponse
from django.db import IntegrityError, transaction
from django.contrib.auth import get_user_model
from django.core.cache import cache
from .models import OTP
from .forms import OTPVerificationForm, SignupForm
from .utils import send_otp_via_email, is_rate_limited, clear_rate_limit
import logging
import time

# Use the custom user model
User = get_user_model()
logger = logging.getLogger(__name__)


def get_signup_lock_key(email):
    """Get cache key for signup lock"""
    return f"signup_lock_{email.lower()}"


def acquire_signup_lock(email, timeout=60):
    """
    Acquire a lock for signup process to prevent concurrent attempts
    Returns True if lock acquired, False if already locked
    """
    lock_key = get_signup_lock_key(email)
    return cache.add(lock_key, True, timeout)


def release_signup_lock(email):
    """Release signup lock"""
    lock_key = get_signup_lock_key(email)
    cache.delete(lock_key)


@csrf_protect
def send_signup_otp(request):
    """View to send OTP during signup"""
    if request.method == "POST":
        form = SignupForm(request.POST)
        
        if form.is_valid():
            # Get cleaned data from form
            email = form.cleaned_data['email'].lower().strip()
            password = form.cleaned_data['password1']
            
            logger.info(f"Starting signup process for: {email}")
            
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                logger.warning(f"Signup attempt for existing user: {email}")
                messages.error(
                    request, 
                    f"A user with email {email} already exists. Please try logging in."
                )
                return redirect('account_signup')
            
            # Rate limiting check
            if is_rate_limited(f"signup_attempt_{email}"):
                messages.error(
                    request, 
                    "Too many signup attempts. Please try again in 5 minutes."
                )
                return redirect('account_signup')
            
            # Acquire lock to prevent concurrent signup attempts
            if not acquire_signup_lock(email):
                messages.error(request, "A signup process is already in progress for this email. Please wait a moment.")
                return redirect('account_signup')
            
            try:
                # Create OTP for signup
                otp = OTP.create_otp(email=email, purpose="signup")
                
                # Send OTP email
                if send_otp_via_email(email, otp.code, "signup"):
                    # Store all necessary data in session
                    request.session['signup_email'] = email
                    request.session['signup_data'] = {
                        'password1': password,
                        'created_at': time.time(),
                    }
                    # Set session expiry (10 minutes)
                    request.session.set_expiry(600)
                    request.session.modified = True
                    
                    logger.info(f"OTP sent successfully to: {email}")
                    messages.success(request, f"OTP sent to {email}. Please check your email.")
                    return redirect('otp_auth:verify_signup_otp')
                else:
                    logger.error(f"Failed to send OTP email to: {email}")
                    messages.error(request, "Failed to send OTP email. Please try again.")
                    return redirect('account_signup')
                    
            except ValueError as e:
                logger.error(f"OTP creation error for {email}: {e}")
                messages.error(request, str(e))
                return redirect('account_signup')
            except Exception as e:
                logger.error(f"Error in send_signup_otp for {email}: {str(e)}")
                messages.error(request, "An error occurred. Please try again.")
                return redirect('account_signup')
            finally:
                release_signup_lock(email)
        else:
            # Form is invalid - show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect('account_signup')
    
    return redirect('account_signup')


@csrf_protect
def verify_signup_otp(request):
    """View to verify OTP and create user account"""
    # Check if signup session exists
    if 'signup_email' not in request.session:
        messages.error(request, "Session expired. Please start signup again.")
        return redirect('account_signup')
    
    # Get session data
    email = request.session.get('signup_email')
    user_data = request.session.get('signup_data', {})
    
    logger.info(f"Verifying OTP for: {email}")
    
    # Check session age (prevent stale sessions)
    session_created_at = user_data.get('created_at', 0)
    if time.time() - session_created_at > 600:  # 10 minutes
        messages.error(request, "Session expired. Please start signup again.")
        clean_signup_session(request)
        return redirect('account_signup')
    
    # Validate that we have all required data
    if not user_data or not user_data.get('password1'):
        logger.error("Missing required data in session")
        messages.error(request, "Session data missing. Please start signup again.")
        clean_signup_session(request)
        return redirect('account_signup')
    
    # Check user existence again before showing verification form
    if User.objects.filter(email=email).exists():
        logger.warning(f"User already exists during OTP verification: {email}")
        messages.error(request, "A user with this email already exists. Please try logging in.")
        clean_signup_session(request)
        clear_rate_limit(f"signup_attempt_{email}")
        return redirect('account_signup')
    
    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        otp_code = form.cleaned_data["otp"]
        
        # Acquire lock for the final user creation step
        if not acquire_signup_lock(email, timeout=30):
            messages.error(request, "Another signup process is in progress. Please wait a moment.")
            return render(request, "otp_auth/verify_signup_otp.html", {
                'form': form,
                'user_email': email
            })
        
        try:
            # Get the latest OTP for this email and purpose
            otp_obj = OTP.objects.filter(
                email=email, 
                purpose="signup"
            ).order_by('-created_at').first()
            
            if not otp_obj:
                logger.error(f"No OTP found for: {email}")
                messages.error(request, "No OTP found. Please request a new one.")
                return render(request, "otp_auth/verify_signup_otp.html", {
                    'form': form,
                    'user_email': email
                })
            
            if not otp_obj.is_valid():
                logger.error(f"OTP expired for: {email}")
                messages.error(request, "OTP has expired. Please request a new one.")
                otp_obj.delete()
                return render(request, "otp_auth/verify_signup_otp.html", {
                    'form': form,
                    'user_email': email
                })
            
            if otp_obj.code != otp_code:
                logger.error(f"Invalid OTP for: {email}")
                messages.error(request, "Invalid OTP code. Please try again.")
                return render(request, "otp_auth/verify_signup_otp.html", {
                    'form': form,
                    'user_email': email
                })
            
            # OTP is valid - proceed with user creation
            logger.info(f"OTP verified for: {email}. Creating user...")
            
            # Store user object outside transaction
            created_user = None
            
            try:
                with transaction.atomic():
                    # Final user existence check within transaction
                    if User.objects.filter(email=email).select_for_update().exists():
                        logger.error(f"User already exists (final check): {email}")
                        messages.error(request, "A user with this email already exists. Please try logging in.")
                        otp_obj.delete()
                        clean_signup_session(request)
                        clear_rate_limit(f"signup_attempt_{email}")
                        return redirect('account_signup')
                    
                    # Extract data from session
                    password = user_data['password1']
                    
                    if not password:
                        messages.error(request, "Password is missing. Please start signup again.")
                        clean_signup_session(request)
                        return redirect('account_signup')
                    
                    # Create user using your custom user model
                    try:
                        # Try create_user method first
                        created_user = User.objects.create_user(
                            email=email,
                            password=password,
                            is_active=True
                        )
                        logger.info(f"User created successfully: {created_user.email}")
                    except TypeError:
                        # If create_user expects username, use alternative method
                        logger.info(f"Using alternative user creation method for: {email}")
                        
                        # Generate unique username from email
                        username = email.split('@')[0]
                        base_username = username
                        counter = 1
                        
                        # Ensure username is unique
                        while User.objects.filter(username=username).exists():
                            username = f"{base_username}{counter}"
                            counter += 1
                        
                        created_user = User.objects.create(
                            email=email,
                            username=username,
                            is_active=True
                        )
                        created_user.set_password(password)
                        created_user.save()
                        logger.info(f"User created via alternative method: {created_user.email}")
                    
                    # Verify user was actually created
                    if not User.objects.filter(id=created_user.id).exists():
                        logger.error(f"User creation failed for: {email}")
                        messages.error(request, "Failed to create user account. Please try again.")
                        return redirect('account_signup')
                    
                    # Delete the used OTP
                    otp_obj.delete()
                
                # Transaction completed successfully
                # Clear rate limit on successful signup
                clear_rate_limit(f"signup_attempt_{email}")
                
                # Clean up session BEFORE login to avoid conflicts
                clean_signup_session(request)
                
                # Log the user in with explicit backend
                login(request, created_user, backend='django.contrib.auth.backends.ModelBackend')
                logger.info(f"User logged in successfully: {created_user.email}")
                
                messages.success(request, "Account created successfully! Welcome to HomeServices.")
                # REDIRECT TO ACCOUNT SETUP PAGE INSTEAD OF LANDING PAGE
                return redirect("http://127.0.0.1:8000/account-setup/")
                
            except IntegrityError as e:
                logger.error(f"Integrity error creating user {email}: {e}")
                messages.error(request, "A user with this email already exists. Please try logging in.")
                if otp_obj and hasattr(otp_obj, 'id'):
                    otp_obj.delete()
                clean_signup_session(request)
                clear_rate_limit(f"signup_attempt_{email}")
                return redirect('account_signup')
            except Exception as e:
                logger.error(f"Error creating user {email}: {str(e)}")
                messages.error(request, "An error occurred while creating your account. Please try again.")
                return redirect('account_signup')
                
        finally:
            release_signup_lock(email)
    
    context = {
        'form': form,
        'user_email': email
    }
    return render(request, "otp_auth/verify_signup_otp.html", context)


@csrf_protect
def verify_login_otp(request, user_id):
    """View to verify OTP for login"""
    user = get_object_or_404(User, id=user_id)
    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        otp_code = form.cleaned_data["otp"]
        
        # Get the latest OTP for this user and purpose
        otp_obj = OTP.objects.filter(
            user=user, 
            purpose="login"
        ).order_by('-created_at').first()
        
        if otp_obj and otp_obj.is_valid() and otp_obj.code == otp_code:
            # OTP is valid - log the user in
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            # Delete the used OTP
            otp_obj.delete()
            
            messages.success(request, "Login successful!")
            # REDIRECT TO ACCOUNT SETUP PAGE INSTEAD OF LANDING PAGE
            return redirect("http://127.0.0.1:8000/account-setup/")
        else:
            messages.error(request, "Invalid or expired OTP. Please try again.")
    
    context = {
        'form': form,
        'user_email': user.email
    }
    return render(request, "otp_auth/verify_login_otp.html", context)


def clean_signup_session(request):
    """Helper function to clean up signup session data"""
    request.session.pop('signup_email', None)
    request.session.pop('signup_data', None)
    request.session.modified = True


@csrf_protect
def check_email_availability(request):
    """AJAX endpoint to check email availability"""
    if request.method == "POST":
        email = request.POST.get('email', '').lower().strip()
        
        if not email:
            return JsonResponse({'available': False, 'error': 'Email is required'})
        
        # Check if user exists
        if User.objects.filter(email=email).exists():
            return JsonResponse({'available': False, 'error': 'Email already registered'})
        
        # Check rate limiting
        if is_rate_limited(f"signup_attempt_{email}"):
            return JsonResponse({
                'available': False, 
                'error': 'Too many attempts. Please wait before trying again.'
            })
        
        return JsonResponse({'available': True})
    
    return JsonResponse({'available': False, 'error': 'Invalid request'})