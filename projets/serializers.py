from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Forage, Installation, Route, Solaire, TrackingRoute

CHAMPS_COMMUNS = (
    "id", "nom", "localite", "type", "status", "photo",
    "beneficiaire", "description", "date_creation",
)
CHAMPS_TRACKING = tuple(
    f"t{i}_{axe}" for i in range(1, 5) for axe in ("longitude", "latitude")
)
CHAMPS_SOMMETS = tuple(
    f"l{i}_{axe}" for i in range(1, 5) for axe in ("longitude", "latitude")
)


class ForageGeoSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Forage
        geo_field = "geometrie"
        fields = CHAMPS_COMMUNS + ("longitude", "latitude", "geometrie")


class SolaireGeoSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Solaire
        geo_field = "geometrie"
        fields = CHAMPS_COMMUNS + ("longitude", "latitude", "geometrie")


class InstallationGeoSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Installation
        geo_field = "geometrie"
        fields = CHAMPS_COMMUNS + CHAMPS_SOMMETS + ("superficie", "geometrie")


class TrackingRouteSerializer(serializers.ModelSerializer):
    """Un relevé de tracking : date, points T1..T4, longueur et tronçon (GeoJSON)."""

    geometrie = GeometryField(read_only=True)

    class Meta:
        model = TrackingRoute
        fields = ("id", "date_releve", "longueur", "commentaire", "geometrie") + CHAMPS_TRACKING


class RouteGeoSerializer(GeoFeatureModelSerializer):
    """Liste des routes : tracé cumulé et avancement."""

    class Meta:
        model = Route
        geo_field = "geometrie"
        fields = CHAMPS_COMMUNS + (
            "largeur", "longueur_prevue", "longueur_realisee",
            "taux_avancement", "geometrie",
        )


class RouteDetailGeoSerializer(RouteGeoSerializer):
    """Fiche d'une route : ajoute l'historique des relevés (progression des travaux)."""

    trackings = TrackingRouteSerializer(many=True, read_only=True)

    class Meta(RouteGeoSerializer.Meta):
        fields = RouteGeoSerializer.Meta.fields + ("trackings",)
