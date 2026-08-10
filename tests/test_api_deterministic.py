from fastapi.testclient import TestClient

from conformidade.main import create_app

client = TestClient(create_app())


def test_lista_controles():
    r = client.get("/api/v1/controls")
    assert r.status_code == 200
    controles = r.json()
    assert len(controles) >= 30
    assert all(c["control_id"].startswith("CONF-") for c in controles)


def test_analisa_dockerfile_enviado():
    r = client.post(
        "/api/v1/analyze",
        files={"file": ("Dockerfile", b"FROM ubuntu\nRUN sudo apt-get update\n")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["artifact"]["kind"] == "dockerfile"
    assert body["summary"]["total"] > 0
    assert {f["control_id"] for f in body["findings"]} >= {"CONF-IMG-001", "CONF-DKR-007"}


def test_analisa_manifesto_kubernetes():
    manifesto = (
        b"apiVersion: v1\nkind: Pod\nmetadata:\n  name: p\nspec:\n"
        b"  containers:\n    - name: c\n      image: nginx:latest\n"
        b"      securityContext:\n        privileged: true\n"
    )
    r = client.post("/api/v1/analyze", files={"file": ("pod.yaml", manifesto)})
    assert r.status_code == 200
    assert "CONF-WLD-001" in {f["control_id"] for f in r.json()["findings"]}


def test_formato_desconhecido_retorna_422():
    r = client.post("/api/v1/analyze", files={"file": ("notas.txt", b"texto qualquer\n")})
    assert r.status_code == 422


def test_arquivo_vazio_retorna_400():
    r = client.post("/api/v1/analyze", files={"file": ("Dockerfile", b"   \n")})
    assert r.status_code == 400


def test_arquivo_grande_demais_retorna_413():
    grande = b"FROM alpine\n" + b"# padding\n" * 300_000
    r = client.post("/api/v1/analyze", files={"file": ("Dockerfile", grande)})
    assert r.status_code == 413
