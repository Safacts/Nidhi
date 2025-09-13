# backend/api/models.py
from django.db import models
import uuid

class DatabaseRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('error', 'Error'),
    ]

    # Use a UUID for the primary key for more security/flexibility
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # User details from the Attendance Project
    student_id = models.IntegerField()
    student_username = models.CharField(max_length=150)
    # We will add college_id later to implement multi-tenancy
    # college_id = models.CharField(max_length=100)

    # Database details
    db_name = models.CharField(max_length=63, unique=True) # Postgres db names have a 63 char limit
    db_user = models.CharField(max_length=63, unique=True)
    # We will NOT store the password in the database. It is revealed once and then discarded.

    # Request metadata
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.CharField(max_length=150, blank=True, null=True) # Admin's username

    def __str__(self):
        return f"{self.db_name} requested by {self.student_username} ({self.status})"