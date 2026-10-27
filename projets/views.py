from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework_gis.filters import InBBoxFilter
from django.shortcuts import render

from .models import Forage, Installation, Route, Solaire
from .serializers import (
    ForageGeoSerializer,
    InstallationGeoSerializer,
    RouteDetailGeoSerializer,
    RouteGeoSerializer,
    SolaireGeoSerializer,
)


class ProjetViewSet(viewsets.ReadOnlyModelViewSet):
    """Liste + fiche détaillée, avec recherche, filtres et filtre par emprise de carte."""

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter, InBBoxFilter]
    filterset_fields = {
        "status": ["exact"],
        "localite": ["exact", "icontains"],
        "type": ["exact", "icontains"],
    }
    search_fields = ["nom", "localite", "beneficiaire"]
    ordering_fields = ["nom", "date_creation"]
    bbox_filter_field = "geometrie"
    bbox_filter_include_overlapping = True


class ForageViewSet(ProjetViewSet):
    queryset = Forage.objects.all()
    serializer_class = ForageGeoSerializer


class SolaireViewSet(ProjetViewSet):
    queryset = Solaire.objects.all()
    serializer_class = SolaireGeoSerializer


class InstallationViewSet(ProjetViewSet):
    queryset = Installation.objects.all()
    serializer_class = InstallationGeoSerializer


class RouteViewSet(ProjetViewSet):
    queryset = Route.objects.all()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "retrieve":
            queryset = queryset.prefetch_related("trackings")
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RouteDetailGeoSerializer
        return RouteGeoSerializer


def carte_projets(request):
    return render(request, 'projets/carte.html')