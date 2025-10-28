# payments/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
import requests
import logging
import json

# Import from current app (payments)
from .models import Payment
from jobs.models import Appointment

logger = logging.getLogger(__name__)

def get_khalti_config():
    """Get Khalti configuration for use in other apps"""
    return {
        'public_key': getattr(settings, 'KHALTI_PUBLIC_KEY', 'test_public_key_dc74e0fd297a46f6aedf3c98b727a9a2'),
        'secret_key': getattr(settings, 'KHALTI_SECRET_KEY', '05bf95cc57244045b8df5fad06748dab'),
        'base_url': getattr(settings, 'KHALTI_BASE_URL', 'https://dev.khalti.com/api/v2'),
        'live_mode': getattr(settings, 'KHALTI_LIVE_MODE', False)
    }

@login_required
def checkout_page(request, appointment_id):
    """Checkout page with proper Khalti integration"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    # Calculate total amount based on service
    total_amount = 100.00
    if appointment.service_subtask and appointment.service_subtask.price:
        total_amount = float(appointment.service_subtask.price)
    
    # Create or get payment record
    payment, created = Payment.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': total_amount,
            'prepayment_amount': 50.00,
            'payment_type': 'hybrid',
            'remaining_amount': total_amount - 50.00
        }
    )
    
    # Get Khalti configuration
    khalti_config = get_khalti_config()
    
    context = {
        'appointment': appointment,
        'payment': payment,
        'khalti_public_key': khalti_config['public_key'],
        'khalti_config': khalti_config,
        'amount_in_paisa': 5000,  # 50 rupees in paisa
    }
    return render(request, 'payments/checkout.html', context)

@csrf_exempt
@login_required
def initiate_khalti_payment(request, appointment_id):
    """Initiate Khalti payment using KPG-2 API - CORRECTED"""
    try:
        # Get Khalti configuration
        khalti_config = get_khalti_config()
        secret_key = khalti_config['secret_key']
        base_url = khalti_config['base_url']
        
        if not secret_key:
            return JsonResponse({
                'success': False,
                'error': 'Khalti secret key not configured'
            }, status=500)
        
        appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
        
        # Always use 50 rupees for initial payment (5000 paisa)
        amount = 5000
        
        # Build the return URL
        return_url = request.build_absolute_uri('/payments/khalti-callback/')
        website_url = request.build_absolute_uri('/')
        
        payload = {
            "return_url": return_url,
            "website_url": website_url,
            "amount": amount,
            "purchase_order_id": f"appointment_{appointment.id}",
            "purchase_order_name": f"Service Booking - {appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'}",
            "customer_info": {
                "name": appointment.customer.name or "Customer",
                "email": appointment.customer.owner.email,
                "phone": str(appointment.customer.phone_number or "9800000000")
            },
            "amount_breakdown": [
                {
                    "label": "Prepayment Amount",
                    "amount": amount
                }
            ],
            "product_details": [
                {
                    "identity": f"service_{appointment.id}",
                    "name": f"{appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service'} - {appointment.worker.name}",
                    "total_price": amount,
                    "quantity": 1,
                    "unit_price": amount
                }
            ]
        }
        
        headers = {
            "Authorization": f"key {secret_key}",  # Note: lowercase 'key' as in ecommerce
            "Content-Type": "application/json",
        }
        
        # Make request to Khalti
        response = requests.post(
            f"{base_url}/epayment/initiate/",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        logger.info(f"Khalti Initiate Response: {response.status_code}")
        logger.info(f"Khalti Response Text: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            
            # Store pidx in session for verification
            request.session['khalti_pidx'] = data.get('pidx')
            request.session['payment_appointment_id'] = appointment_id
            
            return JsonResponse({
                'success': True,
                'payment_url': data['payment_url'],
                'pidx': data.get('pidx'),
                'expires_at': data.get('expires_at'),
                'expires_in': data.get('expires_in')
            })
        else:
            error_data = response.json() if response.content else {}
            logger.error(f"Khalti initiation failed: {response.status_code} - {response.text}")
            return JsonResponse({
                'success': False,
                'error': 'Payment initiation failed',
                'details': error_data
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error initiating Khalti payment: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

def verify_khalti_payment(pidx):
    """Verify Khalti payment status using lookup API"""
    try:
        khalti_config = get_khalti_config()
        secret_key = khalti_config['secret_key']
        base_url = khalti_config['base_url']
        
        headers = {
            "Authorization": f"key {secret_key}",  # Note: lowercase 'key'
            "Content-Type": "application/json",
        }
        
        response = requests.post(
            f"{base_url}/epayment/lookup/",
            json={"pidx": pidx},
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Payment verification failed: {response.status_code} - {response.text}")
            return {'status': 'Failed'}
            
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        return {'status': 'Failed'}
@csrf_exempt
def khalti_callback(request):
    """Handle Khalti payment callback with improved error handling"""
    if request.method == "GET":
        pidx = request.GET.get('pidx')
        transaction_id = request.GET.get('transaction_id')
        status = request.GET.get('status')
        
        # Get additional error parameters
        error_code = request.GET.get('error_code')
        error_message = request.GET.get('message')
        
        logger.info(f"Khalti Callback: pidx={pidx}, status={status}, error={error_message}")
        
        if not pidx:
            messages.error(request, 'No payment ID provided')
            return redirect('payments:payment_failed')
        
        try:
            # Verify the pidx matches what we stored
            session_pidx = request.session.get('khalti_pidx')
            if pidx != session_pidx:
                messages.error(request, 'Payment verification failed')
                return redirect('payments:payment_failed')
            
            # Handle specific error cases
            if error_code or error_message:
                # MPIN locked error
                if 'MPIN' in str(error_message) or 'locked' in str(error_message).lower():
                    messages.error(request, 
                        'Khalti MPIN is locked. Please reset it in your Khalti app: '
                        'Menu > Settings > Security > Khalti MPIN > Reset Khalti MPIN. '
                        'Or wait 24 hours for automatic reset.')
                    return redirect('payments:checkout', 
                                  appointment_id=request.session.get('payment_appointment_id'))
                
                # Other errors
                messages.error(request, f'Payment error: {error_message}')
                return redirect('payments:payment_failed')
            
            if status == 'Completed':
                # Verify payment with lookup API
                verification_response = verify_khalti_payment(pidx)
                
                if verification_response.get('status') == 'Completed':
                    # Get appointment from session
                    appointment_id = request.session.get('payment_appointment_id')
                    if not appointment_id:
                        messages.error(request, 'Appointment reference missing')
                        return redirect('payments:payment_failed')
                    
                    appointment = get_object_or_404(Appointment, id=appointment_id)
                    
                    # Create or get payment record
                    payment, created = Payment.objects.get_or_create(
                        appointment=appointment,
                        defaults={
                            'amount': 100.00,
                            'prepayment_amount': 50.00,
                            'payment_type': 'hybrid',
                            'remaining_amount': 50.00
                        }
                    )
                    
                    # Update payment status
                    payment.initial_payment_status = 'completed'
                    payment.payment_status = 'completed'
                    payment.khalti_token = pidx
                    payment.khalti_transaction_id = transaction_id or verification_response.get('transaction_id')
                    payment.paid_at = timezone.now()
                    payment.save()
                    
                    # Update appointment status
                    appointment.status = 'pending'
                    appointment.save()
                    
                    # Send notification to worker
                    try:
                        send_appointment_request_email(appointment.worker, appointment)
                        logger.info(f"Appointment request email sent to worker after payment")
                    except Exception as email_error:
                        logger.error(f"Failed to send appointment email after payment: {email_error}")
                    
                    # Create notification for worker
                    Notification.objects.create(
                        worker=appointment.worker,
                        notification_type='appointment_request',
                        title='New Appointment Request',
                        message=f'{appointment.customer.name} has sent you an appointment request with prepayment completed.',
                        appointment=appointment
                    )
                    
                    # Clear session data
                    if 'khalti_pidx' in request.session:
                        del request.session['khalti_pidx']
                    if 'payment_appointment_id' in request.session:
                        del request.session['payment_appointment_id']
                    
                    messages.success(request, 'Payment successful! Your appointment request has been sent to the worker.')
                    return redirect('payments:payment_success', appointment_id=appointment.id)
                else:
                    messages.error(request, f'Payment verification failed with status: {verification_response.get("status")}')
                    return redirect('payments:payment_failed')
                    
            elif status == 'User canceled' or status == 'Canceled':
                messages.warning(request, 'Payment was canceled. You can try again.')
                appointment_id = request.session.get('payment_appointment_id')
                if appointment_id:
                    return redirect('payments:checkout', appointment_id=appointment_id)
                return redirect('payments:payment_failed')
            
            elif status == 'Expired':
                messages.error(request, 'Payment session expired. Please try again.')
                appointment_id = request.session.get('payment_appointment_id')
                if appointment_id:
                    return redirect('payments:checkout', appointment_id=appointment_id)
                return redirect('payments:payment_failed')
            
            else:
                messages.error(request, f'Payment failed with status: {status}')
                return redirect('payments:payment_failed')
                
        except Exception as e:
            logger.error(f"Error in khalti_callback: {str(e)}")
            messages.error(request, 'Payment verification failed. Please contact support if payment was deducted.')
            return redirect('payments:payment_failed')
    
    return redirect('payments:payment_failed')

    
@login_required
def payment_success(request, appointment_id):
    """Payment success page"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    # Get the payment object related to this appointment
    try:
        payment = Payment.objects.get(appointment=appointment)
    except Payment.DoesNotExist:
        # If payment doesn't exist, create one with default values
        payment = Payment.objects.create(
            appointment=appointment,
            amount=100.00,
            prepayment_amount=50.00,
            payment_type='hybrid',
            remaining_amount=50.00,
            initial_payment_status='completed',
            payment_status='completed'
        )
    
    context = {
        'appointment': appointment,
        'payment': payment,  
    }
    return render(request, 'payments/payment_success.html', context)

@login_required
def payment_failed(request):
    """Payment failed page"""
    return render(request, 'payments/payment_failed.html')

@csrf_exempt
def test_khalti_api(request):
    """Test Khalti API connectivity and credentials"""
    if request.method == 'GET':
        try:
            # Test the API with a simple request
            khalti_config = get_khalti_config()
            test_url = f"{khalti_config['base_url']}/epayment/initiate/"
            
            headers = {
                'Authorization': f"key {khalti_config['secret_key']}",
                'Content-Type': 'application/json',
            }
            
            # Minimal test payload
            test_payload = {
                "return_url": "https://example.com/",
                "website_url": "https://example.com/",
                "amount": 1000,  # 10 NPR in paisa
                "purchase_order_id": "test_order_123",
                "purchase_order_name": "Test Order",
                "customer_info": {
                    "name": "Test Customer",
                    "email": "test@example.com",
                    "phone": "9800000001"
                }
            }
            
            response = requests.post(test_url, json=test_payload, headers=headers, timeout=30)
            
            return JsonResponse({
                'status_code': response.status_code,
                'response_text': response.text,
                'headers_sent': headers,
                'payload_sent': test_payload,
                'khalti_config_used': khalti_config
            })
            
        except Exception as e:
            return JsonResponse({
                'error': str(e),
                'message': 'Failed to test Khalti API',
                'khalti_config': khalti_config
            })
    
    return JsonResponse({'message': 'Use GET request to test'})


@login_required
def payment_page(request, appointment_id):
    """Payment page - similar to ecommerce payment page"""
    appointment = get_object_or_404(Appointment, id=appointment_id, customer__owner=request.user)
    
    # Get or create payment record
    payment, created = Payment.objects.get_or_create(
        appointment=appointment,
        defaults={
            'amount': 100.00,  # Default amount
            'prepayment_amount': 50.00,
            'payment_type': 'hybrid',
            'remaining_amount': 50.00
        }
    )
    
    # Calculate amount if service has price
    if appointment.service_subtask and appointment.service_subtask.price:
        total_amount = float(appointment.service_subtask.price)
        payment.amount = total_amount
        payment.prepayment_amount = 50.00
        payment.remaining_amount = total_amount - 50.00
        payment.save()
    
    context = {
        'appointment': appointment,
        'payment': payment,
    }
    return render(request, 'payments/payment.html', context)