from django.urls import path
from . import views

urlpatterns = [
    path('instances/auto-provision/', views.auto_provision_instance, name='auto_provision_instance'),
    path('servers/auto-register/', views.auto_register_server, name='auto_register_server'),
    path('servers/', views.server_list_create, name='server_list_create'),
    path('products/', views.product_list_create, name='product_list_create'),
    path('instances/', views.database_instance_list_create, name='database_instance_list_create'),
    path('instances/<uuid:instance_id>/delete/', views.delete_database, name='delete_database'),
    path('instances/<uuid:instance_id>/reveal/', views.reveal_credentials, name='reveal_credentials'),
    path('instances/<uuid:instance_id>/replicate/', views.replicate_to_dev, name='replicate_to_dev'),
    path('sso/callback/', views.sso_callback, name='sso_callback'),
    path('me/', views.me, name='me'),
]