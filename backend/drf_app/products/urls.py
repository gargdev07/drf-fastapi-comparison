from django.urls import path
from .views import DummyJSONImportView, HealthView, ProductDetailView, ProductListView, ValidationView

urlpatterns = [
    path("health", HealthView.as_view()),
    path("products", ProductListView.as_view()),
    path("products/import-dummyjson", DummyJSONImportView.as_view()),
    path("products/<int:pk>", ProductDetailView.as_view()),
    path("validation/example", ValidationView.as_view()),
]
