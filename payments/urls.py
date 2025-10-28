# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('checkout/<int:appointment_id>/', views.checkout_page, name='checkout'),
    path('payment/<int:appointment_id>/', views.payment_page, name='payment_page'),  # Add this
    path('initiate/<int:appointment_id>/', views.initiate_khalti_payment, name='initiate_payment'),
    path('khalti-callback/', views.khalti_callback, name='khalti_callback'),
    path('success/<int:appointment_id>/', views.payment_success, name='payment_success'),
    path('failed/', views.payment_failed, name='payment_failed'),
    path('test-khalti/', views.test_khalti_api, name='test_khalti_api'),
]