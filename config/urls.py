from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Custom admin dashboard (with custom views)
    path('bluecollar-admin/', include('admin_dashboard.urls')),
    
    # Custom admin site (Django admin customized)
    path('super-admin/', admin.site.urls),  # Use the default for now
    
    # Original Django admin (backup)
    path('admin/', admin.site.urls),
    
    # Authentication
    path('accounts/', include('allauth.urls')),
    
    # Main application
    path('', include('jobs.urls')),
    
    # Payments
    path('payments/', include('payments.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)