# backend/api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    
    # Student endpoints
    path('requests/create/', views.create_database_request, name='create_request'),
    path('requests/my/', views.list_my_requests, name='my_requests'),

    # Admin endpoints
    path('admin/requests/pending/', views.list_pending_requests, name='pending_requests'),
    path('admin/requests/approve/<uuid:request_id>/', views.approve_database_request, name='approve_request'),
    path('requests/reveal/<uuid:request_id>/', views.reveal_credentials, name='reveal_credentials'),
    path('requests/delete/<uuid:request_id>/', views.delete_database, name='delete_database'),
    path('requests/change-password/<uuid:request_id>/', views.change_password, name='change_password'),
     # --- ADD THESE TWO LINES ---
    path('requests/size/<uuid:request_id>/', views.get_database_size, name='get_database_size'),
    path('requests/tables/<uuid:request_id>/', views.list_database_tables, name='list_database_tables'),
]