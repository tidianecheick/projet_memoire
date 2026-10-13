from django.contrib import admin

# Register your models here.
from django.contrib import admin
from leaflet.admin import LeafletGeoAdmin

from .models import Forage, Solaire, Route, Installation


class ProjetAdmin(LeafletGeoAdmin):
    list_display = ("nom", "localite", "type", "status")
    list_filter = ("status", "localite")
    search_fields = ("nom", "localite", "beneficiaire")


admin.site.register(Forage, ProjetAdmin)
admin.site.register(Solaire, ProjetAdmin)
admin.site.register(Route, ProjetAdmin)
admin.site.register(Installation, ProjetAdmin)
