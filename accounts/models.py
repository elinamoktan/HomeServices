from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    middle_name = models.CharField(max_length=150, blank=True, null=True)
    contact_no = models.CharField(max_length=20, blank=True, null=True)
    pass

    def get_worker(self):
        if(hasattr(self,'worker')):
            return self.worker 
        return None
    
    def get_customer(self):
        if(hasattr(self,'customer')):
            return self.customer 
        return None

class ProjectCategory(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Plan(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return self.name

class UserActivity(models.Model):
    email = models.EmailField()
    status = models.CharField(max_length=50)
    contact_no = models.CharField(max_length=20)
    activity_type = models.CharField(max_length=100)
    def __str__(self):
        return self.email