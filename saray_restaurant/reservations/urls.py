from django.urls import path

from . import views

app_name = 'reservations'

urlpatterns = [
    path('', views.create, name='create'),
    path('done/<str:code>/', views.done, name='done'),
]
