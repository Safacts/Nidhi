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
]