import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()
from api.models import DatabaseInstance
import psycopg2
from psycopg2 import sql

iid = 'b909dfff-16fd-4803-9a45-5a158e5dad3b'
inst = DatabaseInstance.objects.get(id=iid)
srv = inst.server
pw = inst.db_password_temp
uname = inst.db_user
u = sql.Identifier(uname)          # for CREATE/ALTER USER (quoted identifier - OK)
ulit = sql.Literal(uname)          # for rolname comparison (string literal)
p = sql.Literal(pw)

conn = psycopg2.connect(dbname='postgres', user=srv.root_user, password=srv.root_password, host=srv.host, port=srv.port)
conn.autocommit = True
cur = conn.cursor()
cur.execute(sql.SQL("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname={ulit}) THEN CREATE USER {u} WITH PASSWORD {p}; END IF; END $$;").format(ulit=ulit, u=u, p=p))
print("ensure user OK")
cur.execute(sql.SQL("ALTER USER {u} WITH PASSWORD {p};").format(u=u, p=p))
print("alter pw OK")
cur.execute(sql.SQL("GRANT ALL PRIVILEGES ON DATABASE {db} TO {u};").format(db=sql.Identifier(inst.db_name), u=u))
conn2 = psycopg2.connect(dbname=inst.db_name, user=srv.root_user, password=srv.root_password, host=srv.host, port=srv.port)
conn2.autocommit = True
c2 = conn2.cursor()
c2.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {u};").format(u=u))
c2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {u};").format(u=u))
c2.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {u};").format(u=u))
c2.execute(sql.SQL("ALTER ROLE {u} SET search_path TO public;").format(u=u))
c2.close(); conn2.close(); cur.close(); conn.close()
print("GRANT ALL OK -> vitharn_production_user re-provisioned with Nidhi-stored password")
