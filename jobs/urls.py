from django.urls import path, include
from . import views
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views
from .views import CustomLoginView  # ✅ NEW: Import custom login view

urlpatterns = [
    # Landing page
    path('', TemplateView.as_view(template_name="landing/index.html"), name='landing-page'),

    # ✅ NEW: Override allauth's default login with custom view (must come BEFORE allauth urls)
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    
    # Worker URLs
    path('worker/<int:pk>/', views.WorkerDetailView.as_view(), name='worker-detail'),
    path('get-started/', views.WorkerListView.as_view(), name='worker-list'),
    path('account-setup/', views.handle_login, name='handle-login'),
    path('logout/', views.custom_logout, name='logout'),
    path('worker/create/', views.WorkerCreateView.as_view(), name='worker-create'),
    path('worker/dashboard/', views.worker_dashboard, name='worker_dashboard'),

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
    path('appointment/<int:pk>/customer-complete/', views.mark_customer_completed, name='mark_customer_completed'),
    # Support
    path('help-support/', views.customer_support, name='help_support'),

    # OTP Authentication (must come AFTER custom login override)
    path('otp-auth/', include('otp_auth.urls')),
    
    # ✅ IMPORTANT: Allauth URLs must come AFTER custom login override
    path('accounts/', include('allauth.urls')),

    # Favorite URLs
    path('favorite-workers/', views.favorite_workers_list, name='favorite_workers_list'),
    path('toggle-favorite-worker/<int:worker_id>/', views.toggle_favorite_worker, name='toggle_favorite_worker'),
    path('check-favorite-status/<int:worker_id>/', views.check_favorite_status, name='check_favorite_status'),


    # Worker section URLs
    path('worker/calendar/', views.worker_calendar, name='worker_calendar'),
    path('worker/reviews/', views.worker_reviews, name='worker_reviews'),
    path('worker/analytics/', views.worker_analytics, name='worker_analytics'),
    path('worker/earnings/', views.worker_earnings, name='worker_earnings'),
    path('worker/settings/', views.worker_settings, name='worker_settings'),

    # Add this URL pattern to your urlpatterns list
    path('delete-worker-review/', views.delete_worker_review, name='delete_worker_review'),
]