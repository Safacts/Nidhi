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
# make app user own the public schema (so it controls all objects)
cur.execute(sql.SQL("ALTER SCHEMA public OWNER TO {u};").format(u=u))
# grant full perms on ALL existing tables/sequences/types in public
cur.execute(sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA public TO {u};").format(u=u))
cur.execute(sql.SQL("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {u};").format(u=u))
cur.execute(sql.SQL("GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO {u};").format(u=u))
print("GRANT ALL ON ALL OBJECTS IN public -> app user OK")
cur.close(); conn.close()
