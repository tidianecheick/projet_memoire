from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ForageViewSet,
    InstallationViewSet,
    RouteViewSet,
    SolaireViewSet,
    carte_projets,
)

router = DefaultRouter()
router.register("forages", ForageViewSet, basename="forage")
router.register("solaires", SolaireViewSet, basename="solaire")
router.register("routes", RouteViewSet, basename="route")
router.register("installations", InstallationViewSet, basename="installation")

urlpatterns = [
    path("carte/", carte_projets, name="carte-projets"),
    path("", include(router.urls)),
]