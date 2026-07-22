import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()
from api.models import StorageBucket
from minio import Minio

for bname in ['granth-development-media', 'granth-production-media']:
    b = StorageBucket.objects.get(bucket_name=bname)
    ep = b.endpoint if b.endpoint not in ('localhost:9000','minio:9000','127.0.0.1:9000') else '100.83.65.7:9000'
    c = Minio(ep, access_key=b.access_key, secret_key=b.secret_key, secure=False)
    objs = list(c.list_objects(b.bucket_name, prefix='books/', recursive=True))
    print(f'== {bname} ({ep}) objects={len(objs)} ==')
    # show covers and page counts per book
    covers = [o.object_name for o in objs if o.object_name.endswith('cover.png')]
    for cov in covers[:60]:
        print('  ', cov)
