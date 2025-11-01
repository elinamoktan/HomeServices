from django.db import models
from django.conf import settings
from jobs.models import Appointment
from django.utils import timezone 
class Payment(models.Model):
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('partially_paid', 'Partially Paid'),
    ]
    
    PAYMENT_TYPE = [
        ('full', 'Full Payment'),
        ('hybrid', 'Hybrid Payment'),
    ]
    
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    prepayment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=50.00)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE, default='hybrid')
    khalti_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    khalti_token = models.CharField(max_length=255, blank=True, null=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    initial_payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    final_payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    paid_at = models.DateTimeField(null=True, blank=True)
    final_payment_paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    khalti_initial_token = models.CharField(max_length=255, blank=True, null=True)  # ADD THIS
    khalti_final_token = models.CharField(max_length=255, blank=True, null=True)    # ADD THIS
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Payment {self.id} - {self.appointment.customer.name} - Rs{self.amount}"
    
    def save(self, *args, **kwargs):
        # Calculate remaining amount when saving
        if self.amount and self.prepayment_amount:
            self.remaining_amount = self.amount - self.prepayment_amount
        super().save(*args, **kwargs)
    
    def mark_initial_payment_completed(self):
        """Mark initial payment as completed"""
        self.initial_payment_status = 'completed'
        self.payment_status = 'partially_paid'
        self.paid_at = timezone.now()
        self.save()
        
        # Update appointment status
        self.appointment.status = 'pending'  # Change from pending_payment to pending
        self.appointment.save()
    
    def mark_final_payment_completed(self):
        """Mark final payment as completed"""
        self.final_payment_status = 'completed'
        self.payment_status = 'completed'
        self.final_payment_paid_at = timezone.now()
        self.save()

        