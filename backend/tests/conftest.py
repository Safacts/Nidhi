"""
Shared pytest fixtures for Nidhi tests.

The provisioning-task tests deliberately NEVER touch a real Postgres. They patch
`psycopg2.connect` (and `subprocess.run` for pg_dump/pg_restore) and feed the
tasks a fake connection that records the SQL strings that *would* have been sent.
We then assert the SQL is built correctly (CREATE/DROP DATABASE/USER/GRANT) and
that the connection was only ever aimed at a dummy test server — never the real
nidhi-db (5433) or nidhi-main_db (5435).
"""
import psycopg2
from unittest import mock
import pytest

# TESTING_STRATEGY.md #13 — safety-critical guard.
# The REAL nidhi-db (5433) / nidhi-main_db (5435) must never be touched by tests.
REAL_NIDHI_PORTS = {5433, 5435}
REAL_NIDHI_HOSTS = {"localhost", "127.0.0.1", "100.83.65.7", "72.60.218.127"}


class FakeCursor:
    """Records every cursor.execute() call and returns a canned fetchone()."""

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

    def __init__(self, exec_log, connect_log):
        self._exec_log = exec_log
        self._connect_log = connect_log

    def cursor(self):
        return FakeCursor(self._exec_log)

    def close(self):
        pass


def make_fake_connect(exec_log, connect_log, fetchone_value=(5,)):
    """Return a fake psycopg2.connect that records args and returns a FakeConn."""

    def _connect(*args, **kwargs):
        connect_log.append(kwargs)
        return FakeConn(exec_log, connect_log)

    return _connect


@pytest.fixture(autouse=True)
def _guard_no_real_psycopg2(monkeypatch):
    """Global safety net: every psycopg2.connect during a test is intercepted.

    If any code path tries to open a REAL connection to the production
    nidhi-db (5433) / nidhi-main_db (5435) — or any real nidhi host — the test
    FAILS immediately. This is the hard guarantee behind TESTING_STRATEGY #13:
    tests may only ever aim psycopg2.connect at a dummy test server.
    """
    real_connect = psycopg2.connect

    def _safe_connect(*args, **kwargs):
        host = str(kwargs.get("host", "") or (args[3] if len(args) > 3 else ""))
        port = kwargs.get("port")
        if isinstance(port, str):
            try:
                port = int(port)
            except ValueError:
                port = None
        if port in REAL_NIDHI_PORTS or host in REAL_NIDHI_HOSTS:
            raise AssertionError(
                f"TEST attempted a REAL psycopg2.connect to nidhi infra "
                f"(host={host!r}, port={port!r}). Tests must mock psycopg2.connect."
            )
        # Not a real nidhi server: return a fake so the test can record SQL.
        # (Provisioning tests replace this themselves; this is the backstop.)
        return FakeConn([], [])

    monkeypatch.setattr(psycopg2, "connect", _safe_connect)
    yield
    monkeypatch.setattr(psycopg2, "connect", real_connect)
