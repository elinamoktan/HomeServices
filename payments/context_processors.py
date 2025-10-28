from django.conf import settings

def khalti_config(request):
    """Add Khalti configuration to template context"""
    return {
        'KHALTI_PUBLIC_KEY': getattr(settings, 'KHALTI_PUBLIC_KEY', ''),
        'KHALTI_SECRET_KEY': getattr(settings, 'KHALTI_SECRET_KEY', ''),
        'KHALTI_BASE_URL': getattr(settings, 'KHALTI_BASE_URL', 'https://khalti.com/api/v2'),
        'INITIAL_PAYMENT_AMOUNT': getattr(settings, 'INITIAL_PAYMENT_AMOUNT', 50.00),
    }