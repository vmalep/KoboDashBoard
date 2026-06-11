from django.urls import path
from . import views

urlpatterns = [
    path('', views.form_list, name='form_list'),
    path('settings/', views.settings_view, name='settings'),
    path('users/', views.user_list, name='user_list'),
    path('users/<int:user_id>/activate/', views.user_activate, name='user_activate'),
    path('users/<int:user_id>/deactivate/', views.user_deactivate, name='user_deactivate'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('<str:uid>/', views.coverage, name='coverage'),
    path('<str:uid>/submissions/', views.submission_list, name='submission_list'),
    path('<str:uid>/submission/<int:sub_id>/', views.submission_detail, name='submission_detail'),
    path('<str:uid>/refresh/', views.refresh_form, name='refresh_form'),
    path('<str:uid>/export/csv/', views.export_csv, name='export_csv'),
    path('<str:uid>/export/xlsx/', views.export_xlsx, name='export_xlsx'),
]
