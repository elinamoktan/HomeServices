from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import re

User = get_user_model()

class SignupForm(forms.Form):
    """Custom signup form that matches our OTP flow"""
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email'
        }),
        label='Email Address'
    )
    
    password1 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a strong password',
            'autocomplete': 'new-password'
        }),
        label='Password',
        min_length=8,
        help_text='Password must be at least 8 characters long'
    )
    
    password2 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password'
        }),
        label='Confirm Password'
    )
    
    def clean_email(self):
        """Validate email and check if user already exists"""
        email = self.cleaned_data.get('email', '').lower().strip()
        
        print(f"🧪 FORM DEBUG: clean_email called with: '{email}'")
        
        if not email:
            raise ValidationError("Email is required.")
        
        # Email format validation
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValidationError("Please enter a valid email address.")
        
        # Check if user already exists - with detailed debugging
        User = get_user_model()
        
        print(f"🧪 FORM DEBUG: Checking if user exists for: '{email}'")
        
        # Multiple ways to check
        exists_filter = User.objects.filter(email=email).exists()
        exists_iexact = User.objects.filter(email__iexact=email).exists()
        
        print(f"🧪 FORM DEBUG: exists (filter): {exists_filter}")
        print(f"🧪 FORM DEBUG: exists (iexact): {exists_iexact}")
        
        # Check all users for debugging
        all_users = list(User.objects.all().values_list('email', flat=True))
        print(f"🧪 FORM DEBUG: All users in DB: {all_users}")
        
        if exists_filter or exists_iexact:
            print(f"🧪 FORM DEBUG: BLOCKING - User found in database")
            raise ValidationError("A user with this email already exists. Please try logging in.")
        
        print(f"🧪 FORM DEBUG: PROCEEDING - No user found")
        return email
        
    def clean_password1(self):
        """Password strength validation"""
        password1 = self.cleaned_data.get('password1')
        
        if len(password1) < 8:
            raise ValidationError("Password must be at least 8 characters long.")
        
        # Check for common patterns
        if password1.isnumeric():
            raise ValidationError("Password cannot be entirely numeric.")
        
        return password1
    
    def clean(self):
        """Validate that passwords match"""
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise ValidationError("Passwords do not match.")
        
        return cleaned_data

class OTPVerificationForm(forms.Form):
    """Form for OTP verification"""
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center',
            'placeholder': '000000',
            'autocomplete': 'off',
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
            'maxlength': '6'
        }),
        label='Enter OTP Code',
        help_text='Enter the 6-digit code sent to your email'
    )
    
    def clean_otp(self):
        """Validate OTP format"""
        otp = self.cleaned_data.get('otp', '').strip()
        if not otp.isdigit():
            raise ValidationError("OTP must contain only numbers.")
        if len(otp) != 6:
            raise ValidationError("OTP must be exactly 6 digits.")
        return otp