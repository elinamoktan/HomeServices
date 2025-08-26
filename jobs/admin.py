from django.contrib import admin
from django.http import HttpRequest
from .models import Worker, Customer,Appointment,WorkerRating

def verify_workers(modeladmin: admin.ModelAdmin, request: HttpRequest, queryset):
    queryset.update(verified=True)

admin.site.register(Worker)
admin.site.register(Customer)
admin.site.register(Appointment)
admin.site.register(WorkerRating)

admin.site.add_action(verify_workers)

from .models import Service  # Import your Service model

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'category']
    search_fields = ['title', 'category']
    list_filter = ['category']

