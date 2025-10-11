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

    path('customers/', views.customer_management, name='customer_management'),
    path('appointments/', views.appointment_management, name='appointment_management'),
    path('services/', views.service_management, name='service_management'),
    path('bulk-actions/', views.bulk_actions, name='bulk_actions'),
    path('api/quick-stats/', views.quick_stats_api, name='quick_stats_api'),
    path('export/<str:model_type>/', views.export_data, name='export_data'),
]