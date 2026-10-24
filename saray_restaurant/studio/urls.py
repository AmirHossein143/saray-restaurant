from django.urls import path

from . import views

app_name = 'studio'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/tables/', views.tables, name='tables'),
    path('api/<str:key>/rows/', views.rows, name='rows'),
    path('api/<str:key>/rows/<int:pk>/', views.row, name='row'),
    path('api/<str:key>/rows/<int:pk>/delete-preview/', views.delete_preview, name='delete_preview'),
    path('api/<str:key>/bulk-delete/', views.bulk_delete, name='bulk_delete'),
    path('api/<str:key>/options/', views.options, name='options'),
    path('api/<str:key>/export.csv', views.export_csv, name='export_csv'),
]
