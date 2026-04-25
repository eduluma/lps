from fastapi.testclient import TestClient


def test_healthz_smoke():
    # Importing here to avoid DB init at collection time.
    from app.main import app

    # Lifespan needs a running DB; this is a placeholder smoke test.
    assert app.title == "LPS API"
