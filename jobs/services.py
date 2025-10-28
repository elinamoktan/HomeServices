# jobs/services.py
from django.utils import timezone
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from .models import Appointment, Notification
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

def check_appointment_conflicts(worker, new_estimated_end_time, current_appointment_id):
    """
    Check for conflicting appointments when a delay is reported
    """
    try:
        # Find appointments that conflict with the new estimated end time
        conflicting_appointments = Appointment.objects.filter(
            worker=worker,
            appointment_date__lt=new_estimated_end_time,
            appointment_date__gt=timezone.now(),  # Only future appointments
            status__in=['pending', 'accepted']  # Only active appointments
        ).exclude(id=current_appointment_id)  # Exclude current appointment
        
        conflicts = []
        for appointment in conflicting_appointments:
            # Send delay notification to customer
            send_delay_notification(appointment, new_estimated_end_time)
            conflicts.append(appointment)
            
            # Create in-app notification
            Notification.objects.create(
                customer=appointment.customer,
                notification_type='appointment_delayed',
                title='Appointment Delayed',
                message=f'Your appointment with {worker.name} has been delayed due to a previous job running late. New estimated time will be communicated soon.',
                appointment=appointment
            )
        
        return conflicts
        
    except Exception as e:
        logger.error(f"Error checking appointment conflicts: {e}")
        return []

def send_delay_notification(appointment, new_estimated_end_time):
    """
    Send delay notification to customer via email
    """
    try:
        customer = appointment.customer
        worker = appointment.worker
        
        subject = f"Appointment Delay Notification - {worker.name}"
        
        context = {
            'customer_name': customer.name,
            'worker_name': worker.name,
            'original_time': appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p'),
            'new_estimated_time': new_estimated_end_time.strftime('%B %d, %Y at %I:%M %p'),
            'service_name': appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service',
            'worker_phone': str(worker.phone_number),
        }
        
        html_message = render_to_string('emails/appointment_delay_notification.html', context)
        plain_message = strip_tags(html_message)
        
        from_email = 'noreply@bluecaller.com'  # Use your actual from email
        recipients = [customer.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Delay notification sent to {customer.name}")
        
    except Exception as e:
        logger.error(f"Failed to send delay notification: {e}")

def report_delay_service(appointment_id, new_estimated_time, delay_reason=""):
    """
    Service function to handle delay reporting for accepted appointments
    """
    try:
        appointment = Appointment.objects.get(id=appointment_id)
        
        # Verify appointment is accepted
        if appointment.status != 'accepted':
            return {
                'success': False, 
                'error': 'Can only report delays for accepted appointments'
            }
        
        # Convert string to datetime
        if isinstance(new_estimated_time, str):
            new_estimated_time = timezone.make_aware(
                datetime.strptime(new_estimated_time, '%Y-%m-%dT%H:%M:%S')
            )
        
        # Store original end time if not already stored
        if not appointment.original_end_time:
            appointment.original_end_time = appointment.appointment_date
        
        # Update appointment with delay information
        appointment.estimated_completion_time = new_estimated_time
        appointment.delay_reason = delay_reason
        appointment.delay_reported_at = timezone.now()
        appointment.is_delayed = True
        appointment.save()
        
        # Create notification for customer
        Notification.objects.create(
            customer=appointment.customer,
            notification_type='appointment_delayed',
            title='Appointment Delayed',
            message=f'{appointment.worker.name} has reported a delay in your appointment. New estimated completion: {new_estimated_time.strftime("%B %d, %Y at %I:%M %p")}. Reason: {delay_reason}',
            appointment=appointment
        )
        
        # Check for conflicts with other appointments
        conflicts = check_appointment_conflicts(
            appointment.worker, 
            new_estimated_time, 
            appointment_id
        )
        
        # Send email notification to customer
        try:
            send_delay_notification_to_customer(appointment, new_estimated_time, delay_reason)
        except Exception as e:
            logger.error(f"Failed to send delay email: {e}")
        
        return {
            'success': True,
            'conflicts': len(conflicts),
            'message': f'Delay reported successfully. Customer has been notified. {len(conflicts)} conflicting appointments found.'
        }
        
    except Appointment.DoesNotExist:
        return {'success': False, 'error': 'Appointment not found'}
    except Exception as e:
        logger.error(f"Error reporting delay: {e}")
        return {'success': False, 'error': str(e)}

def send_delay_notification_to_customer(appointment, new_estimated_time, delay_reason):
    """
    Send delay notification email to customer
    """
    try:
        customer = appointment.customer
        worker = appointment.worker
        
        subject = f"Appointment Delay Update - {worker.name}"
        
        context = {
            'customer_name': customer.name,
            'worker_name': worker.name,
            'original_time': appointment.appointment_date.strftime('%B %d, %Y at %I:%M %p'),
            'new_estimated_time': new_estimated_time.strftime('%B %d, %Y at %I:%M %p'),
            'delay_reason': delay_reason,
            'service_name': appointment.service_subtask.subtask.name if appointment.service_subtask else 'Service',
            'worker_phone': str(worker.phone_number),
            'appointment_id': appointment.id,
        }
        
        html_message = render_to_string('emails/appointment_delay_notification.html', context)
        plain_message = strip_tags(html_message)
        
        from_email = 'noreply@bluecaller.com'  # Use your actual from email
        recipients = [customer.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Delay notification email sent to {customer.name}")
        
    except Exception as e:
        logger.error(f"Failed to send delay notification email: {e}")