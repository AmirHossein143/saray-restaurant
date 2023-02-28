from django.db import models

# Create your models here.
class Categories(models.Model):
    category_name = models.CharField(max_length=50)
    def __str__(self):
        return f"category: {self.category_name}"
class Image(models.Model):
    image1 = models.ImageField(upload_to = "saray_menu\static\images", blank = True)
    def __str__(self):
        return f"{self.image1.name}"
class Food(models.Model):
    food_name = models.CharField(max_length = 40)
    price = models.DecimalField(max_digits = 10, decimal_places = 2)
    image = models.ManyToManyField(Image, blank=True, related_name="image_field")
    category = models.ForeignKey(Categories, on_delete = models.CASCADE, related_name = "category_relate")
    description = models.TextField(max_length = 200, blank = True)

    def __str__(self):
        p = ""
        for i in self.image.all():
            p += f"{str(i)}, "
        p = p[0:-2]
        return f"food_name: {self.food_name},  price: {self.price},  image: {p}, {self.category},  description: {self.description} "
