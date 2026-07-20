from rest_framework import serializers
from .models import DatabaseServer, Product, EmployeeProductAssignment, DatabaseInstance, DatabaseBackup, SystemAlert

class DatabaseServerSerializer(serializers.ModelSerializer):
    root_password = serializers.CharField(write_only=True)
    root_user = serializers.CharField(write_only=True, required=False, default='postgres')

    class Meta:
        model = DatabaseServer
        fields = ['id', 'name', 'host', 'port', 'root_user', 'root_password', 'environment_type', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']

class EmployeeProductAssignmentSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = EmployeeProductAssignment
        fields = ['id', 'sso_user_id', 'product', 'product_name', 'role']
        read_only_fields = ['id']

class DatabaseInstanceSerializer(serializers.ModelSerializer):
    server_name = serializers.CharField(source='server.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = DatabaseInstance
        fields = [
            'id', 'db_name', 'db_user', 'server', 'server_name', 'product', 'product_name',
            'status', 'created_by_sso_id', 'is_deleted', 'deleted_at',
            'backup_enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'db_user', 'status', 'created_by_sso_id', 'is_deleted', 'deleted_at', 'created_at', 'updated_at']

class DatabaseBackupSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatabaseBackup
        fields = ['id', 'instance', 's3_path', 'file_size_bytes', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']
class SystemAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemAlert
        fields = '__all__'
