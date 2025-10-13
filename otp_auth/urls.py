from django.urls import path
from . import views

app_name = 'otp_auth'

urlpatterns = [
    # Main OTP flow
    path("send-signup-otp/", views.send_signup_otp, name="send_signup_otp"),
    path("verify-signup/", views.verify_signup_otp, name="verify_signup_otp"),
]