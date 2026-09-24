def test_docs_and_role_boundary(app_client):
    client, _ = app_client
    docs = client.get("/docs")
    assert docs.status_code == 200
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/api/v1/pipelines/run" in openapi.json()["paths"]
    denied = client.post("/api/v1/discovery/run", json={"source_id": "missing"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
