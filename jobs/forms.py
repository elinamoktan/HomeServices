from django import forms
from .models import Worker, Appointment, Customer

class WorkerForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = [
            'name',
            'profile_pic', 
            'tagline',
            'phone_number',
            'bio',
            'citizenship_image',
            'certificate_file',
            'shift',
            'latitude',
            'longitude',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4}),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make profile pic optional
        self.fields['profile_pic'].required = False
        self.fields['citizenship_image'].required = True
        self.fields['certificate_file'].required = False

class WorkerProfileForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = [
            'name',
            'profile_pic',
            'tagline', 
            'phone_number',
            'bio',
            'shift',
            'latitude',
            'longitude',
        ]
        widgets = {
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

class AppointmentLocationForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = [
            'location',
            'customer_latitude', 
            'customer_longitude',
        ]
        widgets = {
            'customer_latitude': forms.HiddenInput(),
            'customer_longitude': forms.HiddenInput(),
        }

# Add CustomerForm if needed
class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'name',
            'profile_pic',
            'phone_number', 
            'latitude',
            'longitude',
        ]
        widgets = {
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }