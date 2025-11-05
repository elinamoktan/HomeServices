
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.conf import settings
from django.utils.html import strip_tags
from datetime import datetime, timedelta
import json
import csv
import logging
from django.utils import timezone
from datetime import timedelta

from jobs.models import (
    Worker, Customer, Appointment, WorkerRating, Service, 
    WorkerService, WorkerSubTaskPricing, ServiceCategory, SubTask,
    Notification, FavoriteWorker
)
from .models import AdminDashboardSettings, AdminActivityLog

# Configure logging
logger = logging.getLogger(__name__)

def admin_required(user):
    """Check if user is admin/staff"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@login_required
@user_passes_test(admin_required)
def admin_dashboard(request):
    """Main admin dashboard view"""
    # Calculate statistics
    total_workers = Worker.objects.count()
    total_customers = Customer.objects.count()
    total_appointments = Appointment.objects.count()
    total_services = Service.objects.count()
    
    # Recent appointments
    recent_appointments = Appointment.objects.select_related('worker', 'customer').order_by('-created_at')[:10]
    
    # Pending approvals
    pending_workers = Worker.objects.filter(verified=False).count()
    pending_appointments = Appointment.objects.filter(status='pending').count()
    
    # Get pending workers list for the table
    pending_workers_list = Worker.objects.filter(verified=False).select_related('owner').order_by('-created_at')[:10]
    
    # Revenue statistics
    completed_appointments = Appointment.objects.filter(status='completed')
    total_revenue = sum(app.total_price or 0 for app in completed_appointments if app.total_price)
    
    # Chart data - appointments by status
    status_counts = list(Appointment.objects.values('status').annotate(count=Count('id')))
    
    context = {
        'total_workers': total_workers,
        'total_customers': total_customers,
        'total_appointments': total_appointments,
        'total_services': total_services,
        'pending_workers': pending_workers,
        'pending_appointments': pending_appointments,
        'pending_workers_list': pending_workers_list,
        'total_revenue': total_revenue,
        'recent_appointments': recent_appointments,
        'status_counts': status_counts,
    }
    return render(request, 'admin_dashboard/dashboard.html', context)



@login_required
@user_passes_test(admin_required)
def verify_worker_dashboard(request, worker_id):
    """Handle worker verification from dashboard - FIXED VERSION WITH EMAIL"""
    print("="*80)
    print(f"🔍 VERIFY WORKER DASHBOARD CALLED")
    print(f"🔍 Worker ID: {worker_id}")
    print(f"🔍 Method: {request.method}")
    print(f"🔍 POST Data: {dict(request.POST)}")
    print("="*80)
    
    if request.method != 'POST':
        return JsonResponse({
            'success': False, 
            'error': 'Only POST method allowed'
        }, status=405)
    
    try:
        # Get worker
        worker = get_object_or_404(Worker, id=worker_id)
        action = request.POST.get('action')
        
        if not action:
            return JsonResponse({
                'success': False, 
                'error': 'No action provided'
            }, status=400)
        
        # Process action
        if action == 'approve':
            print(f"🔍 Processing APPROVE for {worker.name}")
            
            try:
                # ✅ Use verify_worker method
                success = worker.verify_worker()
                print(f"✅ Worker verified: {success}")
                
                # ✅ CRITICAL: Send approval email to worker
                try:
                    from jobs.views import send_worker_verification_email
                    email_sent = send_worker_verification_email(worker, approved=True)
                    if email_sent:
                        print(f"✅ Approval email sent to {worker.name}")
                    else:
                        print(f"❌ Failed to send approval email to {worker.name}")
                except Exception as email_error:
                    print(f"❌ Email error: {email_error}")
                
            except Exception as e:
                print(f"❌ Failed to verify: {e}")
                return JsonResponse({
                    'success': False, 
                    'error': f'Failed to verify worker: {str(e)}'
                }, status=500)
            
            # Log admin activity
            try:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Verified worker {worker.name} from dashboard'
                )
            except Exception as e:
                print(f"⚠️ Admin activity logging failed: {e}")
            
            print(f"🎉 SUCCESS: Worker {worker.name} approved!")
            return JsonResponse({
                'success': True, 
                'message': f'Worker {worker.name} approved successfully!',
                'worker_id': worker.id
            })
            
        elif action == 'reject':
            reason = request.POST.get('reason', 'Profile does not meet our verification requirements')
            print(f"🔍 Processing REJECT for {worker.name}")
            print(f"🔍 Reason: {reason}")
            
            try:
                # ✅ CRITICAL FIX: Use reject_worker method
                success = worker.reject_worker(reason)
                print(f"✅ Worker rejected: {success}")
                print(f"✅ last_rejection_date set to: {worker.last_rejection_date}")
                
                # ✅ CRITICAL: Send rejection email to worker
                try:
                    from jobs.views import send_worker_verification_email
                    email_sent = send_worker_verification_email(worker, approved=False, rejection_reason=reason)
                    if email_sent:
                        print(f"✅ Rejection email sent to {worker.name}")
                    else:
                        print(f"❌ Failed to send rejection email to {worker.name}")
                except Exception as email_error:
                    print(f"❌ Email error: {email_error}")
                
            except Exception as e:
                print(f"❌ Failed to reject: {e}")
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    'success': False, 
                    'error': f'Failed to reject worker: {str(e)}'
                }, status=500)
            
            # Log admin activity
            try:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Rejected worker {worker.name}. Reason: {reason}'
                )
            except Exception as e:
                print(f"⚠️ Admin activity logging failed: {e}")
            
            print(f"🎉 SUCCESS: Worker {worker.name} rejected!")
            return JsonResponse({
                'success': True, 
                'message': f'Worker {worker.name} rejected successfully',
                'worker_id': worker.id,
                'reason': reason
            })
            
        else:
            return JsonResponse({
                'success': False, 
                'error': f'Invalid action: {action}'
            }, status=400)
            
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }, status=500)

@login_required
@user_passes_test(admin_required)
def quick_verify_worker(request, worker_id):
    """Quick verify/reject worker from the popup - FIXED VERSION"""
    logger.info(f"quick_verify_worker called with worker_id: {worker_id}")
    
    try:
        worker = get_object_or_404(Worker, id=worker_id)
        action = request.POST.get('action')
        
        logger.info(f"Action received: '{action}' for worker: {worker.name}")
        
        if action == 'approve' or action == 'verify':
            logger.info(f"Processing approval for {worker.name}")
            
            try:
                # ✅ Use verify_worker method
                success = worker.verify_worker()
                logger.info(f"Worker verified successfully: {success}")
                
                # ✅ Send approval email
                try:
                    from jobs.views import send_worker_verification_email
                    email_sent = send_worker_verification_email(worker, approved=True)
                    if email_sent:
                        logger.info(f"Approval email sent to {worker.name}")
                except Exception as email_error:
                    logger.error(f"Failed to send approval email: {email_error}")
                
            except Exception as e:
                logger.error(f"Failed to verify worker: {e}")
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to verify worker: {str(e)}'
                }, status=500)
            
            # Log admin activity
            try:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Verified worker {worker.name} from quick verification'
                )
                logger.info(f"Admin activity logged")
            except Exception as e:
                logger.error(f"Failed to log admin activity: {e}")
            
            return JsonResponse({
                'success': True, 
                'message': f'Worker {worker.name} verified successfully',
                'worker_id': worker.id
            })
            
        elif action == 'reject':
            reason = request.POST.get('reason', 'Profile does not meet requirements')
            logger.info(f"Processing rejection for {worker.name}, reason: {reason}")
            
            try:
                # ✅ CRITICAL FIX: Use reject_worker method
                success = worker.reject_worker(reason)
                logger.info(f"Worker rejected successfully: {success}")
                logger.info(f"last_rejection_date set to: {worker.last_rejection_date}")
                
                # ✅ Send rejection email
                try:
                    from jobs.views import send_worker_verification_email
                    email_sent = send_worker_verification_email(worker, approved=False, rejection_reason=reason)
                    if email_sent:
                        logger.info(f"Rejection email sent to {worker.name}")
                except Exception as email_error:
                    logger.error(f"Failed to send rejection email: {email_error}")
                
            except Exception as e:
                logger.error(f"Failed to reject worker: {e}")
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to reject worker: {str(e)}'
                }, status=500)
            
            # Log admin activity
            try:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Rejected worker {worker.name} from quick verification. Reason: {reason}'
                )
                logger.info(f"Rejection admin activity logged")
            except Exception as e:
                logger.error(f"Failed to log rejection admin activity: {e}")
            
            return JsonResponse({
                'success': True, 
                'message': f'Worker {worker.name} rejected successfully',
                'worker_id': worker.id
            })
            
        else:
            logger.error(f"Invalid action received: {action}")
            return JsonResponse({
                'success': False, 
                'error': f'Invalid action: {action}'
            }, status=400)
            
    except Worker.DoesNotExist:
        logger.error(f"Worker with id {worker_id} not found")
        return JsonResponse({
            'success': False, 
            'error': 'Worker not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Exception occurred: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False, 
            'error': f'Server error: {str(e)}'
        }, status=500)


def send_verification_resubmission_email(worker):
    """Send email to admin when worker resubmits for verification"""
    try:
        subject = f"🔄 Verification Resubmission: {worker.name}"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                <h2 style="color: #4f46e5; text-align: center;">Worker Resubmitted for Verification</h2>
                
                <p>Worker <strong>{worker.name}</strong> has updated their profile and resubmitted for verification.</p>
                
                <div style="background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <h3 style="color: #1e40af; margin-top: 0;">Worker Details:</h3>
                    <p><strong>Name:</strong> {worker.name}</p>
                    <p><strong>Email:</strong> {worker.owner.email}</p>
                    <p><strong>Phone:</strong> {worker.phone_number}</p>
                    <p><strong>Previous Rejection Reason:</strong> {worker.rejection_reason or 'N/A'}</p>
                    <p><strong>Resubmitted At:</strong> {worker.verification_submitted_at.strftime('%Y-%m-%d %H:%M') if worker.verification_submitted_at else 'Just now'}</p>
                </div>
                
                <div style="text-align: center; margin: 25px 0;">
                    <a href="{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/bluecollar-admin/pending-verifications/" 
                       style="background: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">
                       Review Profile
                    </a>
                </div>
                
                <p style="color: #6b7280; font-size: 14px; text-align: center;">
                    This is an automated notification from BlueCollar Admin System
                </p>
            </div>
        </body>
        </html>
        """
        
        # Send to all admin users
        admin_users = User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True)
        )
        admin_emails = list(admin_users.values_list('email', flat=True))
        
        if admin_emails:
            from django.core.mail import send_mail
            from django.utils.html import strip_tags
            
            send_mail(
                subject=subject,
                message=strip_tags(html_message),
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecollar.com'),
                recipient_list=admin_emails,
                html_message=html_message,
                fail_silently=True,
            )
            
            logger.info(f"Resubmission email sent to admins for worker {worker.name}")
        
    except Exception as e:
        logger.error(f"Failed to send resubmission email: {e}")


@login_required
@user_passes_test(admin_required)
def worker_management(request):
    """Worker management view"""
    workers = Worker.objects.select_related('owner').annotate(
        appointment_count=Count('worker_appointments'),
        avg_rating=Avg('ratings__rating')
    ).order_by('-created_at')
    
    # Calculate statistics
    total_workers = workers.count()
    verified_workers = workers.filter(verified=True).count()
    unverified_workers = workers.filter(verified=False).count()
    available_workers = workers.filter(is_available=True).count()
    unavailable_workers = workers.filter(is_available=False).count()
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter == 'verified':
        workers = workers.filter(verified=True)
    elif status_filter == 'unverified':
        workers = workers.filter(verified=False)
    elif status_filter == 'available':
        workers = workers.filter(is_available=True)
    elif status_filter == 'unavailable':
        workers = workers.filter(is_available=False)
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        workers = workers.filter(
            Q(name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(tagline__icontains=search_query) |
            Q(owner__email__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(workers, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'workers': page_obj,
        'current_filter': status_filter,
        'search_query': search_query,
        'total_workers': total_workers,
        'verified_workers': verified_workers,
        'unverified_workers': unverified_workers,
        'available_workers': available_workers,
        'unavailable_workers': unavailable_workers,
    }
    return render(request, 'admin_dashboard/worker_management.html', context)

@login_required
@user_passes_test(admin_required)
def edit_worker(request, worker_id):
    """Edit worker directly in the template - FIXED VERSION"""
    worker = get_object_or_404(Worker, id=worker_id)
    
    if request.method == 'POST':
        try:
            # Update worker fields
            worker.name = request.POST.get('name', worker.name)
            worker.phone_number = request.POST.get('phone_number', worker.phone_number)
            worker.tagline = request.POST.get('tagline', worker.tagline)
            worker.bio = request.POST.get('bio', worker.bio)
            
            # Handle verified status - check if it's being passed
            if 'verified' in request.POST:
                worker.verified = request.POST.get('verified') in ['true', 'True', '1', 'on']
            
            worker.is_available = request.POST.get('is_available') == 'true'
            worker.shift = request.POST.get('shift', worker.shift)
            
            # Handle file uploads
            if 'profile_pic' in request.FILES:
                worker.profile_pic = request.FILES['profile_pic']
            
            if 'citizenship_image' in request.FILES:
                worker.citizenship_image = request.FILES['citizenship_image']
            
            if 'certificate_file' in request.FILES:
                worker.certificate_file = request.FILES['certificate_file']
            
            worker.save()
            
            # Log admin activity
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='UPDATE',
                model_name='Worker',
                object_id=worker.id,
                description=f'Updated worker {worker.name}'
            )
            
            return JsonResponse({'success': True, 'message': 'Worker updated successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    # For GET request, return worker data - FIXED VERSION
    elif request.method == 'GET':
        try:
            # Calculate appointment count and average rating
            appointment_count = worker.worker_appointments.count()
            avg_rating = worker.ratings.aggregate(avg=Avg('rating'))['avg'] or 0
            
            # Format location updated at
            location_updated_at = worker.location_updated_at.strftime('%b. %d, %Y, %I:%M %p') if worker.location_updated_at else None
            
            # Handle profile picture URL safely
            profile_pic_url = ''
            if worker.profile_pic:
                try:
                    profile_pic_url = worker.profile_pic.url
                except Exception as e:
                    logger.warning(f"Could not get profile pic URL for worker {worker_id}: {e}")
                    profile_pic_url = ''
            
            # Handle citizenship image URL safely
            citizenship_image_url = ''
            if worker.citizenship_image:
                try:
                    citizenship_image_url = worker.citizenship_image.url
                except Exception as e:
                    logger.warning(f"Could not get citizenship image URL for worker {worker_id}: {e}")
                    citizenship_image_url = ''
            
            # Handle certificate file URL safely
            certificate_file_url = ''
            if worker.certificate_file:
                try:
                    certificate_file_url = worker.certificate_file.url
                except Exception as e:
                    logger.warning(f"Could not get certificate file URL for worker {worker_id}: {e}")
                    certificate_file_url = ''
            
            worker_data = {
                'id': worker.id,
                'name': worker.name,
                'phone_number': str(worker.phone_number),  # ✅ FIXED: Convert PhoneNumber to string
                'tagline': worker.tagline or '',
                'bio': worker.bio or '',
                'verified': worker.verified,
                'is_available': worker.is_available,
                'shift': worker.shift,
                'profile_pic_url': profile_pic_url,
                'average_rating': round(float(avg_rating), 2),
                'total_ratings': worker.ratings.count(),
                'appointment_count': appointment_count,
                'created_at': worker.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'email': worker.owner.email if worker.owner else '',
                'owner_id': worker.owner.id if worker.owner else None,
                
                # Location information
                'latitude': str(worker.latitude) if worker.latitude else None,
                'longitude': str(worker.longitude) if worker.longitude else None,
                'location_address': worker.location_address or 'Browser Geolocation',
                'location_updated_at': location_updated_at,
                'location_accuracy': '12/0',
                'location_source': 'Browser Geolocation',
                
                # Documents
                'citizenship_image_url': citizenship_image_url,
                'certificate_file_url': certificate_file_url,
            }
            
            logger.info(f"Successfully fetched worker data for ID: {worker_id}")
            return JsonResponse(worker_data)
            
        except Exception as e:
            logger.error(f"Error fetching worker data for ID {worker_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return JsonResponse({
                'success': False, 
                'error': f'Error loading worker data: {str(e)}'
            }, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@user_passes_test(admin_required)
def delete_worker(request, worker_id):
    """Delete worker directly in the template"""
    if request.method == 'POST':
        try:
            worker = get_object_or_404(Worker, id=worker_id)
            worker_name = worker.name
            
            # Log admin activity before deletion
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='DELETE',
                model_name='Worker',
                object_id=worker.id,
                description=f'Deleted worker {worker.name}'
            )
            
            worker.delete()
            
            return JsonResponse({'success': True, 'message': 'Worker deleted successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@require_http_methods(["POST"])
def create_worker(request):
    """Create a new worker"""
    try:
        # Get form data
        name = request.POST.get('name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        tagline = request.POST.get('tagline', '').strip()
        bio = request.POST.get('bio', '').strip()
        shift = request.POST.get('shift', '')
        
        # Handle boolean fields
        verified = request.POST.get('verified', 'false').lower() == 'true'
        is_available = request.POST.get('is_available', 'true').lower() == 'true'
        
        # Handle file uploads
        profile_pic = request.FILES.get('profile_pic')
        
        # Validation
        if not all([name, phone_number, email, username, password, shift]):
            return JsonResponse({
                'success': False,
                'error': 'All required fields must be filled'
            }, status=400)
        
        if password != confirm_password:
            return JsonResponse({
                'success': False,
                'error': 'Passwords do not match'
            }, status=400)
        
        if len(password) < 8:
            return JsonResponse({
                'success': False,
                'error': 'Password must be at least 8 characters long'
            }, status=400)
        
        # Check if username or email already exists
        if User.objects.filter(username=username).exists():
            return JsonResponse({
                'success': False,
                'error': 'Username already exists'
            }, status=400)
        
        if User.objects.filter(email=email).exists():
            return JsonResponse({
                'success': False,
                'error': 'Email already exists'
            }, status=400)
        
        # Check if phone number already exists
        if Worker.objects.filter(phone_number=phone_number).exists():
            return JsonResponse({
                'success': False,
                'error': 'Phone number already exists'
            }, status=400)
        
        # Create user and worker in a transaction
        with transaction.atomic():
            # Create user account
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=name
            )
            
            # Create worker profile
            worker = Worker.objects.create(
                owner=user,
                name=name,
                phone_number=phone_number,
                tagline=tagline,
                bio=bio,
                shift=shift,
                verified=verified,
                is_available=is_available,
                profile_pic=profile_pic
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Worker {name} created successfully!',
                'worker_id': worker.id
            })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@login_required
@user_passes_test(admin_required)
def get_worker_documents(request, worker_id):
    """API endpoint to get worker document URLs"""
    try:
        worker = get_object_or_404(Worker, id=worker_id)
        
        documents = {
            'citizenship_image': None,
            'certificate_file': None,
            'profile_pic': None
        }
        
        # Safely get document URLs
        try:
            if worker.citizenship_image and hasattr(worker.citizenship_image, 'url'):
                documents['citizenship_image'] = worker.citizenship_image.url
        except Exception as e:
            logger.warning(f"Could not get citizenship image URL: {e}")
            
        try:
            if worker.certificate_file and hasattr(worker.certificate_file, 'url'):
                documents['certificate_file'] = worker.certificate_file.url
        except Exception as e:
            logger.warning(f"Could not get certificate file URL: {e}")
            
        try:
            if worker.profile_pic and hasattr(worker.profile_pic, 'url'):
                documents['profile_pic'] = worker.profile_pic.url
        except Exception as e:
            logger.warning(f"Could not get profile pic URL: {e}")
        
        return JsonResponse({
            'success': True,
            'documents': documents
        })
        
    except Exception as e:
        logger.error(f"Error getting worker documents: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@user_passes_test(admin_required)
def customer_management(request):
    """Customer management view"""
    customers = Customer.objects.select_related('owner').annotate(
        appointment_count=Count('customer_appointments'),
        total_spent=Sum('customer_appointments__total_price')
    ).order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        customers = customers.filter(
            Q(name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(owner__email__icontains=search_query)
        )
    
    # Filtering
    filter_type = request.GET.get('filter')
    if filter_type == 'active':
        customers = customers.filter(appointment_count__gt=0)
    elif filter_type == 'new':
        start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        customers = customers.filter(created_at__gte=start_of_month)
    
    # Calculate stats
    total_customers = customers.count()
    active_customers = customers.filter(appointment_count__gt=0).count()
    total_revenue = customers.aggregate(total=Sum('total_spent'))['total'] or 0
    avg_appointments = customers.aggregate(avg=Avg('appointment_count'))['avg'] or 0
    
    # Additional insights
    high_value_customers = customers.filter(total_spent__gt=1000).count()
    repeat_customers = customers.filter(appointment_count__gt=1).count()
    new_customers_this_month = customers.filter(
        created_at__month=timezone.now().month,
        created_at__year=timezone.now().year
    ).count()
    
    # Top spenders
    top_spenders = customers.order_by('-total_spent')[:5]
    
    context = {
        'customers': customers,
        'total_customers': total_customers,
        'active_customers': active_customers,
        'total_revenue': total_revenue,
        'avg_appointments': round(avg_appointments, 1),
        'high_value_customers': high_value_customers,
        'repeat_customers': repeat_customers,
        'new_customers_this_month': new_customers_this_month,
        'top_spenders': top_spenders,
        'search_query': search_query,
        'current_filter': filter_type,
    }
    return render(request, 'admin_dashboard/customer_management.html', context)

@login_required
@user_passes_test(admin_required)
def edit_customer(request, customer_id):
    """Edit customer directly in the template"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == 'POST':
        try:
            # Update customer fields
            customer.name = request.POST.get('name', customer.name)
            customer.phone_number = request.POST.get('phone_number', customer.phone_number)
            customer.location_address = request.POST.get('location_address', customer.location_address)
            
            # Handle profile picture upload
            if 'profile_pic' in request.FILES:
                customer.profile_pic = request.FILES['profile_pic']
            
            customer.save()
            
            # Log admin activity
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='UPDATE',
                model_name='Customer',
                object_id=customer.id,
                description=f'Updated customer {customer.name}'
            )
            
            return JsonResponse({'success': True, 'message': 'Customer updated successfully'})
            
        except Exception as e:
            logger.error(f"Error updating customer {customer_id}: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    # For GET request, return customer data - FIXED VERSION
    elif request.method == 'GET':
        try:
            # Calculate appointment count and total spent safely
            appointment_count = customer.customer_appointments.count()
            
            total_spent_result = customer.customer_appointments.aggregate(
                total=Sum('total_price')
            )
            total_spent = float(total_spent_result['total'] or 0)
            
            customer_data = {
                'id': customer.id,
                'name': customer.name,
                'phone_number': str(customer.phone_number),  # Ensure string conversion
                'email': customer.owner.email if customer.owner else '',
                'location_address': customer.location_address or '',
                'profile_pic_url': customer.profile_pic.url if customer.profile_pic else '',
                'appointment_count': appointment_count,
                'total_spent': total_spent,
                'created_at': customer.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
            
            logger.info(f"Successfully fetched customer data for ID: {customer_id}")
            return JsonResponse(customer_data)
            
        except Exception as e:
            logger.error(f"Error fetching customer data for ID {customer_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return JsonResponse({
                'success': False, 
                'error': f'Error loading customer data: {str(e)}'
            }, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@user_passes_test(admin_required)
def delete_customer(request, customer_id):
    """Delete customer directly in the template"""
    if request.method == 'POST':
        try:
            customer = get_object_or_404(Customer, id=customer_id)
            customer_name = customer.name
            
            # Log admin activity before deletion
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='DELETE',
                model_name='Customer',
                object_id=customer.id,
                description=f'Deleted customer {customer.name}'
            )
            
            customer.delete()
            
            return JsonResponse({'success': True, 'message': 'Customer deleted successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@user_passes_test(admin_required)
def create_customer(request):
    """Create new customer directly in the template"""
    if request.method == 'POST':
        try:
            # Create user first
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password', 'Temp123!')
            
            # Check if user already exists
            if User.objects.filter(username=username).exists():
                return JsonResponse({
                    'success': False, 
                    'error': 'A user with this username already exists'
                }, status=400)
            
            if User.objects.filter(email=email).exists():
                return JsonResponse({
                    'success': False, 
                    'error': 'A user with this email already exists'
                }, status=400)
            
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            
            # Create customer
            customer = Customer.objects.create(
                owner=user,
                name=request.POST.get('name'),
                phone_number=request.POST.get('phone_number'),
                location_address=request.POST.get('location_address', '')
            )
            
            # Handle profile picture
            if 'profile_pic' in request.FILES:
                customer.profile_pic = request.FILES['profile_pic']
                customer.save()
            
            # Log admin activity
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='CREATE',
                model_name='Customer',
                object_id=customer.id,
                description=f'Created new customer {customer.name}'
            )
            
            return JsonResponse({
                'success': True, 
                'message': 'Customer created successfully', 
                'customer_id': customer.id
            })
            
        except Exception as e:
            # Clean up user if customer creation fails
            if 'user' in locals():
                user.delete()
                
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)


@login_required
@user_passes_test(admin_required)
def service_management(request):
    """Service management view for admin dashboard"""
    services = Service.objects.all().select_related('category').order_by('-created_at')
    categories = ServiceCategory.objects.all()
    
    # Calculate stats
    total_services = services.count()
    active_services = services.filter(is_active=True).count()
    inactive_services = services.filter(is_active=False).count()
    
    # Add subtask count to each service
    for service in services:
        service.subtask_count = service.subtasks.count()
    
    context = {
        'services': services,
        'categories': categories,
        'total_services': total_services,
        'active_services': active_services,
        'inactive_services': inactive_services,
    }
    return render(request, 'admin_dashboard/service_management.html', context)

@login_required
@user_passes_test(admin_required)
def edit_service(request, service_id):
    """Edit service view"""
    service = get_object_or_404(Service, id=service_id)
    
    if request.method == 'POST':
        try:
            service.name = request.POST.get('name')
            service.description = request.POST.get('description')
            category_id = request.POST.get('category')
            service.base_pricing_type = request.POST.get('base_pricing_type')
            service.is_active = request.POST.get('is_active') == 'on'
            
            category = ServiceCategory.objects.get(id=category_id)
            service.category = category
            
            # Handle image upload
            if 'image' in request.FILES:
                service.image = request.FILES['image']
            
            service.save()
            messages.success(request, f'Service "{service.name}" updated successfully!')
            return redirect('admin_dashboard:service_management')
            
        except Exception as e:
            messages.error(request, f'Error updating service: {str(e)}')
    
    categories = ServiceCategory.objects.all()
    return render(request, 'admin_dashboard/edit_service.html', {
        'service': service,
        'categories': categories
    })

@login_required
@user_passes_test(admin_required)
def delete_service(request, service_id):
    """Delete service via AJAX"""
    if request.method == 'POST':
        try:
            service = get_object_or_404(Service, id=service_id)
            service_name = service.name
            service.delete()
            
            # Log admin activity
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='DELETE',
                model_name='Service',
                object_id=service_id,
                description=f'Deleted service {service_name}'
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Service "{service_name}" deleted successfully!'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
@user_passes_test(admin_required)
def appointment_management(request):
    """Appointment management view"""
    appointments = Appointment.objects.select_related(
        'customer', 'worker', 'service_subtask'
    ).order_by('-created_at')
    
    # Calculate stats
    total_appointments = appointments.count()
    pending_appointments = appointments.filter(status='pending').count()
    completed_appointments = appointments.filter(status='completed').count()
    total_revenue = appointments.filter(status='completed').aggregate(
        total=Sum('total_price')
    )['total'] or 0
    
    # Filtering
    status_filter = request.GET.get('status')
    if status_filter:
        appointments = appointments.filter(status=status_filter)
    
    context = {
        'appointments': appointments,
        'current_filter': status_filter,
        'total_appointments': total_appointments,
        'pending_appointments': pending_appointments,
        'completed_appointments': completed_appointments,
        'total_revenue': total_revenue,
    }
    return render(request, 'admin_dashboard/appointment_management.html', context)

@login_required
@user_passes_test(admin_required)
def service_management(request):
    """Service management view - safe version"""
    # Get services with basic information
    services = Service.objects.select_related('category').order_by('-created_at')
    
    # Get worker counts using the correct related name
    try:
        services_with_counts = Service.objects.annotate(
            worker_count=Count('workerservice')
        )
        worker_count_dict = {s.id: s.worker_count for s in services_with_counts}
    except Exception as e:
        logger.error(f"Error getting worker counts: {e}")
        worker_count_dict = {}
    
    # Add counts to services
    for service in services:
        service.worker_count = worker_count_dict.get(service.id, 0)
        service.subtask_count = service.subtasks.count()
    
    categories = ServiceCategory.objects.annotate(
        service_count=Count('services')
    ).order_by('name')
    
    # Calculate statistics
    total_services = services.count()
    active_services = services.filter(is_active=True).count()
    inactive_services = services.filter(is_active=False).count()
    
    context = {
        'services': services,
        'categories': categories,
        'total_services': total_services,
        'active_services': active_services,
        'inactive_services': inactive_services,
    }
    return render(request, 'admin_dashboard/service_management.html', context)

@login_required
@user_passes_test(admin_required)
def admin_analytics(request):
    """Advanced analytics view"""
    # Time period filter
    period = request.GET.get('period', '7')
    end_date = timezone.now()
    
    if period == '7':
        start_date = end_date - timedelta(days=7)
    elif period == '30':
        start_date = end_date - timedelta(days=30)
    else:  # 90 days
        start_date = end_date - timedelta(days=90)
    
    # Registration analytics
    worker_registrations = Worker.objects.filter(
        created_at__range=[start_date, end_date]
    ).extra({'date': "date(created_at)"}).values('date').annotate(count=Count('id')).order_by('date')
    
    customer_registrations = Customer.objects.filter(
        created_at__range=[start_date, end_date]
    ).extra({'date': "date(created_at)"}).values('date').annotate(count=Count('id')).order_by('date')
    
    # Appointment analytics
    appointment_stats = Appointment.objects.filter(
        created_at__range=[start_date, end_date]
    ).values('status').annotate(count=Count('id'))
    
    # Revenue analytics
    revenue_data = Appointment.objects.filter(
        status='completed',
        created_at__range=[start_date, end_date]
    ).extra({'date': "date(created_at)"}).values('date').annotate(
        revenue=Sum('total_price')
    ).order_by('date')
    
    context = {
        'period': period,
        'worker_registrations': list(worker_registrations),
        'customer_registrations': list(customer_registrations),
        'appointment_stats': list(appointment_stats),
        'revenue_data': list(revenue_data),
    }
    return render(request, 'admin_dashboard/analytics.html', context)

@login_required
@user_passes_test(admin_required)
def admin_reports(request):
    """Comprehensive reports view"""
    # Top performers
    top_workers = Worker.objects.annotate(
        total_appointments=Count('worker_appointments'),
        avg_rating=Avg('ratings__rating'),
        completed_appointments=Count('worker_appointments', filter=Q(worker_appointments__status='completed'))
    ).order_by('-total_appointments')[:10]
    
    # Popular services
    popular_services = Service.objects.annotate(
        appointment_count=Count('subtasks__workersubtaskpricing__appointment')
    ).order_by('-appointment_count')[:10]
    
    # Active customers
    active_customers = Customer.objects.annotate(
        appointment_count=Count('customer_appointments'),
        total_spent=Sum('customer_appointments__total_price')
    ).order_by('-appointment_count')[:10]
    
    context = {
        'top_workers': top_workers,
        'popular_services': popular_services,
        'active_customers': active_customers,
    }
    return render(request, 'admin_dashboard/reports.html', context)

@login_required
@user_passes_test(admin_required)
def bulk_actions(request):
    """Handle bulk actions from admin"""
    if request.method == 'POST':
        action = request.POST.get('action')
        selected_ids = request.POST.getlist('selected_ids')
        
        if action == 'verify_workers':
            workers = Worker.objects.filter(id__in=selected_ids)
            updated_count = workers.update(verified=True)
            
            # Log bulk action
            for worker in workers:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Bulk verified worker {worker.name}'
                )
            
            messages.success(request, f'{updated_count} workers verified successfully.')
        
        elif action == 'unverify_workers':
            workers = Worker.objects.filter(id__in=selected_ids)
            updated_count = workers.update(verified=False)
            
            # Log bulk action
            for worker in workers:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Worker',
                    object_id=worker.id,
                    description=f'Bulk unverified worker {worker.name}'
                )
            
            messages.success(request, f'{updated_count} workers unverified.')
        
        elif action == 'activate_services':
            services = Service.objects.filter(id__in=selected_ids)
            updated_count = services.update(is_active=True)
            
            # Log bulk action
            for service in services:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Service',
                    object_id=service.id,
                    description=f'Bulk activated service {service.name}'
                )
            
            messages.success(request, f'{updated_count} services activated.')
        
        elif action == 'deactivate_services':
            services = Service.objects.filter(id__in=selected_ids)
            updated_count = services.update(is_active=False)
            
            # Log bulk action
            for service in services:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Service',
                    object_id=service.id,
                    description=f'Bulk deactivated service {service.name}'
                )
            
            messages.success(request, f'{updated_count} services deactivated.')
        
        elif action == 'complete_appointments':
            appointments = Appointment.objects.filter(id__in=selected_ids)
            updated_count = appointments.update(status='completed')
            
            # Log bulk action
            for appointment in appointments:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Appointment',
                    object_id=appointment.id,
                    description=f'Bulk completed appointment #{appointment.id}'
                )
            
            messages.success(request, f'{updated_count} appointments marked as completed.')
        
        elif action == 'cancel_appointments':
            appointments = Appointment.objects.filter(id__in=selected_ids)
            updated_count = appointments.update(status='cancelled')
            
            # Log bulk action
            for appointment in appointments:
                AdminActivityLog.objects.create(
                    admin_user=request.user,
                    action='UPDATE',
                    model_name='Appointment',
                    object_id=appointment.id,
                    description=f'Bulk cancelled appointment #{appointment.id}'
                )
            
            messages.success(request, f'{updated_count} appointments cancelled.')
    
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard:dashboard'))

@login_required
@user_passes_test(admin_required)
def quick_stats_api(request):
    """API endpoint for quick stats (AJAX)"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        today = timezone.now().date()
        
        # Today's stats
        today_appointments = Appointment.objects.filter(
            created_at__date=today
        ).count()
        
        today_registrations = Worker.objects.filter(
            created_at__date=today
        ).count() + Customer.objects.filter(
            created_at__date=today
        ).count()
        
        today_revenue = Appointment.objects.filter(
            status='completed',
            created_at__date=today
        ).aggregate(Sum('total_price'))['total_price__sum'] or 0
        
        data = {
            'today_appointments': today_appointments,
            'today_registrations': today_registrations,
            'today_revenue': float(today_revenue),
        }
        
        return JsonResponse(data)
    
    return JsonResponse({'error': 'Invalid request'})

@login_required
@user_passes_test(admin_required)
def export_data(request, model_type):
    """Export data to various formats"""
    format_type = request.GET.get('format', 'csv')
    
    if model_type == 'workers':
        data = Worker.objects.all().values('name', 'phone_number', 'verified', 'average_rating', 'created_at')
        filename = 'workers_export'
    
    elif model_type == 'customers':
        data = Customer.objects.all().values('name', 'phone_number', 'created_at')
        filename = 'customers_export'
    
    elif model_type == 'appointments':
        data = Appointment.objects.all().values(
            'customer__name', 'worker__name', 'appointment_date', 'status', 'total_price'
        )
        filename = 'appointments_export'
    
    else:
        messages.error(request, 'Invalid export type')
        return redirect('admin_dashboard:dashboard')
    
    if format_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        if data:
            # Write headers
            writer.writerow(data[0].keys())
            # Write data
            for item in data:
                writer.writerow(item.values())
        
        return response
    
    elif format_type == 'json':
        response = HttpResponse(content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}.json"'
        response.write(json.dumps(list(data), indent=2, default=str))
        return response
    
    messages.error(request, 'Invalid format type')
    return redirect('admin_dashboard:dashboard')

@login_required
@user_passes_test(admin_required)
def verify_worker(request, worker_id):
    """Verify/Unverify worker"""
    if request.method == 'POST':
        try:
            worker = get_object_or_404(Worker, id=worker_id)
            action = request.POST.get('action', 'verify')
            
            if action == 'verify':
                worker.verified = True
                message = f'Worker {worker.name} verified successfully'
            else:
                worker.verified = False
                message = f'Worker {worker.name} unverified'
            
            worker.save()
            
            # Log admin activity
            AdminActivityLog.objects.create(
                admin_user=request.user,
                action='UPDATE',
                model_name='Worker',
                object_id=worker.id,
                description=message
            )
            
            return JsonResponse({'success': True, 'message': message})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@user_passes_test(admin_required)
def pending_worker_verifications(request):
    """View for pending worker verifications"""
    pending_workers = Worker.objects.filter(verified=False).select_related('owner').order_by('-created_at')
    
    # Calculate statistics
    total_pending = pending_workers.count()
    recent_pending = pending_workers.filter(created_at__gte=timezone.now() - timedelta(days=7)).count()
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        pending_workers = pending_workers.filter(
            Q(name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(owner__email__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(pending_workers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'pending_workers': page_obj,
        'total_pending': total_pending,
        'recent_pending': recent_pending,
        'search_query': search_query,
    }
    return render(request, 'admin_dashboard/pending_verifications.html', context)

@login_required
@user_passes_test(admin_required)
def get_pending_workers_count(request):
    """API endpoint to get count of pending worker verifications"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        pending_count = Worker.objects.filter(verified=False).count()
        return JsonResponse({'pending_count': pending_count})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@user_passes_test(admin_required)
def get_next_pending_worker(request):
    """API endpoint to get next pending worker for popup"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        pending_worker = Worker.objects.filter(verified=False).select_related('owner').first()
        
        if pending_worker:
            worker_data = {
                'id': pending_worker.id,
                'name': pending_worker.name,
                'phone_number': str(pending_worker.phone_number),  # ✅ FIXED: Convert to string
                'email': pending_worker.owner.email,
                'tagline': pending_worker.tagline or 'No tagline',
                'bio': pending_worker.bio or 'No bio',
                'profile_pic': pending_worker.profile_pic.url if pending_worker.profile_pic else '/static/images/default-profile.png',
                'citizenship_image': pending_worker.citizenship_image.url if pending_worker.citizenship_image else None,
                'certificate_file': pending_worker.certificate_file.url if pending_worker.certificate_file else None,
                'created_at': pending_worker.created_at.strftime('%Y-%m-%d %H:%M'),
                'shift': pending_worker.get_shift_display(),
            }
            return JsonResponse({'worker': worker_data})
        else:
            return JsonResponse({'worker': None})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
def send_worker_verification_email(worker, approved, rejection_reason=None):
    """Send email notification to worker about verification status"""
    try:
        if approved:
            subject = "Worker Profile Verified - BlueCollar"
            site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c3e50;">Profile Verified Successfully! 🎉</h2>
                    
                    <div style="background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin: 0;">Your worker profile has been verified</h3>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #007bff; margin-top: 0;">What's Next?</h3>
                        <p>✅ Your profile is now visible to customers</p>
                        <p>✅ You can receive appointment requests</p>
                        <p>✅ Start building your reputation with reviews</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{site_url}/worker/dashboard/" 
                           style="background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Go to Dashboard
                        </a>
                    </div>
                </div>
            </body>
            </html>
            """
        else:
            subject = "Worker Profile Verification Update - BlueCollar"
            site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #2c3e50;">Profile Verification Update</h2>
                    
                    <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="margin: 0;">Verification Required</h3>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <p>Your worker profile requires additional verification.</p>
                        <p><strong>Reason:</strong> {rejection_reason or 'Profile information needs verification'}</p>
                        <p>Please update your profile and ensure all documents are clear and valid.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{site_url}/worker/settings/" 
                           style="background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Update Profile
                        </a>
                    </div>
                </div>
            </body>
            </html>
            """
        
        # Plain text version
        plain_message = strip_tags(html_message)
        
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecollar.com')
        recipients = [worker.owner.email]
        
        # Send email
        from django.core.mail import send_mail
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=True
        )
        
        logger.info(f"Email sent successfully to {worker.owner.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False
        
@login_required
@user_passes_test(admin_required)
def suspend_worker(request, worker_id):
    """Suspend a worker"""
    if request.method == 'POST':
        try:
            worker = get_object_or_404(Worker, id=worker_id)
            reason = request.POST.get('reason', 'Violation of platform policies')
            end_date_str = request.POST.get('end_date')
            
            end_date = None
            if end_date_str:
                try:
                    end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
                except ValueError:
                    pass
            
            # Suspend the worker
            success = worker.suspend_worker(reason, request.user, end_date)
            
            if success:
                # Send suspension email notification
                try:
                    send_worker_suspension_email(worker, reason, end_date)
                except Exception as e:
                    logger.error(f"Failed to send suspension email: {e}")
                
                return JsonResponse({
                    'success': True, 
                    'message': f'Worker {worker.name} suspended successfully'
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'error': 'Failed to suspend worker'
                })
                
        except Exception as e:
            logger.error(f"Error suspending worker {worker_id}: {str(e)}")
            return JsonResponse({
                'success': False, 
                'error': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

@login_required
@user_passes_test(admin_required)
def unsuspend_worker(request, worker_id):
    """Unsuspend a worker"""
    if request.method == 'POST':
        try:
            worker = get_object_or_404(Worker, id=worker_id)
            
            # Unsuspend the worker
            success = worker.unsuspend_worker(request.user)
            
            if success:
                # Send unsuspension email notification
                try:
                    send_worker_unsuspension_email(worker)
                except Exception as e:
                    logger.error(f"Failed to send unsuspension email: {e}")
                
                return JsonResponse({
                    'success': True, 
                    'message': f'Worker {worker.name} unsuspended successfully'
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'error': 'Failed to unsuspend worker'
                })
                
        except Exception as e:
            logger.error(f"Error unsuspending worker {worker_id}: {str(e)}")
            return JsonResponse({
                'success': False, 
                'error': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

def send_worker_suspension_email(worker, reason, end_date=None):
    """Send suspension email to worker"""
    try:
        subject = "Account Suspension - BlueCollar"
        site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        
        end_date_text = end_date.strftime('%B %d, %Y') if end_date else "until further notice"
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #dc3545;">Account Suspension Notice</h2>
                
                <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0;">Your account has been suspended</h3>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Reason:</strong> {reason}</p>
                    <p><strong>Suspension Period:</strong> {end_date_text}</p>
                    <p>During this suspension period, you will not be able to:</p>
                    <ul>
                        <li>Receive new appointment requests</li>
                        <li>Appear in customer searches</li>
                        <li>Access your worker dashboard</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{site_url}/contact/" 
                       style="background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Contact Support
                    </a>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_message = strip_tags(html_message)
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecollar.com')
        recipients = [worker.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=True
        )
        
        logger.info(f"Suspension email sent to {worker.owner.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send suspension email: {str(e)}")
        return False

def send_worker_unsuspension_email(worker):
    """Send unsuspension email to worker"""
    try:
        subject = "Account Access Restored - BlueCollar"
        site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        
        html_message = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #28a745;">Account Access Restored! 🎉</h2>
                
                <div style="background: #d4edda; color: #155724; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0;">Your account suspension has been lifted</h3>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p>Your BlueCollar worker account has been restored and you can now:</p>
                    <ul>
                        <li>✅ Receive new appointment requests</li>
                        <li>✅ Appear in customer searches</li>
                        <li>✅ Access your worker dashboard</li>
                        <li>✅ Continue providing services</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{site_url}/worker/dashboard/" 
                       style="background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Go to Dashboard
                    </a>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_message = strip_tags(html_message)
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bluecollar.com')
        recipients = [worker.owner.email]
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipients,
            html_message=html_message,
            fail_silently=True
        )
        
        logger.info(f"Unsuspension email sent to {worker.owner.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send unsuspension email: {str(e)}")
        return False