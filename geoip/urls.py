from django.urls import path
from . import views

urlpatterns = [
    path('upload_csv/', views.upload_csv, name='upload_csv'),
    path('get_processing_status/', views.get_processing_status, name='get_processing_status'),
]