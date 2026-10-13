from django.db import models

# Create your models here.

from django.contrib.gis.db import models


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


class Forage(ProjetBase):
    geometrie = models.PointField(srid=4326)


class Solaire(ProjetBase):
    geometrie = models.PointField(srid=4326)

    class Meta(ProjetBase.Meta):
        verbose_name = "électrification solaire"
        verbose_name_plural = "électrifications solaires"


class Route(ProjetBase):
    geometrie = models.LineStringField(srid=4326)
    longueur = models.FloatField(null=True, blank=True, help_text="en mètres")
    largeur = models.FloatField(null=True, blank=True, help_text="en mètres")


class Installation(ProjetBase):
    geometrie = models.PolygonField(srid=4326)
    superficie = models.FloatField(null=True, blank=True, help_text="en m²")

    class Meta(ProjetBase.Meta):
        verbose_name = "installation solaire"
        verbose_name_plural = "installations solaires"
