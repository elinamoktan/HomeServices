from django import forms

class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter 6-digit OTP", 
            "class": "form-input",
            "pattern": "[0-9]{6}",
            "title": "Please enter exactly 6 digits"
        }),
        error_messages={
            'required': 'OTP code is required',
            'min_length': 'OTP must be exactly 6 digits',
            'max_length': 'OTP must be exactly 6 digits'
        }
    )