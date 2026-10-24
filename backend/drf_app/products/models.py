from django.db import models

class Product(models.Model):
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    price = models.FloatField()
    category = models.CharField(max_length=80)
    stock = models.IntegerField(default=0)
    image = models.URLField(blank=True, max_length=500)

    def __str__(self):
        return self.title
