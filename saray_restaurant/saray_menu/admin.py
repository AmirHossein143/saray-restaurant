from django.contrib import admin
from .models import Food, Categories, Image
# Register your models here.
class Category_Model(admin.ModelAdmin):
    list_display = ["id", "category_name"]
# class Food_model(admin.ModelAdmin):
#     list_display = ["id", "food_name", "price", "image", "category", "description"]
class Image_model(admin.ModelAdmin):
    list_display = ["id", "image1"]
class Food_admin(admin.ModelAdmin):
    filter_horizontal = ("image",)
    list_display = ["id", "food_name", "price", "category", "description"]
admin.site.register(Food, Food_admin)
admin.site.register(Categories, Category_Model)
admin.site.register(Image, Image_model)
