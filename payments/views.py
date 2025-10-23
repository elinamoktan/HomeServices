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


def get_khalti_config():
    """Get Khalti configuration based on environment"""
    from django.conf import settings
    config = settings.KHALTI_CONFIG[settings.KHALTI_ENVIRONMENT]  # ✅ Now uses lowercase
    return config

@login_required
def checkout_page(request, appointment_id):
    """Enhanced checkout page with hybrid payment option"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    # Calculate total amount based on service
    total_amount = 100.00  # Default amount, replace with your logic
    if appointment.service_subtask and appointment.service_subtask.price:
        total_amount = float(appointment.service_subtask.price)
    
    # Create or get payment record with hybrid payment
    payment, created = Payment.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': total_amount,
            'prepayment_amount': 50.00,  # Fixed 50 rupees prepayment
            'payment_type': 'hybrid',
            'remaining_amount': total_amount - 50.00
        }
    )
    
    context = {
        'appointment': appointment,
        'payment': payment,
        'khalti_public_key': getattr(settings, 'KHALTI_PUBLIC_KEY', 'test_public_key_xxx'),
    }
    return render(request, 'payments/checkout.html', context)

@login_required
def booking_success(request):
    """Display booking success page after payment"""
    return render(request, 'payments/booking_success.html')
@csrf_exempt
@login_required
def initiate_khalti_payment(request, appointment_id):
    """Initiate Khalti payment with proper configuration"""
    try:
        config = get_khalti_config()
        
        appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
        
        payload = {
            "return_url": request.build_absolute_uri('/payments/khalti-callback/'),
            "website_url": request.build_absolute_uri('/'),
            "amount": 5000,  # 50 rupees in paisa
            "purchase_order_id": f"booking_{appointment.id}",
            "purchase_order_name": f"Service Booking - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}",
            "customer_info": {
                "name": appointment.customer.name,
                "email": appointment.customer.owner.email,
                "phone": str(appointment.customer.phone_number or "9800000000")
            }
        }
        
        headers = {
            "Authorization": f"Key {config['SECRET_KEY']}",
            "Content-Type": "application/json",
        }
        
        # Make request to Khalti
        response = requests.post(
            f"{config['BASE_URL']}/epayment/initiate/",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
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
@csrf_exempt
def khalti_callback(request):
    """Handle Khalti payment callback for hybrid payments"""
    if request.method == "GET":
        pidx = request.GET.get('pidx')
        transaction_id = request.GET.get('transaction_id')
        purchase_order_id = request.GET.get('purchase_order_id')
        payment_stage = request.GET.get('payment_stage', 'initial')
        
        if not pidx:
            return render(request, 'payments/payment_failed.html', {
                'error': 'No payment ID provided'
            })
        
        try:
            # Verify payment with Khalti
            verification_response = verify_khalti_payment(pidx)
            
            if verification_response['success']:
                data = verification_response['data']
                
                # Extract appointment ID from purchase_order_id (format: {appointment_id}_{stage})
                if purchase_order_id and '_' in purchase_order_id:
                    appointment_id = purchase_order_id.split('_')[0]
                else:
                    # Fallback: try to find by token
                    appointment_id = None
                
                # Find payment
                if appointment_id:
                    payment = Payment.objects.get(
                        appointment_id=appointment_id
                    )
                else:
                    payment = Payment.objects.get(
                        Q(khalti_token=pidx) | Q(khalti_final_token=pidx)
                    )
                
                appointment = payment.appointment
                
                if data['status'] == 'Completed':
                    # Update payment status based on stage
                    if payment_stage == 'initial':
                        payment.mark_initial_payment_completed()
                        
                        # Update appointment status to accepted after initial payment
                        appointment.status = 'accepted'
                        appointment.save()
                        
                        # Send notification
                        Notification.objects.create(
                            customer=appointment.customer,
                            notification_type='initial_payment_completed',
                            title='Initial Payment Successful!',
                            message=f'Your initial payment of ₹{payment.prepayment_amount} has been processed. Your appointment is now confirmed.',
                            appointment=appointment
                        )
                        
                        logger.info(f"Initial payment completed for appointment {appointment.id}")
                        
                    else:  # final payment
                        payment.mark_final_payment_completed()
                        
                        # Send notification
                        Notification.objects.create(
                            customer=appointment.customer,
                            notification_type='final_payment_completed',
                            title='Final Payment Successful!',
                            message=f'Your final payment of ₹{payment.remaining_amount} has been processed. Thank you for your business!',
                            appointment=appointment
                        )
                        
                        logger.info(f"Final payment completed for appointment {appointment.id}")
                    
                    return render(request, 'payments/payment_success.html', {
                        'appointment': appointment,
                        'payment': payment,
                        'transaction_id': data.get('transaction_id', transaction_id),
                        'payment_stage': payment_stage,
                        'amount_paid': float(payment.prepayment_amount) if payment_stage == 'initial' else float(payment.remaining_amount)
                    })
                else:
                    if payment_stage == 'initial':
                        payment.initial_payment_status = 'failed'
                    else:
                        payment.final_payment_status = 'failed'
                    payment.save()
                    
                    return render(request, 'payments/payment_failed.html', {
                        'error': f"Payment status: {data['status']}",
                        'payment_stage': payment_stage
                    })
                    
            else:
                return render(request, 'payments/payment_failed.html', {
                    'error': verification_response.get('detail', 'Payment verification failed'),
                    'payment_stage': payment_stage
                })
                
        except Payment.DoesNotExist:
            return render(request, 'payments/payment_failed.html', {
                'error': 'Payment record not found',
                'payment_stage': payment_stage
            })
        except Exception as e:
            logger.error(f"Error in khalti_callback: {str(e)}")
            return render(request, 'payments/payment_failed.html', {
                'error': str(e),
                'payment_stage': payment_stage
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


@login_required
def initiate_final_payment(request, appointment_id):
    """Initiate final payment after work completion"""
    if request.method == "POST":
        try:
            appointment = get_object_or_404(Appointment, id=appointment_id)
            payment = get_object_or_404(Payment, appointment=appointment)
            
            # Check if appointment is completed and initial payment is done
            if appointment.status != 'completed':
                return JsonResponse({
                    'success': False,
                    'error': 'Work must be completed before making final payment'
                })
            
            if payment.initial_payment_status != 'completed':
                return JsonResponse({
                    'success': False,
                    'error': 'Initial payment must be completed first'
                })
            
            if payment.final_payment_status == 'completed':
                return JsonResponse({
                    'success': False,
                    'error': 'Final payment already completed'
                })
            
            # Use the same initiate function but with payment_type='final'
            return initiate_khalti_payment(request, appointment_id)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)