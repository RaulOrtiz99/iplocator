from django.contrib import admin
from django.urls import path
from geoip import views  # Importa las vistas de la aplicación geoip

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.upload_csv, name='upload_csv'),  # Ruta para la página principal
    path('get_processing_status/', views.get_processing_status, name='get_processing_status'),
]