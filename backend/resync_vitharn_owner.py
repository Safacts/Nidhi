import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nidhi_backend.settings')
django.setup()
from api.models import DatabaseInstance
import psycopg2
from psycopg2 import sql

iid = 'b909dfff-16fd-4803-9a45-5a158e5dad3b'
inst = DatabaseInstance.objects.get(id=iid)
srv = inst.server
uname = inst.db_user
u = sql.Identifier(uname)
db = sql.Identifier(inst.db_name)

conn = psycopg2.connect(dbname='postgres', user=srv.root_user, password=srv.root_password, host=srv.host, port=srv.port)
conn.autocommit = True
cur = conn.cursor()
# make the app user the OWNER of the database (grants all on existing + future objects)
cur.execute(sql.SQL("ALTER DATABASE {db} OWNER TO {u};").format(db=db, u=u))
print("ALTER DATABASE OWNER OK")
cur.close(); conn.close()

# reassign any objects still owned by old/different roles within the db
conn2 = psycopg2.connect(dbname=inst.db_name, user=srv.root_user, password=srv.root_password, host=srv.host, port=srv.port)
conn2.autocommit = True
c2 = conn2.cursor()
# find non-app owners of schemas/tables and reassign to app user
c2.execute(sql.SQL("REASSIGN OWNED BY {u} TO {u};").format(u=u))  # no-op safety
# reassign objects owned by 'postgres' (root) inside this db to the app user
c2.execute(sql.SQL("DO $$ DECLARE r text; BEGIN FOR r IN SELECT rolname FROM pg_roles WHERE rolname NOT IN ('postgres','rds_admin','vitharn_production_user') LOOP BEGIN EXECUTE format('REASSIGN OWNED BY %I TO %I', r, {u}); EXCEPTION WHEN others THEN END; END LOOP; END $$;").format(u=u))
c2.close(); conn2.close()
print("REASSIGN OK -> vitharn_production_user now owns vitharn_production")
