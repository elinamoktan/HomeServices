from django.urls import path
from . import views

app_name = 'otp_auth'

urlpatterns = [
    path("verify-signup/<int:user_id>/", views.verify_signup_otp, name="verify_signup_otp"),
    path("verify-login/<int:user_id>/", views.verify_login_otp, name="verify_login_otp"),
]