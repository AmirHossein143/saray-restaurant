from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
# Create your views here.
def index(request):
    return render(request, 'saray_menu/index.html')
def menu(request):
    return render(request, 'saray_menu/menu.html')