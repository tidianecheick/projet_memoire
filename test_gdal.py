import os
os.add_dll_directory(r"C:\OSGeo4W\bin")
os.environ["PATH"] = r"C:\OSGeo4W\bin;" + os.environ["PATH"]
os.environ["GDAL_DATA"] = r"C:\OSGeo4W\apps\gdal\share\gdal"
os.environ["PROJ_LIB"] = r"C:\OSGeo4W\share\proj"

from django.conf import settings
settings.configure(
    GDAL_LIBRARY_PATH=r"C:\OSGeo4W\bin\gdal313.dll",
    GEOS_LIBRARY_PATH=r"C:\OSGeo4W\bin\geos_c.dll",
)

from django.contrib.gis.geos import Point
from django.contrib.gis import gdal
print(Point(0, 0))
print("GDAL version :", gdal.gdal_version())