from fastapi.testclient import TestClient

from conformidade.main import create_app

client = TestClient(create_app())


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "conformidade"


def test_liveness():
    assert client.get("/health/live").json() == {"status": "alive"}


def test_readiness():
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_startup():
    assert client.get("/health/startup").status_code == 200
