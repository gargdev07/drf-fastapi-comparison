from fastapi.testclient import TestClient
import main


def test_crud_and_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    with TestClient(main.app) as client:
        root = client.get("/", follow_redirects=False)
        assert root.status_code == 307
        assert root.headers["location"] == "/docs"
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/api/v1/health").json()["data"]["framework"] == "FastAPI"
        created = client.post("/api/v1/products", json={"title": "Test item", "price": 5, "category": "Test"})
        assert created.status_code == 201
        item_id = created.json()["data"]["id"]
        assert client.get(f"/api/v1/products/{item_id}").status_code == 200
        assert client.patch(f"/api/v1/products/{item_id}", json={"stock": 4}).json()["data"]["stock"] == 4
        assert client.delete(f"/api/v1/products/{item_id}").json()["data"]["deleted"] is True
        invalid = client.post("/api/v1/products", json={"title": "x", "price": -1, "category": "Test"})
        assert invalid.status_code == 422
        assert isinstance(invalid.json()["detail"], list)
        assert {issue["loc"][-1] for issue in invalid.json()["detail"]} >= {"title", "price"}


def test_dummyjson_route_is_reachable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "import.sqlite3")

    class DummyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"products": [{"title": "Imported item", "price": 3, "category": "Test", "stock": 2}]}

    monkeypatch.setattr(main.httpx, "get", lambda *args, **kwargs: DummyResponse())
    with TestClient(main.app) as client:
        response = client.post("/api/v1/products/import-dummyjson")
        assert response.status_code == 200
        assert response.json()["data"] == {"fetched": 1, "created": 1, "skipped": 0, "existing": 0, "cache_hit": False, "source": "DummyJSON"}
        again = client.post("/api/v1/products/import-dummyjson")
        assert again.json()["data"]["created"] == 0
        assert again.json()["data"]["skipped"] == 1
