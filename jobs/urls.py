from django.urls import path, include
from . import views
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from .views import CustomLoginView

urlpatterns = [
    # Landing page
    path('', TemplateView.as_view(template_name="landing/index.html"), name='landing-page'),
    
    # Location storage
    path('store-landing-location/', views.store_landing_location, name='store_landing_location'),

    # ✅ NEW: Override allauth's default login with custom view
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    
    # Worker URLs - ✅ FIXED: Remove duplicate worker/create URL
    path('worker/<int:pk>/', views.WorkerDetailView.as_view(), name='worker-detail'),
    path('account-setup/', views.handle_login, name='handle-login'),
    path('logout/', views.custom_logout, name='logout'),
    
    # ✅ CORRECT: Only one worker/create URL - use the function-based view with email
    path('worker/create/', views.create_worker_profile, name='worker-create'),
    
    path('worker/dashboard/', views.worker_dashboard, name='worker_dashboard'),
    path('get-started/', views.WorkerListView.as_view(), name='worker-list'),

    # Customer URLs
    path('customer/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customer/appointments/', views.customer_appointments, name='customer_appointments'),
    path('customer/dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('customer/reviews/', views.customer_reviews, name='customer_reviews'),
    path('customer/profile/', views.customer_profile, name='customer_profile'),
    path('customer/settings/', views.customer_settings, name='customer_settings'),
    path('customer/support/', views.customer_support, name='customer_support'),

    # Appointment management URLs
    path('worker/appoint/<int:worker_id>/', views.appoint_worker, name='appoint-worker'),
    path('worker/<int:worker_id>/appointment-request/', views.appointment_request, name='appointment_request'),

    # Worker appointment management
    path('worker/appointments/', views.worker_appointments, name='worker_appointments_own'),
    path('worker/appointments/<int:worker_id>/', views.worker_appointments, name='worker_appointments'),
    path('worker/<int:worker_id>/services/', views.worker_service_details, name='worker_service_details'),

    # Appointment actions
    path('appointment/<int:appointment_id>/accept/', views.accept_appointment, name='accept_appointment'),
    path('appointment/<int:appointment_id>/reject/', views.reject_appointment, name='reject_appointment'),
    path('appointment/<int:appointment_id>/complete/', views.complete_appointment, name='complete_appointment'),
    path('appointment/<int:appointment_id>/delete/', views.delete_appointment, name='delete_appointment'),
    path('appointment/<int:appointment_id>/request-new/', views.request_new_worker, name='request_new_worker'),
    path('appointments/<int:appointment_id>/details/', views.appointment_request_details, name='appointment_request_details'),

    # Rating and completion URLs
    path('rate-worker/<int:appointment_id>/', views.rate_worker, name='rate_worker'),
    path('appointment/<int:pk>/customer-complete/', views.mark_customer_completed, name='appointment-customer-complete'),
    path('appointment/<int:pk>/worker-complete/', views.mark_worker_completed, name='appointment-worker-complete'),

    # API endpoints
    path('api/workers/<int:worker_id>/services/', views.worker_services_api, name='worker_services_api'),
    path('api/worker/<int:worker_id>/availability/', views.get_worker_availability, name='get_worker_availability'),
    path('api/calculate-price/', views.calculate_service_price, name='calculate_service_price'),
    path('api/notification-count/', views.notification_count, name='get_notification_count'),
    path('api/worker-notifications/', views.worker_notifications, name='worker_notifications'),
    path('api/mark-notification-read/', views.mark_notification_read, name='mark_notification_read'),
    path('api/mark-all-notifications-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),

    # Location Tracking API Endpoints
    path('api/update-location/', views.update_current_location, name='update_current_location'),
    path('api/nearby-workers/', views.get_nearby_workers, name='get_nearby_workers'),

    # Service and interaction URLs
    path('services/', views.service_categories, name='service-categories'),
    path('initiate-chat/<int:worker_id>/', views.initiate_chat, name='initiate_chat'),
    
    # Location updates
    path('worker/update-location/', views.update_worker_location, name='worker-update-location'),
    
    # Support
    path('help-support/', views.customer_support, name='help_support'),

    # OTP Authentication
    path('otp-auth/', include('otp_auth.urls')),
    
    # Allauth URLs
    path('accounts/', include('allauth.urls')),

    # Favorite URLs
    path('favorite-workers/', views.favorite_workers_list, name='favorite_workers_list'),
    path('toggle-favorite-worker/<int:worker_id>/', views.toggle_favorite_worker, name='toggle_favorite_worker'),
    path('check-favorite-status/<int:worker_id>/', views.check_favorite_status, name='check_favorite_status'),

    # Worker section URLs
    path('worker/calendar/', views.worker_calendar, name='worker_calendar'),
    path('worker/reviews/', views.worker_reviews, name='worker_reviews'),
    path('worker/reviews/reply/', views.reply_to_review, name='reply_to_review'),
    path('worker/analytics/', views.worker_analytics, name='worker_analytics'),
    path('worker/earnings/', views.worker_earnings, name='worker_earnings'),
    path('worker/settings/', views.worker_settings, name='worker_settings'),

    # ✅ FIXED: Corrected delete review URL
    path('delete-worker-review/', views.delete_worker_review, name='delete_worker_review'),

    # Notification URLs
    path('customer/notifications/', views.customer_notifications, name='customer_notifications'),
    path('customer/check-appointment-updates/', views.check_appointment_updates, name='check_appointment_updates'),
    path('notifications/<int:notification_id>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('get-notification-count/', views.get_notification_count, name='get_notification_count'),
    
    # Redirect and service URLs
    path('workers/', views.workers_redirect, name='workers-direct'),
    path('worker/<int:worker_id>/services/filter/', views.worker_service_details, name='filter_worker_services'),
    path('worker/add-subtask/<int:worker_service_id>/', views.add_custom_subtask, name='add_custom_subtask'),
    path('worker/services/', views.get_worker_services_for_subtask, name='get_worker_services'),
    path('api/get-worker-address/', views.get_worker_address, name='get_worker_address'),
    
    # ✅ FIXED: Correct completion URLs
    path('customer/appointments/mark-completed/<int:pk>/', views.mark_customer_completed, name='mark_customer_completed'),
    path('worker/appointments/mark-completed/<int:pk>/', views.mark_worker_completed, name='mark_worker_completed'),
    
    # Add this to your urlpatterns
    path('worker/<int:worker_id>/appointment-request/', views.appointment_request, name='appointment_request'),
    # ✅ NEW: Cache management URLs
    path('api/clear-location-cache/', views.clear_location_cache, name='clear_location_cache'),
    path('api/get-cached-location/', views.get_cached_location, name='get_cached_location'),

    path('resubmit-verification/', views.resubmit_verification, name='resubmit_verification'),
    path('check-resubmission-status/', views.check_resubmission_status, name='check_resubmission_status'),

     # Location-based sorting
    # path('update-location-and-sort/', views.update_location_and_sort, name='update_location_and_sort'),
    path('update-current-location/', views.update_current_location, name='update_current_location'),
    path('clear-location-cache/', views.clear_location_cache, name='clear_location_cache'),

    # path('appointment/<int:appointment_id>/report-delay/', views.report_delay, name='report_delay'),
    # path('worker/appointments-for-delay/', views.get_worker_appointments_for_delay, name='worker_appointments_for_delay'),
    
]