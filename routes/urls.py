from django.urls import path
from .views import RouteView

app_name = "routes"

urlpatterns = [
    path("route/", RouteView.as_view(), name="route"),
]
