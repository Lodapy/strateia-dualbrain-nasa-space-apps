"""Loads capas/*.geojson and tablas/*.json into cde_gemelo.gpkg (GeoPackage = SQLite). Run with the QGIS Python:
"C:\\Program Files\\QGIS 3.44.15\\bin\\python-qgis-ltr.bat" cargar_gpkg.py
"""
import json
from pathlib import Path

from osgeo import gdal, ogr

gdal.UseExceptions()
D = Path(__file__).parent
GPKG = D / "cde_gemelo.gpkg"
if GPKG.exists():
    GPKG.unlink()
for i, capa in enumerate(sorted((D / "capas").glob("*.geojson"))):
    gdal.VectorTranslate(str(GPKG), str(capa), format="GPKG", layerName=capa.stem, accessMode=None if i == 0 else "update",
                         dstSRS="EPSG:4326", geometryType="PROMOTE_TO_MULTI", layerCreationOptions=["SPATIAL_INDEX=YES"])
    print("layer", capa.stem)
ds = ogr.Open(str(GPKG), 1)
for tabla in sorted((D / "tablas").glob("*.json")):
    filas = json.load(open(tabla, encoding="utf-8"))
    if isinstance(filas, dict):  # e.g. no2_diario_cde.json: summary + "serie"
        filas = filas.get("serie", [])
    if not filas or not isinstance(filas[0], dict):
        print("table skipped (no rows):", tabla.stem)
        continue
    lyr = ds.CreateLayer(tabla.stem, geom_type=ogr.wkbNone)
    campos = list(dict.fromkeys(k for f in filas for k in f))
    for c in campos:
        muestra = next((f[c] for f in filas if f.get(c) is not None), "")
        t = ogr.OFTInteger64 if isinstance(muestra, bool) is False and isinstance(muestra, int) else ogr.OFTReal if isinstance(muestra, float) else ogr.OFTString
        lyr.CreateField(ogr.FieldDefn(c, t))
    for f in filas:
        ft = ogr.Feature(lyr.GetLayerDefn())
        for c in campos:
            v = f.get(c)
            if v is not None:
                ft.SetField(c, json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict, bool)) else v)
        lyr.CreateFeature(ft)
    print("table", tabla.stem, len(filas))
ds = None
print("GeoPackage ready:", GPKG, GPKG.stat().st_size // 1024, "KB")
