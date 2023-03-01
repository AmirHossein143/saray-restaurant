from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from .models import Food, Categories, Image
# Create your views here.
        # image_for_food = Food.objects.all().values_list("id", "image")
    # ls = []
    # ls2 = []
    # temp = image_for_food[0][0]
    # for i in image_for_food:
    #     b = list(i)
    #     b.append(str(Image.objects.get(pk = b[1]).image1))
    #     if (b[0] == temp):
    #         ls.append(b) 
    #     else:
    #         ls2.append(ls)
    #         ls = []
    #         ls.append(b)
    #         temp = b[0] 
first = True
def index(request):
    Categories1 = Categories.objects.all()
    return render(request, 'saray_menu/index.html', {"categories": Categories1})
def menu(request, category_name1):

    Categories1 = Categories.objects.all()
    our_category = Categories.objects.filter(category_name = category_name1)[0]
    our_food = Food.objects.filter(category = our_category)
    Image1 = Image.objects.all()
    length = [i for i in range(0, our_food.count())]
    # hello
    image_for_food = Food.objects.all().values_list("id", "image")
    ls = []
    for i in image_for_food:
        b = list(i)
        b.append(str(Image.objects.get(pk = b[1]).image1))
        ls.append(b) 
    image_length_d = dict()
    # for j in our_food:
    #     image_length_d[int(j.id)] = [i for i in range(0, Food.objects.get(pk=j.id).image.count())]
    # # first_food = our_food.first().id
    count1 = 0
    count2 = 0
    return render(request, 'saray_menu/menu.html',
                  {"categories": Categories1, "Food": our_food, "Image": Image1, 
                   "class_name": "carouselExampleIndicators", 
                   "images":ls, "image_length":image_length_d, "count1":count1, "count2":count2})