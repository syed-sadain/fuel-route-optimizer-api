from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def home(request):
    return JsonResponse({
        "status": "success",
        "message": "Fuel Route Optimization API is running"
    })

urlpatterns = [
    path('', home),
    
    path('api/', include('routes.urls')),
]