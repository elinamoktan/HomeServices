# urls.py - Add these URL patterns
from django.urls import path
from . import views

app_name = 'admin_dashboard'

urlpatterns = [
    path('', views.admin_dashboard, name='dashboard'),
    path('analytics/', views.admin_analytics, name='analytics'),
    path('reports/', views.admin_reports, name='reports'),

    path('workers/', views.worker_management, name='worker_management'),
    path('workers/<int:worker_id>/edit/', views.edit_worker, name='edit_worker'),
    path('workers/<int:worker_id>/delete/', views.delete_worker, name='delete_worker'),
    path('workers/<int:worker_id>/verify/', views.verify_worker, name='verify_worker'),
    path('workers/create/', views.create_worker, name='create_worker'),
    
    # Worker verification routes
    path('pending-verifications/', views.pending_worker_verifications, name='pending_verifications'),
    path('workers/<int:worker_id>/quick-verify/', views.quick_verify_worker, name='quick_verify_worker'),
    path('api/pending-workers-count/', views.get_pending_workers_count, name='pending_workers_count'),
    path('api/next-pending-worker/', views.get_next_pending_worker, name='next_pending_worker'),
    path('verify-worker-dashboard/<int:worker_id>/', views.quick_verify_worker, name='verify_worker_dashboard'),

    # ✅ FIXED: Customer management URLs
    path('customers/', views.customer_management, name='customer_management'),
    path('customers/<int:customer_id>/edit/', views.edit_customer, name='edit_customer'),
    # In your admin_dashboard/urls.py
    path('customer/delete/<int:customer_id>/', views.delete_customer, name='delete_customer'),
    path('customers/create/', views.create_customer, name='create_customer'),
    
    path('appointments/', views.appointment_management, name='appointment_management'),
    path('services/', views.service_management, name='service_management'),
    path('services/edit/<int:service_id>/', views.edit_service, name='edit_service'),
    path('services/delete/<int:service_id>/', views.delete_service, name='delete_service'),
    path('bulk-actions/', views.bulk_actions, name='bulk_actions'),
    path('api/quick-stats/', views.quick_stats_api, name='quick_stats_api'),
    path('export/<str:model_type>/', views.export_data, name='export_data'),

    path('suspend-worker/<int:worker_id>/', views.suspend_worker, name='suspend_worker'),
    path('unsuspend-worker/<int:worker_id>/', views.unsuspend_worker, name='unsuspend_worker'),
    path('worker/<int:worker_id>/documents/', views.get_worker_documents, name='get_worker_documents'),
    
]