import httpx
from math import isfinite
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit
from django.db.models import Q
from django.db import connection
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Product
from .serializers import ImportResponseSerializer, ProductListResponseSerializer, ProductResponseSerializer, ProductSerializer, ValidationExampleSerializer

_upstream_cache = []
_upstream_cache_until = 0.0
_upstream_lock = Lock()

def _fetch_dummyjson():
    global _upstream_cache, _upstream_cache_until
    with _upstream_lock:
        if _upstream_cache and monotonic() < _upstream_cache_until:
            return [item.copy() for item in _upstream_cache], True
        response = httpx.get("https://dummyjson.com/products?limit=30&select=title,description,price,category,stock,thumbnail", timeout=httpx.Timeout(8.0, connect=3.0))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            raise ValueError("DummyJSON returned an invalid products response")
        items = []
        for i, source in enumerate(payload["products"]):
            if not isinstance(source, dict):
                raise ValueError(f"DummyJSON product {i} is not an object")
            title, category, description, image = (source.get("title"), source.get("category"), source.get("description", ""), source.get("thumbnail", ""))
            price, stock = source.get("price"), source.get("stock", 0)
            if not isinstance(title, str) or not title.strip() or not isinstance(category, str) or not category.strip():
                raise ValueError(f"DummyJSON product {i} is missing a title or category")
            if isinstance(price, bool) or not isinstance(price, (float, int)) or not isfinite(price) or price < 0.01:
                raise ValueError(f"DummyJSON product {i} has an invalid price")
            if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0 or not isinstance(description, str) or not isinstance(image, str):
                raise ValueError(f"DummyJSON product {i} has invalid fields")
            if image:
                parsed = urlsplit(image)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError(f"DummyJSON product {i} has an invalid image URL")
            items.append({"title": title.strip()[:120], "description": description.strip()[:500], "price": price, "category": category.strip()[:80], "stock": stock, "image": image})
        _upstream_cache, _upstream_cache_until = items, monotonic() + 300
        return [item.copy() for item in items], False

class HealthView(APIView):
    @extend_schema(responses={200: dict})
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"data": {"status": "ok", "framework": "Django REST Framework", "database": "sqlite"}})

class ProductListView(APIView):
    serializer_class = ProductSerializer

    @extend_schema(operation_id="listProducts", parameters=[OpenApiParameter("q", str), OpenApiParameter("limit", int), OpenApiParameter("offset", int)], responses=ProductListResponseSerializer)
    def get(self, request):
        query = request.query_params.get("q", "")
        try:
            limit = min(max(int(request.query_params.get("limit", 20)), 1), 100)
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            return Response({"detail": "limit and offset must be integers"}, status=400)
        products = Product.objects.filter(Q(title__icontains=query) | Q(category__icontains=query)).order_by("-id")
        total = products.count()
        data = ProductSerializer(products[offset:offset + limit], many=True).data
        return Response({"data": data, "meta": {"total": total, "limit": limit, "offset": offset}})

    @extend_schema(operation_id="createProduct", request=ProductSerializer, responses={201: ProductResponseSerializer, 422: dict})
    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"data": ProductSerializer(serializer.instance).data}, status=status.HTTP_201_CREATED)

class ProductDetailView(APIView):
    serializer_class = ProductSerializer

    def get_object(self, pk):
        try:
            return Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return None

    @extend_schema(operation_id="retrieveProduct", responses={200: ProductResponseSerializer, 404: dict})
    def get(self, request, pk):
        product = self.get_object(pk)
        if product is None:
            return Response({"detail": "Product not found"}, status=404)
        return Response({"data": ProductSerializer(product).data})

    @extend_schema(operation_id="replaceProduct", request=ProductSerializer, responses={200: ProductResponseSerializer, 422: dict})
    def put(self, request, pk):
        product = self.get_object(pk)
        if product is None:
            return Response({"detail": "Product not found"}, status=404)
        serializer = ProductSerializer(product, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"data": ProductSerializer(serializer.instance).data})

    @extend_schema(operation_id="updateProduct", request=ProductSerializer, responses={200: ProductResponseSerializer, 422: dict})
    def patch(self, request, pk):
        product = self.get_object(pk)
        if product is None:
            return Response({"detail": "Product not found"}, status=404)
        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"data": ProductSerializer(serializer.instance).data})

    @extend_schema(operation_id="deleteProduct", responses={200: dict, 404: dict})
    def delete(self, request, pk):
        product = self.get_object(pk)
        if product is None:
            return Response({"detail": "Product not found"}, status=404)
        product.delete()
        return Response({"data": {"deleted": True, "id": pk}})

class ValidationView(APIView):
    @extend_schema(request=ValidationExampleSerializer, responses={200: dict})
    def post(self, request):
        serializer = ValidationExampleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"data": {"valid": True, "validated": serializer.validated_data}})

class DummyJSONImportView(APIView):
    serializer_class = ImportResponseSerializer

    @extend_schema(operation_id="importDummyJSONProducts", request=None, responses={200: ImportResponseSerializer, 502: dict})
    def post(self, request):
        try:
            items, cache_hit = _fetch_dummyjson()
        except Exception as exc:
            return Response({"detail": f"DummyJSON import failed: {exc}"}, status=502)
        created = 0
        for item in items:
            _, was_created = Product.objects.get_or_create(title=item["title"], category=item["category"], defaults={
                "description": item["description"], "price": item["price"], "stock": item["stock"], "image": item["image"]
            })
            created += int(was_created)
        return Response({"data": {"fetched": len(items), "created": created, "skipped": len(items) - created,
                                   "existing": len(items) - created, "cache_hit": cache_hit, "source": "DummyJSON"}})
