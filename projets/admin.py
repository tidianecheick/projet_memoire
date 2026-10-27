import json

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.templatetags.static import static
from django.utils import timezone
from django.utils.safestring import mark_safe
from leaflet.admin import LeafletGeoAdmin

from .models import Forage, Installation, Route, Solaire, TrackingRoute

CHAMPS_COMMUNS = ("nom", "localite", "type", "status", "beneficiaire", "description", "photo")


class ProjetAdmin(LeafletGeoAdmin):
    list_display = ("nom", "localite", "type", "status")
    list_filter = ("status", "localite")
    search_fields = ("nom", "localite", "beneficiaire")


class ProjetPonctuelAdmin(ProjetAdmin):
    list_display = ("nom", "localite", "type", "status", "longitude", "latitude")


# ---------- Routes : saisie du tracking dans la fiche ----------

def _lon(label):
    return forms.FloatField(required=False, label=label, min_value=-180, max_value=180)


def _lat(label):
    return forms.FloatField(required=False, label=label, min_value=-90, max_value=90)


class RouteForm(forms.ModelForm):
    # Champs de saisie du nouveau relevé (non enregistrés sur la route elle-même)
    date_releve = forms.DateField(
        required=False, initial=timezone.localdate,
        label="Date du relevé", widget=AdminDateWidget,
    )
    t1_longitude = _lon("T1 - longitude")
    t1_latitude = _lat("T1 - latitude")
    t2_longitude = _lon("T2 - longitude")
    t2_latitude = _lat("T2 - latitude")
    t3_longitude = _lon("T3 - longitude")
    t3_latitude = _lat("T3 - latitude")
    t4_longitude = _lon("T4 - longitude")
    t4_latitude = _lat("T4 - latitude")

    class Meta:
        model = Route
        fields = "__all__"

    def clean(self):
        data = super().clean()
        points = []
        for i in range(1, 5):
            lon = data.get(f"t{i}_longitude")
            lat = data.get(f"t{i}_latitude")
            if (lon is None) != (lat is None):
                raise ValidationError(
                    f"T{i} : renseignez la longitude et la latitude, ou aucune des deux."
                )
            if lon is not None:
                points.append((lon, lat))
        if points and len(points) < 2:
            raise ValidationError("Un relevé nécessite au moins 2 points (T1 et T2).")
        self.points = points
        return data


class HistoriqueTrackingInline(admin.TabularInline):
    """Historique des relevés : lecture seule, suppression possible."""
    model = TrackingRoute
    extra = 0
    can_delete = True
    fields = ("date_releve", "points", "longueur")
    readonly_fields = ("date_releve", "points", "longueur")
    verbose_name_plural = "Historique des relevés de tracking"

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Points")
    def points(self, obj):
        p = obj.PREFIXE
        pts = []
        for i in range(1, 5):
            lon = getattr(obj, f"{p}{i}_longitude")
            lat = getattr(obj, f"{p}{i}_latitude")
            if lon is not None:
                pts.append(f"T{i} ({lon}, {lat})")
        return " → ".join(pts) or "tracé dessiné"


# Carte Leaflet du tracé : un tronçon par relevé, le dernier relevé en orange
GABARIT_CARTE = """
<link rel="stylesheet" href="__CSS__">
<div id="carte-trace" style="height:420px; width:100%; max-width:760px;"></div>
<p style="margin-top:6px;">
  Bleu : relevés précédents &mdash; Orange : dernier relevé.
  Cliquez sur un tronçon pour voir sa date et sa longueur.
</p>
<script src="__JS__"></script>
<script>
(function () {
  var carte = L.map("carte-trace");
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap"
  }).addTo(carte);

  var releves = __RELEVES__;
  var groupe = L.featureGroup().addTo(carte);
  releves.forEach(function (r, i) {
    var dernier = (i === releves.length - 1);
    L.geoJSON(r.geom, {style: {color: dernier ? "#d9480f" : "#1c7ed6", weight: 5}})
      .bindPopup("Relevé du " + r.date + " : " + r.km + " km")
      .addTo(groupe);
  });
  carte.fitBounds(groupe.getBounds(), {padding: [30, 30], maxZoom: 16});
})();
</script>
"""


class RouteAdmin(ProjetAdmin):
    form = RouteForm
    inlines = [HistoriqueTrackingInline]
    list_display = (
        "nom", "localite", "status",
        "longueur_prevue", "longueur_realisee", "taux_avancement",
    )
    readonly_fields = ("longueur_realisee", "taux_avancement", "carte_trace")
    fieldsets = (
        (None, {"fields": CHAMPS_COMMUNS}),
        ("Dimensions", {"fields": ("longueur_prevue", "largeur")}),
        ("Nouveau relevé de tracking (4 points maximum)", {"fields": (
            "date_releve",
            ("t1_longitude", "t1_latitude"),
            ("t2_longitude", "t2_latitude"),
            ("t3_longitude", "t3_latitude"),
            ("t4_longitude", "t4_latitude"),
        )}),
        ("Avancement (calculé)", {"fields": (
            "longueur_realisee", "taux_avancement", "carte_trace",
        )}),
    )

    @admin.display(description="Carte du tracé")
    def carte_trace(self, obj):
        if not obj or not obj.pk:
            return "La carte s'affichera après l'enregistrement du premier relevé."

        releves = [
            {
                "geom": json.loads(t.geometrie.geojson),
                "date": t.date_releve.strftime("%d/%m/%Y"),
                "km": t.longueur,
            }
            for t in obj.trackings.order_by("date_releve", "id")
            if t.geometrie
        ]
        if not releves:
            return "Aucun relevé enregistré pour le moment."

        html = (
            GABARIT_CARTE
            .replace("__CSS__", static("leaflet/leaflet.css"))
            .replace("__JS__", static("leaflet/leaflet.js"))
            .replace("__RELEVES__", json.dumps(releves))
        )
        return mark_safe(html)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        points = getattr(form, "points", [])
        if not points:
            return

        # Avertissement si le nouveau relevé ne prolonge pas le tracé précédent
        precedent = obj.trackings.order_by("-date_releve", "-id").first()
        if precedent and precedent.geometrie:
            fin = Point(precedent.geometrie.coords[-1], srid=4326)
            debut = Point(points[0], srid=4326)
            ecart = debut.transform(32630, clone=True).distance(
                fin.transform(32630, clone=True)
            )
            if ecart > 100:
                messages.warning(
                    request,
                    f"Le premier point du nouveau relevé est à {ecart:.0f} m de la fin "
                    "du tracé précédent. Vérifiez la continuité.",
                )

        releve = TrackingRoute(
            route=obj,
            date_releve=form.cleaned_data.get("date_releve") or timezone.localdate(),
        )
        for i, (lon, lat) in enumerate(points, start=1):
            setattr(releve, f"t{i}_longitude", lon)
            setattr(releve, f"t{i}_latitude", lat)
        releve.save()   # calcule la géométrie, la longueur, puis met la route à jour


# ---------- Installations ----------

class InstallationAdmin(ProjetAdmin):
    fieldsets = (
        (None, {"fields": CHAMPS_COMMUNS}),
        ("Emprise (4 sommets)", {"fields": (
            ("l1_longitude", "l1_latitude"),
            ("l2_longitude", "l2_latitude"),
            ("l3_longitude", "l3_latitude"),
            ("l4_longitude", "l4_latitude"),
        )}),
        ("Géométrie et superficie", {"fields": ("geometrie", "superficie")}),
    )


admin.site.register(Forage, ProjetPonctuelAdmin)
admin.site.register(Solaire, ProjetPonctuelAdmin)
admin.site.register(Route, RouteAdmin)
admin.site.register(Installation, InstallationAdmin)