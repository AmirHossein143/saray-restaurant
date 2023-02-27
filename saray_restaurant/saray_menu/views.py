from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import Food, Categories, Image
# Create your views here.
def index(request):
    Categories1 = Categories.objects.all()
    return render(request, 'saray_menu/index.html', {"categories": Categories1})
def menu(request, category_name1):
    Categories1 = Categories.objects.all()
    our_category = Categories.objects.filter(category_name = category_name1)[0]
    our_food = Food.objects.filter(category = our_category)
    Image1 = Image.objects.all()
    image_for_food = Food.objects.all().values("id", "image")
    
    length = [i for i in range(0, our_food.count())]
    count =0
    return render(request, 'saray_menu/menu.html', {"categories": Categories1, "Food": our_food, "Image": Image1, "length": length, "class_name": "carouselExampleIndicators", "images":image_for_food, "counter":count})