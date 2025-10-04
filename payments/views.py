import requests
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.conf import settings
from jobs.models import Appointment
from .models import Payment

# Khalti configuration
KHALTI_SECRET_KEY = getattr(settings, 'KHALTI_SECRET_KEY', 'test_secret_key_xxx')
KHALTI_BASE_URL = "https://dev.khalti.com/api/v2/epayment"  # Use live URL in production

@login_required
def checkout_page(request, appointment_id):
    """Enhanced checkout page with Khalti payment"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    # Create or get payment record
    payment, created = Payment.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': appointment.total_price or 100.00,
            'prepayment_amount': 100.00  # Fixed 100 rupees prepayment
        }
    )
    
    context = {
        'appointment': appointment,
        'payment': payment,
        'khalti_public_key': getattr(settings, 'KHALTI_PUBLIC_KEY', 'test_public_key_xxx'),
    }
    return render(request, 'payments/checkout.html', context)

@csrf_exempt
@login_required
def initiate_khalti_payment(request, appointment_id):
    """Initiate Khalti payment"""
    if request.method == "POST":
        try:
            appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
            payment = get_object_or_404(Payment, appointment=appointment)
            
            # Khalti payment payload
            payload = {
                "return_url": request.build_absolute_uri(f'/payments/success/{appointment.id}/'),
                "website_url": request.build_absolute_uri('/'),
                "amount": int(payment.prepayment_amount * 100),  # Convert to paisa
                "purchase_order_id": str(appointment.id),
                "purchase_order_name": f"Appointment_{appointment.id}",
                "customer_info": {
                    "name": appointment.customer.name,
                    "email": appointment.customer.owner.email,
                    "phone": str(appointment.customer.phone_number)
                }
            }
            
            headers = {
                "Authorization": f"Key {KHALTI_SECRET_KEY}",
                "Content-Type": "application/json",
            }
            
            # Make request to Khalti
            response = requests.post(
                f"{KHALTI_BASE_URL}/initiate/",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                # Store Khalti token for verification
                payment.khalti_token = data.get('token')
                payment.save()
                
                return JsonResponse({
                    'success': True,
                    'payment_url': data['payment_url'],
                    'pidx': data.get('pidx')
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Payment initiation failed',
                    'details': response.text
                }, status=400)
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@csrf_exempt
def khalti_callback(request):
    """Handle Khalti payment callback"""
    if request.method == "GET":
        token = request.GET.get('token')
        
        if not token:
            return render(request, 'payments/payment_failed.html', {
                'error': 'No token provided'
            })
        
        # Verify payment with Khalti
        headers = {
            "Authorization": f"Key {KHALTI_SECRET_KEY}",
        }
        
        response = requests.get(
            f"{KHALTI_BASE_URL}/lookup/",
            headers=headers,
            params={'token': token}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            try:
                # Find payment by token
                payment = Payment.objects.get(khalti_token=token)
                appointment = payment.appointment
                
                if data['status'] == 'Completed':
                    # Update payment status
                    payment.payment_status = 'completed'
                    payment.khalti_transaction_id = data['idx']
                    payment.paid_at = timezone.now()
                    payment.save()
                    
                    # Update appointment status
                    appointment.status = 'accepted'  # Auto-accept after payment
                    appointment.save()
                    
                    return render(request, 'payments/payment_success.html', {
                        'appointment': appointment,
                        'payment': payment,
                        'transaction_id': data['idx']
                    })
                else:
                    payment.payment_status = 'failed'
                    payment.save()
                    return render(request, 'payments/payment_failed.html', {
                        'error': 'Payment was not completed'
                    })
                    
            except Payment.DoesNotExist:
                return render(request, 'payments/payment_failed.html', {
                    'error': 'Payment record not found'
                })
        
        return render(request, 'payments/payment_failed.html', {
            'error': 'Payment verification failed'
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def payment_success(request, appointment_id):
    """Payment success page"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    payment = get_object_or_404(Payment, appointment=appointment)
    
    return render(request, 'payments/payment_success.html', {
        'appointment': appointment,
        'payment': payment
    })

@login_required
def payment_failed(request, appointment_id):
    """Payment failed page"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    return render(request, 'payments/payment_failed.html', {
        'appointment': appointment
    })