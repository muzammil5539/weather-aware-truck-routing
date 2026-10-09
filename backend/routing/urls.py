from django.urls import include, path
from rest_framework.routers import DefaultRouter

from routing import views

router = DefaultRouter()
router.register("trips", views.TripViewSet, basename="trip")

urlpatterns = [
    path("", include(router.urls)),
    path("geocode/", views.geocode_search, name="geocode"),
    path("risk-reference/", views.risk_reference, name="risk-reference"),
    path("health/", views.health, name="health"),
]
