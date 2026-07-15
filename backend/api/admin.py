from django.contrib import admin
from .models import (
    DatabaseServer,
    Product,
    EmployeeProductAssignment,
    DatabaseInstance,
    DatabaseBackup,
    StorageBucket,
    SystemAlert,
    InstanceHeartbeat,
)


@admin.register(DatabaseServer)
class DatabaseServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'host', 'port', 'environment_type', 'is_active')
    list_filter = ('environment_type', 'is_active')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')


@admin.register(EmployeeProductAssignment)
class EmployeeProductAssignmentAdmin(admin.ModelAdmin):
    list_display = ('sso_user_id', 'product', 'role')
    list_filter = ('role',)


@admin.register(DatabaseInstance)
class DatabaseInstanceAdmin(admin.ModelAdmin):
    list_display = ('db_name', 'server', 'product', 'status', 'is_deleted', 'created_at')
    list_filter = ('status', 'is_deleted', 'server')
    search_fields = ('db_name', 'db_user')


@admin.register(DatabaseBackup)
class DatabaseBackupAdmin(admin.ModelAdmin):
    list_display = ('instance', 'status', 'file_size_bytes', 'created_at')
    list_filter = ('status',)


@admin.register(StorageBucket)
class StorageBucketAdmin(admin.ModelAdmin):
    """SCRUM-287: allows editing a bucket's endpoint/server for relocation."""
    list_display = ('bucket_name', 'product', 'server', 'endpoint', 'status')
    list_filter = ('status', 'server')
    search_fields = ('bucket_name',)
    fields = ('product', 'server', 'bucket_name', 'endpoint', 'access_key', 'secret_key',
              'status', 'created_by_sso_id')


@admin.register(SystemAlert)
class SystemAlertAdmin(admin.ModelAdmin):
    list_display = ('level', 'title', 'is_read', 'created_at')
    list_filter = ('level', 'is_read')


@admin.register(InstanceHeartbeat)
class InstanceHeartbeatAdmin(admin.ModelAdmin):
    list_display = ('instance', 'is_valid', 'last_heartbeat_at', 'stale_alerted')
    list_filter = ('is_valid', 'stale_alerted')
