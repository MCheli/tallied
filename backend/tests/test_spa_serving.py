"""The built SPA: index.html and the manifest revalidate on every load (so a Home Screen app picks up
a new release), hashed bundles and icons do not, and unknown /api paths stay JSON 404s."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import spa_response


def _client(static_dir):
    app = FastAPI()

    @app.get("/{full_path:path}")
    async def serve(full_path: str):
        return spa_response(static_dir, full_path)

    return TestClient(app)


def _static(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Tallied</title>")
    (tmp_path / "manifest.webmanifest").write_text('{"name": "Tallied"}')
    (tmp_path / "icon-192.png").write_bytes(b"\x89PNG")
    return tmp_path


def test_client_routes_get_index_html_that_revalidates(tmp_path):
    client = _client(_static(tmp_path))
    for path in ("/", "/spending", "/index.html"):
        res = client.get(path)
        assert res.status_code == 200
        assert "Tallied" in res.text
        assert res.headers["cache-control"] == "no-cache"


def test_manifest_revalidates_and_icons_do_not(tmp_path):
    client = _client(_static(tmp_path))
    assert client.get("/manifest.webmanifest").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/icon-192.png").headers


def test_unknown_api_path_is_json_404(tmp_path):
    res = _client(_static(tmp_path)).get("/api/v2/nothing")
    assert res.status_code == 404
    assert res.json() == {"detail": "Not Found"}


def test_path_outside_static_dir_falls_back_to_index(tmp_path):
    (tmp_path / "static").mkdir()
    static = _static(tmp_path / "static")
    (tmp_path / "secret.txt").write_text("nope")
    res = spa_response(static, "../secret.txt")
    assert str(res.path) == str(static.resolve() / "index.html")
