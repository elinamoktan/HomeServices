from django.urls import path
from . import views  # Changed this line
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', TemplateView.as_view(template_name="landing/index.html"), name='landing-page'),
    path('worker/<int:pk>/', views.WorkerDetailView.as_view(), name='worker-detail'),
    path('get-started/', views.WorkerListView.as_view(), name='worker-list'),
    path('account-setup/', views.handle_login, name='handle-login'),
    path('logout/', views.custom_logout, name='logout'),  # Use your custom logout view
    path('worker/create/', views.WorkerCreateView.as_view(), name='worker-create'),
    path('customer/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('worker/appoint/<int:worker_id>', views.appoint_worker, name='appoint-worker'),
    path('worker/dashboard/', views.worker_dashboard, name='worker_dashboard'),

    # Customer URLs
    path('customer/appointments/', views.customer_appointments, name='customer_appointments'),
    path('customer/dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('customer/reviews/', views.customer_reviews, name='customer_reviews'),
    path('customer/profile/', views.customer_profile, name='customer_profile'),
    path('customer/settings/', views.customer_settings, name='customer_settings'),
    path('customer/support/', views.customer_support, name='customer_support'),
    
    # Appointment management URLs
    path('appointments/<int:worker_id>/', views.worker_appointments, name='worker_appointments'),
    path('appointments/<int:appointment_id>/accept/', views.accept_appointment, name='accept_appointment'),
    path('appointments/<int:appointment_id>/reject/', views.reject_appointment, name='reject_appointment'),
    path('appointments/<int:appointment_id>/complete/', views.complete_appointment, name='complete_appointment'),
    path('appointments/<int:appointment_id>/delete/', views.delete_appointment, name='delete_appointment'),
    path('appointments/request-new/<int:appointment_id>/', views.request_new_worker, name='request_new_worker'),

    # Alternative appointment URLs
    path('appointment/<int:appointment_id>/accept/', views.accept_appointment, name='accept_appointment'),
    path('appointment/<int:appointment_id>/reject/', views.reject_appointment, name='reject_appointment'),
    path('appointment/delete/<int:appointment_id>/', views.delete_appointment, name='delete_appointment'),
    path('complete-appointment/<int:appointment_id>/', views.complete_appointment, name='complete_appointment'),
    
    # Rating and completion URLs
    path('rate-worker/<int:appointment_id>/', views.rate_worker, name='rate_worker'),
    path('appointment/<int:pk>/customer-complete/', views.mark_customer_completed, name='appointment-customer-complete'),
    path('appointment/<int:pk>/worker-complete/', views.mark_worker_completed, name='appointment-worker-complete'),
    
    # Location and AJAX URLs
    path('worker/update-location/', views.update_worker_location, name='worker-update-location'),
    path('worker/<int:worker_id>/availability/', views.get_worker_availability, name='get_worker_availability'),
    path('calculate-price/', views.calculate_service_price, name='calculate_service_price'),
    path('initiate-chat/<int:worker_id>/', views.initiate_chat, name='initiate_chat'),
    
    # Fixed notification count URL
    path('notification-count/', views.notification_count, name='get_notification_count'),
    path('help-support/', views.customer_support, name='help_support'),  
    path('api/worker-notifications/', views.worker_notifications, name='worker_notifications'),
    path('api/mark-notification-read/', views.mark_notification_read, name='mark_notification_read'),
    path('api/mark-all-notifications-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
]