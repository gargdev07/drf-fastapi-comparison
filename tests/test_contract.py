"""Cross-framework contract tests against isolated local SQLite databases."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/fastapi_app"))
sys.path.insert(0, str(ROOT / "backend/drf_app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from rest_framework.test import APIClient
from fastapi.testclient import TestClient
import main as fastapi_main


@pytest.fixture
def apis(tmp_path, monkeypatch):
    from products import views as drf_views

    monkeypatch.setattr(fastapi_main, "DB_PATH", tmp_path / "fastapi.sqlite3")
    _reset_import_cache(drf_views)
    original = settings.DATABASES["default"]["NAME"]
    settings.DATABASES["default"]["NAME"] = str(tmp_path / "drf.sqlite3")
    connections.close_all()
    try:
        call_command("migrate", verbosity=0, interactive=False)
        with TestClient(fastapi_main.app) as fastapi:
            yield fastapi, APIClient()
    finally:
        _reset_import_cache(drf_views)
        connections.close_all()
        settings.DATABASES["default"]["NAME"] = original


def test_contract_validation_and_crud(apis):
    fa, drf = apis
    payload = {"title": "Contract product", "description": "fixture", "price": .01, "category": "Test", "stock": 0, "image": "https://dummyjson.com/image/400x300"}
    created = [fa.post("/api/v1/products", json=payload), drf.post("/api/v1/products", payload, format="json")]
    assert [r.status_code for r in created] == [201, 201]
    assert set(created[0].json()["data"]) == set(created[1].data["data"])
    ids = [created[0].json()["data"]["id"], created[1].data["data"]["id"]]
    assert fa.patch(f"/api/v1/products/{ids[0]}", json={"stock": 4}).status_code == drf.patch(f"/api/v1/products/{ids[1]}", {"stock": 4}, format="json").status_code == 200
    cases = [
        ({**payload, "price": 0}, 422), ({**payload, "price": .001}, 422),
        ({**payload, "stock": -1}, 422),
        ({**payload, "image": "not a url"}, 422), ({"price": 2, "category": "Test"}, 422),
        ({**payload, "extra": True}, 422), ({**payload, "title": ["wrong"]}, 422),
        ({**payload, "title": 7}, 422), ({**payload, "stock": "not an integer"}, 422),
        ({**payload, "stock": 1.5}, 422), ({**payload, "price": True}, 422),
    ]
    for body, expected in cases:
        actual = [fa.post("/api/v1/products", json=body).status_code, drf.post("/api/v1/products", body, format="json").status_code]
        assert actual == [expected, expected], body
    empty = [fa.patch(f"/api/v1/products/{ids[0]}", json={}), drf.patch(f"/api/v1/products/{ids[1]}", {}, format="json")]
    assert [r.status_code for r in empty] == [422, 422]
    put_missing = [fa.put(f"/api/v1/products/{ids[0]}", json={"title":"Incomplete"}), drf.put(f"/api/v1/products/{ids[1]}", {"title":"Incomplete"}, format="json")]
    assert [r.status_code for r in put_missing] == [422, 422]
    missing = [fa.get("/api/v1/products/2147483000"), drf.get("/api/v1/products/2147483000")]
    assert [r.status_code for r in missing] == [404, 404]
    assert fa.get("/api/v1/health").json()["data"]["status"] == drf.get("/api/v1/health").data["data"]["status"] == "ok"
    assert set(fa.get("/api/v1/products?limit=5").json()["data"][0]) == set(drf.get("/api/v1/products?limit=5").data["data"][0])


def test_patch_edge_cases_are_equivalent_and_partial(apis):
    fa, drf = apis
    clients = {"fastapi": fa, "drf": drf}
    product = {
        "title": "PATCH contract product",
        "description": "leave this unchanged",
        "price": 17.25,
        "category": "Contract tests",
        "stock": 4,
        "image": "https://example.com/product.png",
    }
    product_ids = {}
    before = {}

    def body(key, response):
        return response.json() if key == "fastapi" else response.data

    def send(key, method, path, payload=None):
        client = clients[key]
        action = getattr(client, method)
        if key == "fastapi":
            return action(path, json=payload) if payload is not None else action(path)
        return action(path, payload, format="json") if payload is not None else action(path)

    for key, client in clients.items():
        created = send(key, "post", "/api/v1/products", product)
        assert created.status_code == 201
        before[key] = body(key, created)["data"]
        product_ids[key] = before[key]["id"]

    updated = {}
    for key, client in clients.items():
        path = f"/api/v1/products/{product_ids[key]}"
        response = send(key, "patch", path, {"stock": 9})
        assert response.status_code == 200
        updated[key] = body(key, response)["data"]
        assert updated[key]["stock"] == 9
        for field in ("title", "description", "price", "category", "image"):
            assert updated[key][field] == before[key][field]
        assert set(updated[key]) == set(before[key])

    invalid_payloads = [
        {"price": -0.01},
        {"stock": -1},
        {"unexpected": "field"},
        {},
        {"image": "not a URL"},
        {"image": "file:///invalid.png"},
        *[{field: None} for field in ("title", "description", "price", "category", "stock", "image")],
    ]
    for payload in invalid_payloads:
        responses = []
        for key in clients:
            path = f"/api/v1/products/{product_ids[key]}"
            response = send(key, "patch", path, payload)
            responses.append(response)
        assert [response.status_code for response in responses] == [422, 422], payload
        assert all("detail" in body(key, response) for key, response in zip(clients, responses))

    missing = []
    for key in clients:
        path = "/api/v1/products/2147483000"
        missing.append(send(key, "patch", path, {"stock": 2}))
    assert [response.status_code for response in missing] == [404, 404]

    for key in clients:
        path = f"/api/v1/products/{product_ids[key]}"
        current = send(key, "get", path)
        assert body(key, current)["data"] == updated[key]


def _reset_import_cache(drf_views):
    fastapi_main._dummyjson_cache = []
    fastapi_main._dummyjson_cache_until = 0
    drf_views._upstream_cache = []
    drf_views._upstream_cache_until = 0


def test_dummyjson_first_repeat_counts_and_cache(apis, monkeypatch):
    fa, drf = apis
    from products import views as drf_views

    _reset_import_cache(drf_views)
    payload = {
        "products": [
            {"title": "zz_contract_import_alpha", "description": "first", "price": 1.2, "category": "Import tests", "stock": 2, "thumbnail": "https://example.com/a.png"},
            {"title": "zz_contract_import_alpha", "description": "duplicate", "price": 1.3, "category": "Import tests", "stock": 3, "thumbnail": "https://example.com/a.png"},
            {"title": "zz_contract_import_beta", "description": "second", "price": 2.4, "category": "Import tests", "stock": 4, "thumbnail": "https://example.com/b.png"},
        ]
    }
    upstream_calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    def mocked_get(*args, **kwargs):
        upstream_calls.append((args, kwargs))
        return Response()

    monkeypatch.setattr(fastapi_main.httpx, "get", mocked_get)
    monkeypatch.setattr(drf_views.httpx, "get", mocked_get)
    for key, client in (("fastapi", fa), ("drf", drf)):
        route = "/api/v1/products/import-dummyjson"
        first = client.post(route) if key == "fastapi" else client.post(route, {}, format="json")
        second = client.post(route) if key == "fastapi" else client.post(route, {}, format="json")
        first_data = first.json()["data"] if key == "fastapi" else first.data["data"]
        second_data = second.json()["data"] if key == "fastapi" else second.data["data"]
        assert first.status_code == second.status_code == 200
        assert (first_data["fetched"], first_data["created"], first_data["skipped"], first_data["existing"]) == (3, 2, 1, 1)
        assert first_data["cache_hit"] is False
        assert (second_data["fetched"], second_data["created"], second_data["skipped"], second_data["existing"]) == (3, 0, 3, 3)
        assert second_data["cache_hit"] is True
        listing = client.get("/api/v1/products?q=zz_contract_import_")
        listing_data = listing.json() if key == "fastapi" else listing.data
        assert listing_data["meta"]["total"] == 2
    assert len(upstream_calls) == 2  # One source request per backend; each repeated import used its cache.


def test_dummyjson_empty_response(apis, monkeypatch):
    fa, drf = apis
    from products import views as drf_views

    _reset_import_cache(drf_views)

    class EmptyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"products": []}

    monkeypatch.setattr(fastapi_main.httpx, "get", lambda *args, **kwargs: EmptyResponse())
    monkeypatch.setattr(drf_views.httpx, "get", lambda *args, **kwargs: EmptyResponse())
    for key, client in (("fastapi", fa), ("drf", drf)):
        response = client.post("/api/v1/products/import-dummyjson") if key == "fastapi" else client.post("/api/v1/products/import-dummyjson", {}, format="json")
        data = response.json()["data"] if key == "fastapi" else response.data["data"]
        assert response.status_code == 200
        assert (data["fetched"], data["created"], data["skipped"], data["existing"]) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "upstream_payload",
    [
        {"unexpected": []},
        {"products": [{"title": "zz_invalid_import_should_not_persist", "category": "Import tests", "price": 1, "stock": -1}]},
        {"products": [{"title": "zz_invalid_import_should_not_persist", "category": "Import tests", "price": 1, "stock": 1, "thumbnail": "file:///invalid.png"}]},
    ],
    ids=("malformed-response", "invalid-product-stock", "invalid-product-image"),
)
def test_dummyjson_rejects_malformed_or_invalid_products_without_partial_import(apis, monkeypatch, upstream_payload):
    fa, drf = apis
    from products import views as drf_views

    _reset_import_cache(drf_views)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return upstream_payload

    monkeypatch.setattr(fastapi_main.httpx, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(drf_views.httpx, "get", lambda *args, **kwargs: Response())
    for key, client in (("fastapi", fa), ("drf", drf)):
        response = client.post("/api/v1/products/import-dummyjson") if key == "fastapi" else client.post("/api/v1/products/import-dummyjson", {}, format="json")
        assert response.status_code == 502, (key, response.status_code)
        listing = client.get("/api/v1/products?q=zz_invalid_import_should_not_persist")
        listing_data = listing.json() if key == "fastapi" else listing.data
        assert listing_data["meta"]["total"] == 0


def test_dummyjson_network_timeout_is_mocked_and_reported(apis, monkeypatch):
    fa, drf = apis
    from products import views as drf_views

    _reset_import_cache(drf_views)
    calls = []

    def timeout(*args, **kwargs):
        calls.append((args, kwargs))
        raise fastapi_main.httpx.TimeoutException("mocked timeout")

    monkeypatch.setattr(fastapi_main.httpx, "get", timeout)
    monkeypatch.setattr(drf_views.httpx, "get", timeout)
    for key, client in (("fastapi", fa), ("drf", drf)):
        response = client.post("/api/v1/products/import-dummyjson") if key == "fastapi" else client.post("/api/v1/products/import-dummyjson", {}, format="json")
        assert response.status_code == 502
    assert len(calls) == 2
