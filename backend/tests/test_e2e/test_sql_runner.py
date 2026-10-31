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


class TestSqlRunnerPerTenantRole:
    """Each tenant's queries run as its own role, so text tricks that slip past the regex still hit a
    permission error. Before 2026-10-31 one shared role held SELECT on every tenant that had run a query."""

    @pytest.mark.parametrize("sql", [
        "SELECT query_to_xml('select * from '||'{other}'||'.accounts', true, false, '')",
        'SELECT * FROM U&"{other_escaped}".accounts',
        "SELECT set_config('search_path', '{other}', true), query_to_xml('select * from accounts', true, false, '')",
    ])
    def test_other_tenant_is_refused_even_when_the_regex_is_bypassed(
            self, client, client2, seed_test_data, second_tenant_setup, sql):
        other = second_tenant_setup["tenant_schema"]
        # The other tenant runs a query first, which is what used to grant the shared role its schema.
        assert client2.post("/api/v1/admin/query", json={"sql": "SELECT 1 AS one", "limit": 1}).status_code == 200
        escaped = "\\0074" + other[1:]  # U&"\0074enant_..." names the schema without matching tenant_\w
        resp = _run(client, sql.format(other=other, other_escaped=escaped))
        assert resp.status_code == 400, resp.text
        # set_config's search_path does not reach query_to_xml's lookup, so that one fails on the name instead.
        assert "permission denied" in resp.text.lower() or "does not exist" in resp.text.lower()

    def test_tenants_get_distinct_runner_roles(self, pg_engine, seed_test_data, second_tenant_setup, e2e_setup):
        from sqlalchemy import text

        from app.services.sql_runner import LEGACY_SHARED_ROLE, ensure_runner_role

        mine = ensure_runner_role(e2e_setup["tenant_schema"])
        theirs = ensure_runner_role(second_tenant_setup["tenant_schema"])
        assert mine != theirs
        with pg_engine.connect() as conn:
            can_read = conn.execute(
                text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"),
                {"role": mine, "schema": second_tenant_setup["tenant_schema"]},
            ).scalar()
            legacy = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": LEGACY_SHARED_ROLE}).scalar()
        assert can_read is False
        assert legacy is None
