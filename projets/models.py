from django.contrib.gis.db import models
from django.contrib.gis.geos import LineString, MultiLineString, Point, Polygon
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone


# ---------------------------------------------------------------------------
# Fonctions utilitaires pour les champs de coordonnées
# ---------------------------------------------------------------------------

def champ_longitude(aide=""):
    return models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        help_text=aide or "Degrés décimaux (WGS 84)",
    )


def champ_latitude(aide=""):
    return models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        help_text=aide or "Degrés décimaux (WGS 84)",
    )


# ---------------------------------------------------------------------------
# Modèle de base commun à tous les projets
# ---------------------------------------------------------------------------

class ProjetBase(models.Model):
    """Champs communs à tous les types de projets (modèle abstrait)."""

    class Statut(models.TextChoices):
        PLANIFIE = "planifie", "Planifié"
        EN_COURS = "en_cours", "En cours"
        SUSPENDU = "suspendu", "Suspendu"
        TERMINE = "termine", "Terminé"

    nom = models.CharField(max_length=200)
    localite = models.CharField(max_length=200)
    type = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.PLANIFIE
    )
    photo = models.ImageField(upload_to="projets/", blank=True, null=True)
    beneficiaire = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True          # aucune table pour ProjetBase
        ordering = ["nom"]

    def __str__(self):
        return f"{self.nom} ({self.localite})"


# ---------------------------------------------------------------------------
# Forages et électrification solaire : projets ponctuels
# ---------------------------------------------------------------------------

class ProjetPonctuel(ProjetBase):
    """Projet localisé par un point : longitude/latitude + géométrie synchronisées."""

    longitude = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
        help_text="Degrés décimaux (WGS 84), ex. -1.5197",
    )
    latitude = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
        help_text="Degrés décimaux (WGS 84), ex. 12.3714",
    )
    geometrie = models.PointField(
        srid=4326, null=True, blank=True,
        help_text="Renseignée automatiquement à partir de la longitude et de la latitude, "
                  "ou en cliquant sur la carte.",
    )

    class Meta(ProjetBase.Meta):
        abstract = True

    # Coordonnées telles qu'elles étaient en base au chargement de l'objet
    _orig_lonlat = (None, None)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._orig_lonlat = (
            instance.__dict__.get("longitude"),
            instance.__dict__.get("latitude"),
        )
        return instance

    def _synchroniser(self):
        lon, lat, geom = self.longitude, self.latitude, self.geometrie

        if (lon is None) != (lat is None):
            raise ValidationError(
                "Renseignez à la fois la longitude et la latitude, ou aucune des deux."
            )

        lonlat_modifie = (lon, lat) != self._orig_lonlat

        if lon is not None and (lonlat_modifie or geom is None):
            # longitude/latitude font foi : on reconstruit la géométrie
            self.geometrie = Point(lon, lat, srid=4326)
        elif geom is not None:
            # la géométrie (carte) fait foi : on recalcule longitude/latitude
            self.longitude = round(geom.x, 6)
            self.latitude = round(geom.y, 6)
        else:
            raise ValidationError(
                "Indiquez la longitude et la latitude, ou placez le point sur la carte."
            )

    def clean(self):
        super().clean()
        self._synchroniser()

    def save(self, *args, **kwargs):
        self._synchroniser()
        super().save(*args, **kwargs)
        self._orig_lonlat = (self.longitude, self.latitude)


class Forage(ProjetPonctuel):
    pass


class Solaire(ProjetPonctuel):
    class Meta(ProjetPonctuel.Meta):
        verbose_name = "électrification solaire"
        verbose_name_plural = "électrifications solaires"


# ---------------------------------------------------------------------------
# Mécanisme commun : 4 couples longitude/latitude <-> géométrie
# ---------------------------------------------------------------------------

class SommetsMixin(models.Model):
    """Synchronise 4 couples longitude/latitude avec la géométrie (L1..L4 ou T1..T4)."""

    PREFIXE = ""   # "l" pour L1..L4, "t" pour T1..T4
    _orig_sommets = ((None, None),) * 4

    class Meta:
        abstract = True

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        p = cls.PREFIXE
        instance._orig_sommets = tuple(
            (instance.__dict__.get(f"{p}{i}_longitude"),
             instance.__dict__.get(f"{p}{i}_latitude"))
            for i in range(1, 5)
        )
        return instance

    def _lire_sommets(self):
        p = self.PREFIXE
        return tuple(
            (getattr(self, f"{p}{i}_longitude"), getattr(self, f"{p}{i}_latitude"))
            for i in range(1, 5)
        )

    def _ecrire_sommets(self, coords):
        p = self.PREFIXE
        for i in range(1, 5):
            if i <= len(coords):
                lon, lat = round(coords[i - 1][0], 6), round(coords[i - 1][1], 6)
            else:
                lon = lat = None
            setattr(self, f"{p}{i}_longitude", lon)
            setattr(self, f"{p}{i}_latitude", lat)

    def _sommets_saisis(self):
        sommets = self._lire_sommets()
        for i, (lon, lat) in enumerate(sommets, start=1):
            if (lon is None) != (lat is None):
                raise ValidationError(
                    f"{self.PREFIXE.upper()}{i} : renseignez la longitude et la latitude, "
                    "ou aucune des deux."
                )
        remplis = [s for s in sommets if s != (None, None)]
        return remplis, sommets != self._orig_sommets

    def _synchroniser(self):
        raise NotImplementedError

    def clean(self):
        super().clean()
        self._synchroniser()

    def save(self, *args, **kwargs):
        self._synchroniser()
        super().save(*args, **kwargs)
        self._orig_sommets = self._lire_sommets()


# ---------------------------------------------------------------------------
# Routes et relevés de tracking (cumulatifs)
# ---------------------------------------------------------------------------

class Route(ProjetBase):
    # Cumul de tous les relevés : calculé, non saisi
    geometrie = models.MultiLineStringField(
        srid=4326, null=True, blank=True, editable=False,
        help_text="Cumul de tous les relevés de tracking.",
    )
    longueur_prevue = models.FloatField(null=True, blank=True, help_text="en km")
    longueur_realisee = models.FloatField(
        default=0, editable=False, help_text="en km, cumul des relevés"
    )
    taux_avancement = models.FloatField(
        null=True, blank=True, editable=False, help_text="en %"
    )
    largeur = models.FloatField(null=True, blank=True, help_text="en mètres")

    def recalculer(self):
        """Recalcule le tracé cumulé, la longueur réalisée et le taux d'avancement."""
        releves = list(
            self.trackings.exclude(geometrie__isnull=True).order_by("date_releve", "id")
        )
        if releves:
            fusion = MultiLineString(*[r.geometrie for r in releves], srid=4326).merged
            if fusion.geom_type == "LineString":
                fusion = MultiLineString(fusion, srid=4326)
            fusion.srid = 4326
            realisee = round(sum(r.longueur or 0 for r in releves), 3)
        else:
            fusion, realisee = None, 0

        taux = None
        if self.longueur_prevue:
            taux = min(100, round(100 * realisee / self.longueur_prevue, 1))

        type(self).objects.filter(pk=self.pk).update(
            geometrie=fusion, longueur_realisee=realisee, taux_avancement=taux
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.recalculer()


class TrackingRoute(SommetsMixin):
    """Un relevé de tracking (jusqu'à 4 points) : un tronçon qui s'ajoute à la route."""

    PREFIXE = "t"

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="trackings")
    date_releve = models.DateField(default=timezone.localdate)

    t1_longitude = champ_longitude("Point de tracking T1")
    t1_latitude = champ_latitude("Point de tracking T1")
    t2_longitude = champ_longitude("Point de tracking T2")
    t2_latitude = champ_latitude("Point de tracking T2")
    t3_longitude = champ_longitude("Point de tracking T3")
    t3_latitude = champ_latitude("Point de tracking T3")
    t4_longitude = champ_longitude("Point de tracking T4")
    t4_latitude = champ_latitude("Point de tracking T4")

    geometrie = models.LineStringField(
        srid=4326, null=True, blank=True,
        help_text="Construite à partir des points T1 à T4, ou tracée sur la carte.",
    )
    longueur = models.FloatField(
        null=True, blank=True, editable=False, help_text="en km, calculée"
    )
    commentaire = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["route", "date_releve", "id"]
        verbose_name = "relevé de tracking"
        verbose_name_plural = "relevés de tracking"

    def __str__(self):
        return f"{self.route.nom} - relevé du {self.date_releve:%d/%m/%Y}"

    def _synchroniser(self):
        remplis, modifie = self._sommets_saisis()
        geom = self.geometrie

        if remplis and (modifie or geom is None):
            if len(remplis) < 2:
                raise ValidationError("Le relevé nécessite au moins 2 points (T1 et T2).")
            self.geometrie = LineString(remplis, srid=4326)
        elif geom is not None:
            coords = geom.coords
            # au-delà de 4 points, la ligne est conservée mais T1..T4 restent vides
            self._ecrire_sommets(coords if len(coords) <= 4 else [])
        else:
            raise ValidationError(
                "Indiquez au moins T1 et T2, ou tracez le relevé sur la carte."
            )

        # longueur en km, mesurée en projection métrique UTM 30N
        self.longueur = round(
            self.geometrie.transform(32630, clone=True).length / 1000, 3
        )


@receiver([post_save, post_delete], sender=TrackingRoute)
def mettre_a_jour_route(sender, instance, **kwargs):
    route = Route.objects.filter(pk=instance.route_id).first()
    if route:
        route.recalculer()


# ---------------------------------------------------------------------------
# Installations solaires : emprise définie par 4 sommets
# ---------------------------------------------------------------------------

class Installation(SommetsMixin, ProjetBase):
    PREFIXE = "l"

    l1_longitude = champ_longitude("Sommet L1")
    l1_latitude = champ_latitude("Sommet L1")
    l2_longitude = champ_longitude("Sommet L2")
    l2_latitude = champ_latitude("Sommet L2")
    l3_longitude = champ_longitude("Sommet L3")
    l3_latitude = champ_latitude("Sommet L3")
    l4_longitude = champ_longitude("Sommet L4")
    l4_latitude = champ_latitude("Sommet L4")

    geometrie = models.PolygonField(
        srid=4326, null=True, blank=True,
        help_text="Construite à partir des sommets L1 à L4, ou dessinée sur la carte.",
    )
    superficie = models.FloatField(null=True, blank=True, help_text="en m²")

    class Meta(ProjetBase.Meta):
        verbose_name = "installation solaire"
        verbose_name_plural = "installations solaires"

    def _synchroniser(self):
        remplis, modifie = self._sommets_saisis()
        geom = self.geometrie

        if remplis and (modifie or geom is None):
            if len(remplis) != 4:
                raise ValidationError(
                    "Renseignez les 4 sommets L1 à L4 (longitude et latitude)."
                )
            polygone = Polygon(remplis + [remplis[0]], srid=4326)
            if not polygone.valid:
                raise ValidationError(
                    "Les sommets L1 à L4 doivent suivre le contour de l'emprise dans "
                    "l'ordre, sans que les côtés se croisent."
                )
            self.geometrie = polygone
        elif geom is not None:
            anneau = geom.exterior_ring.coords
            self._ecrire_sommets(anneau[:4] if len(anneau) == 5 else [])
        else:
            raise ValidationError(
                "Indiquez les 4 sommets L1 à L4, ou dessinez l'emprise sur la carte."
            )