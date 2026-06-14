from django.urls import path
from . import views

urlpatterns = [
    path('', views.form_list, name='form_list'),
    path('manual/', views.manual, name='manual'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/module-download/<str:uid>/', views.module_download, name='module_download'),
    path('settings/module-upload/<str:uid>/', views.module_upload, name='module_upload'),
    path('users/', views.user_list, name='user_list'),
    path('users/<int:user_id>/activate/', views.user_activate, name='user_activate'),
    path('users/<int:user_id>/deactivate/', views.user_deactivate, name='user_deactivate'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:user_id>/reset-link/', views.generate_reset_link, name='generate_reset_link'),
    path('groups/<int:group_id>/', views.group_edit, name='group_edit'),
    path('my-group/', views.my_group, name='my_group'),
    path('my-group/<int:user_id>/', views.my_group, name='my_group_action'),
    path('<str:uid>/', views.coverage, name='coverage'),
    path('<str:uid>/submissions/', views.submission_list, name='submission_list'),
    path('<str:uid>/submission/<int:sub_id>/', views.submission_detail, name='submission_detail'),
    path('<str:uid>/refresh/', views.refresh_form, name='refresh_form'),
    path('<str:uid>/export/csv/', views.export_csv, name='export_csv'),
    path('<str:uid>/export/xlsx/', views.export_xlsx, name='export_xlsx'),
]
