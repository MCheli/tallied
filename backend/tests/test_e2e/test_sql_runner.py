"""SQL runner isolation against real PostgreSQL (PLAT-DB-001)."""
import pytest

pytestmark = pytest.mark.e2e


def _run(client, sql):
    return client.post("/api/v1/admin/query", json={"sql": sql, "limit": 10})


class TestSqlRunnerIsolation:
    def test_select_inside_tenant_schema_works(self, client, seed_test_data):
        resp = _run(client, "SELECT count(*) AS n FROM accounts")
        assert resp.status_code == 200, resp.text
        assert resp.json()["rows"][0]["n"] >= 3

    @pytest.mark.parametrize("sql", [
        "SELECT email FROM users",
        'SELECT * FROM "public"."users"',
        "SELECT * FROM api_keys",
        "SELECT rolname FROM pg_authid",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM tenants",
    ])
    def test_platform_tables_and_superuser_functions_are_refused(self, client, seed_test_data, sql):
        resp = _run(client, sql)
        assert resp.status_code == 400, resp.text
        assert "password" not in resp.text.lower() or "permission denied" in resp.text.lower()

    def test_other_tenant_schema_is_refused(self, client, seed_test_data, second_tenant_setup):
        other = second_tenant_setup["tenant_schema"]
        resp = _run(client, f'SELECT * FROM "{other}".accounts')
        assert resp.status_code == 400

    def test_writes_are_refused_even_if_wrapped(self, client, seed_test_data):
        resp = _run(client, "WITH x AS (SELECT nextval('accounts_id_seq')) SELECT 1")
        assert resp.status_code == 400

    def test_statement_timeout_applies(self, client, seed_test_data):
        resp = _run(client, "SELECT pg_sleep(8)")
        assert resp.status_code == 400
        assert "timeout" in resp.text.lower() or "canceling" in resp.text.lower()
