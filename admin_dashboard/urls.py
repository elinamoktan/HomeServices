# In admin_dashboard/urls.py
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
    
    # NEW: Worker verification routes
    path('pending-verifications/', views.pending_worker_verifications, name='pending_verifications'),
    path('workers/<int:worker_id>/quick-verify/', views.quick_verify_worker, name='quick_verify_worker'),
    path('api/pending-workers-count/', views.get_pending_workers_count, name='pending_workers_count'),
    path('api/next-pending-worker/', views.get_next_pending_worker, name='next_pending_worker'),

    # ✅ FIXED: URL pattern that accepts worker_id parameter
    path('verify-worker-dashboard/<int:worker_id>/', views.quick_verify_worker, name='verify_worker_dashboard'),

    path('customers/', views.customer_management, name='customer_management'),
    path('customers/<int:customer_id>/edit/', views.edit_customer, name='edit_customer'),
    path('customers/<int:customer_id>/delete/', views.delete_customer, name='delete_customer'),
    path('customers/create/', views.create_customer, name='create_customer'),
    
    path('appointments/', views.appointment_management, name='appointment_management'),
    path('services/', views.service_management, name='service_management'),
    path('bulk-actions/', views.bulk_actions, name='bulk_actions'),
    path('api/quick-stats/', views.quick_stats_api, name='quick_stats_api'),
    path('export/<str:model_type>/', views.export_data, name='export_data'),

    path('super-admin/logout/', views.admin_logout, name='admin_logout'),
   
]