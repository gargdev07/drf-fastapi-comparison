from django.db import migrations

def seed_products(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Product.objects.bulk_create([
        Product(title="Classic cotton tee", description="Everyday heavyweight cotton t-shirt", price=24.5, category="Clothing", stock=38, image="https://dummyjson.com/image/400x300"),
        Product(title="Studio headphones", description="Over-ear wireless headphones", price=89.0, category="Electronics", stock=12, image="https://dummyjson.com/image/400x300"),
        Product(title="Ceramic pour-over set", description="Hand-finished coffee dripper and cup", price=42.0, category="Home", stock=21, image="https://dummyjson.com/image/400x300"),
    ])

class Migration(migrations.Migration):
    dependencies = [("products", "0001_initial")]
    operations = [migrations.RunPython(seed_products, migrations.RunPython.noop)]
