import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()
from api.models import DatabaseInstance
import psycopg2
from psycopg2 import sql

iid = 'b909dfff-16fd-4803-9a45-5a158e5dad3b'
inst = DatabaseInstance.objects.get(id=iid)
srv = inst.server
u = sql.Identifier(inst.db_user)
conn = psycopg2.connect(dbname=inst.db_name, user=srv.root_user, password=srv.root_password, host=srv.host, port=srv.port)
conn.autocommit = True
cur = conn.cursor()
# reassign all objects owned by postgres (root) inside THIS db to the app user
cur.execute(sql.SQL("REASSIGN OWNED BY postgres TO {u};").format(u=u))
print("REASSIGN postgres->app OK")
cur.close(); conn.close()
