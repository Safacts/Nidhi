# backend/api/serializers.py
from rest_framework import serializers
from .models import DatabaseRequest

class DatabaseRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatabaseRequest
        # Fields that can be read from the model
        read_only_fields = (
            'id',
            'student_id',
            'student_username',
            'db_user',
            'status',
            'created_at',
            'updated_at',
            'approved_by',
        )
        # All other fields can be written to
        fields = read_only_fields + ('db_name',)