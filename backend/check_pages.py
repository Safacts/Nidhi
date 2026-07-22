import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()
from api.models import StorageBucket
from minio import Minio

b = StorageBucket.objects.get(bucket_name='granth-development-media')
c = Minio('100.83.65.7:9000', access_key=b.access_key, secret_key=b.secret_key, secure=False)

codes = ['GRN-000001','GRN-000002','GRN-000003','GRN-000004','GRN-000005',
         'GRN-000006','GRN-000007','GRN-000008','GRN-000009','GRN-00000A',
         'GRN-00000B','GRN-00000C','GRN-00000D','GRN-00000E','GRN-00000F',
         'GRN-000010','GRN-000011']

for code in codes:
    objs = list(c.list_objects(b.bucket_name, 'books/' + code + '/pages/', recursive=True))
    print(f'{code}: {len(objs)} pages')
