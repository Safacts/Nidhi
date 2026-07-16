"""
Provisioning task tests — TESTING_STRATEGY #13 (safety-critical).

These exercise the REAL provisioning logic in api/tasks.py:
    * provision_database_task
    * replicate_prod_to_dev
    * refresh_single_delayed_replica

CRITICAL: psycopg2.connect is FULLY MOCKED (and subprocess for pg_dump /
pg_restore). No real CREATE/DROP DATABASE is ever executed. We assert:
  1. The correct SQL (CREATE USER / CREATE DATABASE / GRANT / DROP DATABASE
     IF EXISTS) is *built* with the right identifiers.
  2. psycopg2.connect is only ever aimed at a dummy test server
     (host="test.db.local", port=5442) — never the real 5433/5435 servers.
  3. On connect failure the instance is marked 'failed' (no silent success).
"""
from unittest import mock
import pytest
from psycopg2 import sql as psycopg_sql

from api.models import DatabaseServer, DatabaseInstance, Product

pytestmark = pytest.mark.django_db


# --- Render a psycopg2.sql.Composed to its final SQL text (no real server) ----
def render_query(q):
    if isinstance(q, str):
        return q
    out = []
    for part in q:
        if isinstance(part, psycopg_sql.SQL):
            out.append(part.string)
        elif isinstance(part, psycopg_sql.Identifier):
            name = part.strings[0] if part.strings else ""
            out.append(f'"{name}"')
        elif isinstance(part, psycopg_sql.Literal):
            out.append(repr(part.wrapped))
        else:
            out.append(str(part))
    return "".join(out)


# --- Fake psycopg2 surface (so NO real server is ever reached) ---------------
class FakeCursor:
    def __init__(self, exec_log, fetchone_value=(5,)):
        self._exec_log = exec_log
        self._fetchone_value = fetchone_value

    def execute(self, query, params=None):
        self._exec_log.append((query, params))

    def fetchone(self):
        return self._fetchone_value

    def close(self):
        pass


class FakeConn:
    autocommit = False

    def __init__(self, exec_log, connect_log, fetchone_value=(5,)):
        self._exec_log = exec_log
        self._connect_log = connect_log
        self._fetchone_value = fetchone_value

    def cursor(self):
        return FakeCursor(self._exec_log, self._fetchone_value)

    def close(self):
        pass


def make_fake_connect(exec_log, connect_log, fetchone_value=(5,)):
    def _connect(*args, **kwargs):
        connect_log.append(kwargs)
        return FakeConn(exec_log, connect_log, fetchone_value)
    return _connect


DUMMY_HOST = "test.db.local"
DUMMY_PORT = 5442


def _make_server(name="test-srv", env="production"):
    return DatabaseServer.objects.create(
        name=name,
        host=DUMMY_HOST,
        port=DUMMY_PORT,
        root_user="postgres",
        root_password="super-secret-root",
        environment_type=env,
        is_active=True,
    )


def _make_product(name="testproduct"):
    return Product.objects.create(name=name)


def _make_instance(server, product, db_name="test_db", status="provisioning"):
    return DatabaseInstance.objects.create(
        server=server,
        product=product,
        db_name=db_name,
        db_user=f"{db_name}_user",
        db_password_temp="temp-pw-123",
        created_by_sso_id="tester",
        status=status,
    )


def _mock_subprocess_ok():
    res = mock.MagicMock()
    res.returncode = 0
    res.stderr = ""
    return res


def _subprocess_command_strings(mock_run):
    """Extract the rendered command lines passed to subprocess.run."""
    out = []
    for call in mock_run.call_args_list:
        args, _kwargs = call
        if args:
            out.append(" ".join(str(a) for a in args[0]))
    return out


# ---------------------------------------------------------------------------
# 1. provision_database_task
# ---------------------------------------------------------------------------
def test_provision_database_task_builds_sql_and_marks_available():
    server = _make_server()
    product = _make_product()
    inst = _make_instance(server, product)

    exec_log, connect_log = [], []
    fake_connect = make_fake_connect(exec_log, connect_log)

    with mock.patch("psycopg2.connect", side_effect=fake_connect), \
         mock.patch("subprocess.run", return_value=_mock_subprocess_ok()):
        from api import tasks
        tasks.provision_database_task(str(inst.id))

    inst.refresh_from_db()
    assert inst.status == "available"

    texts = [render_query(q) for q, _ in exec_log]
    assert any("CREATE USER" in t for t in texts), texts
    assert any("CREATE DATABASE" in t for t in texts), texts
    assert any('"test_db"' in t for t in texts), texts
    assert any("GRANT ALL PRIVILEGES ON DATABASE" in t for t in texts), texts

    # No real server was touched: connect only ever aimed at our dummy server.
    assert connect_log, "psycopg2.connect was never called"
    for kw in connect_log:
        assert kw.get("host") == DUMMY_HOST
        assert kw.get("port") == DUMMY_PORT


def test_provision_database_task_marks_failed_on_connect_error():
    server = _make_server()
    product = _make_product()
    inst = _make_instance(server, product)

    with mock.patch("psycopg2.connect", side_effect=RuntimeError("cannot reach db")), \
         mock.patch("subprocess.run", return_value=_mock_subprocess_ok()):
        from api import tasks
        tasks.provision_database_task(str(inst.id))

    inst.refresh_from_db()
    assert inst.status == "failed"


def test_provision_database_task_never_targets_real_nidhi_dbs():
    """Explicit guard: a provisioning run must refuse to touch 5433/5435."""
    server = _make_server()
    product = _make_product()
    inst = _make_instance(server, product)

    exec_log, connect_log = [], []
    fake_connect = make_fake_connect(exec_log, connect_log)

    with mock.patch("psycopg2.connect", side_effect=fake_connect), \
         mock.patch("subprocess.run", return_value=_mock_subprocess_ok()):
        from api import tasks
        tasks.provision_database_task(str(inst.id))

    for kw in connect_log:
        assert kw.get("host") != "localhost"
        assert kw.get("port") not in (5433, 5435)


# ---------------------------------------------------------------------------
# 2. replicate_prod_to_dev
# ---------------------------------------------------------------------------
def test_replicate_prod_to_dev_creates_available_dev_instance():
    prod_server = _make_server(name="prod-srv", env="production")
    dev_server = _make_server(name="dev-srv", env="development")
    product = _make_product()
    prod_inst = _make_instance(prod_server, product, db_name="new_nova_prod",
                               status="available")

    exec_log, connect_log = [], []
    fake_connect = make_fake_connect(exec_log, connect_log)

    with mock.patch("psycopg2.connect", side_effect=fake_connect) as _mc, \
         mock.patch("subprocess.run", return_value=_mock_subprocess_ok()) as mock_run, \
         mock.patch("os.remove"):
        from api import tasks
        new_id = tasks.replicate_prod_to_dev(str(prod_inst.id), str(dev_server.id),
                                            "new_nova_dev")

    assert new_id is not None
    dev_inst = DatabaseInstance.objects.get(id=new_id)
    assert dev_inst.status == "available"
    assert dev_inst.db_name == "new_nova_dev"

    texts = [render_query(q) for q, _ in exec_log]
    assert any('CREATE DATABASE' in t and '"new_nova_dev"' in t for t in texts), texts
    assert any("CREATE USER" in t for t in texts), texts

    # pg_dump + pg_restore must have been invoked (mocked, so no real dump).
    cmds = _subprocess_command_strings(mock_run)
    assert any("pg_dump" in c for c in cmds), cmds
    assert any("pg_restore" in c for c in cmds), cmds


def test_replicate_prod_to_dev_marks_failed_when_dump_fails():
    prod_server = _make_server(name="prod-srv", env="production")
    dev_server = _make_server(name="dev-srv", env="development")
    product = _make_product()
    prod_inst = _make_instance(prod_server, product, db_name="new_nova_prod",
                               status="available")

    bad_dump = mock.MagicMock()
    bad_dump.returncode = 1
    bad_dump.stderr = "pg_dump: error"

    with mock.patch("psycopg2.connect", side_effect=mock.MagicMock()), \
         mock.patch("subprocess.run", return_value=bad_dump):
        from api import tasks
        result = tasks.replicate_prod_to_dev(str(prod_inst.id), str(dev_server.id),
                                             "new_nova_dev")

    assert result is None
    # No dev instance should have been created (dump failed before record create).
    assert not DatabaseInstance.objects.filter(db_name="new_nova_dev").exists()


# ---------------------------------------------------------------------------
# 3. refresh_single_delayed_replica
# ---------------------------------------------------------------------------
def test_refresh_delayed_replica_builds_and_returns_replica_name():
    server = _make_server()
    product = _make_product()
    inst = _make_instance(server, product, db_name="orders_prod", status="available")
    expected = "orders_prod_delayed_replica"

    exec_log, connect_log = [], []
    fake_connect = make_fake_connect(exec_log, connect_log)

    with mock.patch("psycopg2.connect", side_effect=fake_connect), \
         mock.patch("subprocess.run", return_value=_mock_subprocess_ok()):
        from api import tasks
        result = tasks.refresh_single_delayed_replica(str(inst.id))

    assert result == expected
    texts = [render_query(q) for q, _ in exec_log]
    assert any("DROP DATABASE IF EXISTS" in t for t in texts), texts
    assert any('CREATE DATABASE' in t and '"orders_prod_delayed_replica"' in t
               for t in texts), texts


def test_refresh_delayed_replica_fails_when_restore_empty():
    server = _make_server()
    product = _make_product()
    inst = _make_instance(server, product, db_name="orders_prod", status="available")

    exec_log, connect_log = [], []
    # fetchone returns (0,) -> empty replica -> task must fail (no silent success)
    fake_connect = make_fake_connect(exec_log, connect_log, fetchone_value=(0,))

    with mock.patch("psycopg2.connect", side_effect=fake_connect), \
         mock.patch("subprocess.run", return_value=_mock_subprocess_ok()):
        from api import tasks
        result = tasks.refresh_single_delayed_replica(str(inst.id))

    assert result is None
