from rest_framework import serializers
from math import isfinite
from urllib.parse import urlsplit
from .models import Product

class StrictCharField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            raise serializers.ValidationError("A string is required.")
        return super().to_internal_value(data)

class StrictFloatField(serializers.FloatField):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            raise serializers.ValidationError("A number is required.")
        return super().to_internal_value(data)

class StrictIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            raise serializers.ValidationError("An integer is required.")
        return super().to_internal_value(data)

class ProductSerializer(serializers.ModelSerializer):
    price = StrictFloatField(min_value=0.01)
    stock = StrictIntegerField(min_value=0, required=False)
    title = StrictCharField(min_length=2, max_length=120, trim_whitespace=True)
    category = StrictCharField(min_length=1, max_length=80, trim_whitespace=True)
    description = StrictCharField(max_length=500, required=False, allow_blank=True)
    image = serializers.URLField(required=False, allow_blank=True, max_length=500)

    class Meta:
        model = Product
        fields = ("id", "title", "description", "price", "category", "stock", "image")
        read_only_fields = ("id",)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Expected an object."]})
        unknown = (set(data) - set(self.fields)) | (set(data) & {"id"})
        if unknown:
            raise serializers.ValidationError({key: ["Unexpected field."] for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate_price(self, value):
        if not isfinite(value):
            raise serializers.ValidationError("A finite number is required.")
        return value

    def validate_image(self, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise serializers.ValidationError("Enter a valid HTTP or HTTPS URL.")
        return value

    def validate(self, attrs):
        if self.partial and not self.initial_data:
            raise serializers.ValidationError({"non_field_errors": ["PATCH must include at least one product field."]})
        return attrs

class ValidationExampleSerializer(ProductSerializer):
    class Meta:
        model = Product
        fields = ("title", "price", "category")

class ProductResponseSerializer(serializers.Serializer):
    data = ProductSerializer()

class ProductListResponseSerializer(serializers.Serializer):
    data = ProductSerializer(many=True)
    meta = serializers.DictField()

class ImportResponseSerializer(serializers.Serializer):
    data = serializers.DictField()
