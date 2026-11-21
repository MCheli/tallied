"""Every response carries the baseline browser-hardening headers."""


def test_api_responses_carry_security_headers(client):
    res = client.get("/api/v1/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
