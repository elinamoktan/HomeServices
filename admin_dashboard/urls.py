from django.urls import path
from . import views

app_name = 'admin_dashboard'  # This defines the namespace

urlpatterns = [
    path('', views.admin_dashboard, name='dashboard'),
    path('analytics/', views.admin_analytics, name='analytics'),
    path('reports/', views.admin_reports, name='reports'),
    path('workers/', views.worker_management, name='worker_management'),
    path('customers/', views.customer_management, name='customer_management'),
    path('appointments/', views.appointment_management, name='appointment_management'),
    path('services/', views.service_management, name='service_management'),
    path('bulk-actions/', views.bulk_actions, name='bulk_actions'),
    path('api/quick-stats/', views.quick_stats_api, name='quick_stats_api'),
    path('export/<str:model_type>/', views.export_data, name='export_data'),
]