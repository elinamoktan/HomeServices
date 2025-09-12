from django import forms
from .models import Worker, Appointment

class WorkerProfileForm(forms.ModelForm):
    class Meta:
        model = Worker
        fields = [
            # ...existing worker fields...
            'shift',
            'latitude',
            'longitude',
        ]

class AppointmentLocationForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = [
            # ...existing appointment fields...
            'customer_latitude',
            'customer_longitude',
        ]
        widgets = {
            'customer_latitude': forms.HiddenInput(),
            'customer_longitude': forms.HiddenInput(),
        }