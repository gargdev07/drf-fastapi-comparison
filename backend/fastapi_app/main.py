from contextlib import asynccontextmanager
from math import isfinite
import os
import sqlite3
from pathlib import Path
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

DB_PATH = Path(os.getenv("FASTAPI_DB_PATH", str(Path(__file__).with_name("products.sqlite3"))))


def validate_image_url(value: str | None) -> str | None:
    if value:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("An HTTP or HTTPS URL is required.")
        HttpUrl(value)
    return value


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', price REAL NOT NULL,
            category TEXT NOT NULL, stock INTEGER NOT NULL DEFAULT 0,
            image TEXT NOT NULL DEFAULT '', UNIQUE(title, category))""")
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            db.executemany("INSERT INTO products(title,description,price,category,stock,image) VALUES(?,?,?,?,?,?)", [
                ("Classic cotton tee", "Everyday heavyweight cotton t-shirt", 24.5, "Clothing", 38, "https://dummyjson.com/image/400x300"),
                ("Studio headphones", "Over-ear wireless headphones", 89.0, "Electronics", 12, "https://dummyjson.com/image/400x300"),
                ("Ceramic pour-over set", "Hand-finished coffee dripper and cup", 42.0, "Home", 21, "https://dummyjson.com/image/400x300"),
            ])


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Product API · FastAPI", version="1.0.0", description="Product CRUD comparison API", lifespan=lifespan)
_cors_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=["*"] if "*" in _cors_origins else _cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    price: float = Field(ge=0.01, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=80)
    stock: int = Field(default=0, ge=0)
    image: str = Field(default="", max_length=500)

    @field_validator("title", "description", "category", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("price", mode="before")
    @classmethod
    def reject_boolean_price(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("A number is required.")
        return value

    @field_validator("stock", mode="before")
    @classmethod
    def reject_boolean_stock(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("An integer is required.")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("An integer is required.")
        return value

    @field_validator("image")
    @classmethod
    def image_is_url_or_empty(cls, value: str) -> str:
        return validate_image_url(value)


class ProductPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    price: float | None = Field(default=None, ge=0.01, allow_inf_nan=False)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    stock: int | None = Field(default=None, ge=0)
    image: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_a_supplied_field(self):
        if not self.model_fields_set:
            raise ValueError("PATCH must include at least one product field.")
        return self

    @field_validator("title", "description", "category", mode="before")
    @classmethod
    def trim_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("title", "description", "price", "category", "stock", "image", mode="before")
    @classmethod
    def reject_null_when_supplied(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("This field may not be null.")
        return value

    @field_validator("price", mode="before")
    @classmethod
    def reject_boolean_price(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("A number is required.")
        return value

    @field_validator("stock", mode="before")
    @classmethod
    def reject_boolean_stock(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("An integer is required.")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("An integer is required.")
        return value

    @field_validator("image")
    @classmethod
    def image_is_url_or_empty(cls, value: str | None) -> str | None:
        return validate_image_url(value)

def _normalize_dummyjson(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        raise ValueError("DummyJSON returned an invalid products response.")
    normalized = []
    for index, item in enumerate(payload["products"]):
        if not isinstance(item, dict):
            raise ValueError(f"DummyJSON product {index} is not an object.")
        title, category = item.get("title"), item.get("category")
        price, stock = item.get("price"), item.get("stock", 0)
        description, image = item.get("description", ""), item.get("thumbnail", "")
        if not isinstance(title, str) or not title.strip() or not isinstance(category, str) or not category.strip():
            raise ValueError(f"DummyJSON product {index} is missing a title or category.")
        if isinstance(price, bool) or not isinstance(price, (float, int)) or not isfinite(price) or price < 0.01:
            raise ValueError(f"DummyJSON product {index} has an invalid price.")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            raise ValueError(f"DummyJSON product {index} has invalid stock.")
        if not isinstance(description, str) or not isinstance(image, str):
            raise ValueError(f"DummyJSON product {index} has invalid text fields.")
        validate_image_url(image)
        normalized.append({
            "title": title.strip()[:120], "description": description.strip()[:500],
            "price": float(price), "category": category.strip()[:80], "stock": stock,
            "image": image,
        })
    return normalized


_dummyjson_cache: list[dict[str, Any]] = []
_dummyjson_cache_until = 0.0
_dummyjson_cache_lock = threading.Lock()
DUMMYJSON_CACHE_SECONDS = 300


def fetch_dummyjson_products() -> tuple[list[dict[str, Any]], bool]:
    global _dummyjson_cache, _dummyjson_cache_until
    with _dummyjson_cache_lock:
        if _dummyjson_cache and time.monotonic() < _dummyjson_cache_until:
            return [item.copy() for item in _dummyjson_cache], True
        response = httpx.get(
            "https://dummyjson.com/products?limit=30&select=title,description,price,category,stock,thumbnail",
            timeout=httpx.Timeout(8.0, connect=3.0),
        )
        response.raise_for_status()
        products = _normalize_dummyjson(response.json())
        _dummyjson_cache = products
        _dummyjson_cache_until = time.monotonic() + DUMMYJSON_CACHE_SECONDS
        return [item.copy() for item in products], False


class ValidationExample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=120)
    price: float = Field(ge=0.01, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=80)


def serialize(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    return item


@app.get("/api/v1/health")
def health():
    with connect() as db:
        db.execute("SELECT 1")
    return {"data": {"status": "ok", "framework": "FastAPI", "database": "sqlite"}}


@app.get("/api/v1/products")
def list_products(q: str = "", limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    with connect() as db:
        pattern = f"%{q}%"
        total = db.execute("SELECT COUNT(*) FROM products WHERE title LIKE ? OR category LIKE ?", (pattern, pattern)).fetchone()[0]
        rows = db.execute("SELECT * FROM products WHERE title LIKE ? OR category LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?", (pattern, pattern, limit, offset)).fetchall()
    return {"data": [serialize(r) for r in rows], "meta": {"total": total, "limit": limit, "offset": offset}}


@app.post("/api/v1/products", status_code=201)
def create_product(payload: ProductInput):
    data = payload.model_dump()
    data["image"] = str(data["image"] or "")
    with connect() as db:
        cursor = db.execute("INSERT INTO products(title,description,price,category,stock,image) VALUES(:title,:description,:price,:category,:stock,:image)", data)
        row = db.execute("SELECT * FROM products WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"data": serialize(row)}


def get_product(product_id: int) -> dict[str, Any]:
    with connect() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize(row)


@app.get("/api/v1/products/{product_id:int}")
def retrieve_product(product_id: int):
    return {"data": get_product(product_id)}


@app.put("/api/v1/products/{product_id:int}")
def replace_product(product_id: int, payload: ProductInput):
    get_product(product_id)
    data = payload.model_dump()
    data["image"] = str(data["image"] or "")
    with connect() as db:
        db.execute("UPDATE products SET title=:title,description=:description,price=:price,category=:category,stock=:stock,image=:image WHERE id=:id", {**data, "id": product_id})
    return {"data": get_product(product_id)}


@app.patch("/api/v1/products/{product_id:int}")
def update_product(product_id: int, payload: ProductPatch):
    current = get_product(product_id)
    data = {**current, **payload.model_dump(exclude_unset=True)}
    data["image"] = str(data["image"] or "")
    with connect() as db:
        db.execute("UPDATE products SET title=:title,description=:description,price=:price,category=:category,stock=:stock,image=:image WHERE id=:id", {**data, "id": product_id})
    return {"data": get_product(product_id)}


@app.delete("/api/v1/products/{product_id:int}")
def delete_product(product_id: int):
    get_product(product_id)
    with connect() as db:
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
    return {"data": {"deleted": True, "id": product_id}}


@app.post("/api/v1/validation/example")
def validate_example(payload: ValidationExample):
    return {"data": {"valid": True, "validated": payload.model_dump()}}


@app.post("/api/v1/products/import-dummyjson")
def import_dummyjson():
    try:
        products, cache_hit = fetch_dummyjson_products()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"DummyJSON import failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DummyJSON import failed: invalid upstream response ({exc})") from exc
    created = 0
    with connect() as db:
        for item in products:
            cursor = db.execute("""INSERT INTO products(title,description,price,category,stock,image) VALUES(?,?,?,?,?,?)
                ON CONFLICT(title,category) DO NOTHING""", (item["title"], item["description"], item["price"], item["category"], item["stock"], item["image"]))
            created += max(cursor.rowcount, 0)
    return {"data": {"fetched": len(products), "created": created, "skipped": len(products) - created,
                     "existing": len(products) - created, "cache_hit": cache_hit, "source": "DummyJSON"}}
