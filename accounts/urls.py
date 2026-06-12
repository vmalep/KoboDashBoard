from django.urls import path
from django.contrib.auth.views import (
    LoginView, LogoutView,
    PasswordResetView, PasswordResetDoneView,
    PasswordResetConfirmView, PasswordResetCompleteView,
)
from . import views

urlpatterns = [
    path('login/', LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', views.register, name='register'),
    path('pending/', views.pending_approval, name='pending_approval'),

    path('password-reset/',
         PasswordResetView.as_view(template_name='accounts/password_reset_form.html',
                                   email_template_name='accounts/password_reset_email.html',
                                   subject_template_name='accounts/password_reset_subject.txt'),
         name='password_reset'),
    path('password-reset/done/',
         PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset/confirm/<uidb64>/<token>/',
         PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('password-reset/complete/',
         PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'),
         name='password_reset_complete'),
]
