import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nidhi_backend.settings")
django.setup()
from api.models import DatabaseInstance, Product
instances = DatabaseInstance.objects.filter(db_name__icontains="vitharn").values('id', 'db_name', 'product__name', 'server__environment_type', 'is_deleted', 'status')
for i in instances:
    print(i)
