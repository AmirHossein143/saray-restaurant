from django.urls import path
from . import views
urlpatterns = [
    path('', views.index, name='index'),
    path('<str:category_name1>', views.menu, name='menu'),
]