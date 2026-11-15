"""Base cartográfica curada de Ciudad del Este para IA (StrateIA Dual Brain): capas GeoJSON + tablas, todas con fuente, fecha y calidad.

Uso: python construir_base.py   (Python 3.12 con shapely y numpy). Después: cargar_gpkg.py con el Python de QGIS.
Entradas: insumos/ (resultados intermedios de Earth Engine y análisis), edificios con altura (CDE_EDIFICIOS) y datos del gemelo (CDE_GEMELO).
Salida: capas/*.geojson y tablas/*.json. EPSG:4326. Nada se imputa: si un dato falta, el campo queda null y se dice en «calidad».
"""
import heapq
import json
import math
import os
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping
from shapely.ops import unary_union

OUT = Path(__file__).parent
SC = Path(os.getenv("CDE_INSUMOS", OUT / "insumos"))
M3D = Path(os.getenv("CDE_EDIFICIOS", OUT / "edificios"))  # salida/edificios_cde_altura.geojson y salida/construcciones_por_anio.json
GEMELO = Path(os.getenv("CDE_GEMELO", OUT.parent.parent / "stratos-gemelo-cde"))
(OUT / "capas").mkdir(exist_ok=True)
(OUT / "tablas").mkdir(exist_ok=True)
HOY = "2026-11-14"
cargar = lambda p: json.load(open(p, encoding="utf-8"))


def guardar_capa(nombre, feats):
    json.dump({"type": "FeatureCollection", "name": nombre, "features": feats}, open(OUT / "capas" / f"{nombre}.geojson", "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"capa {nombre}: {len(feats)} elementos", flush=True)


def guardar_tabla(nombre, filas):
    json.dump(filas, open(OUT / "tablas" / f"{nombre}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"tabla {nombre}: {len(filas)} filas", flush=True)


def feat(geom, **props):
    return {"type": "Feature", "geometry": geom if isinstance(geom, dict) or geom is None else mapping(geom), "properties": props}


rect = lambda w, s, e, n: {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}

# ---------- grilla NASADEM de la ciudad (30 m) y crecida conectada ----------
dem = cargar(SC / "dem_ciudad.json")
E = np.array(dem["elev"], float); E[E < -9000] = np.nan
R, C = E.shape
W, S, Ea, N = dem["bbox"]
dlo, dla = (Ea - W) / C, (N - S) / R
celda = lambda i, j: box(W + j * dlo, N - (i + 1) * dla, W + (j + 1) * dlo, N - i * dla)
cre = cargar(SC / "crecida_ciudad.json")
cota_celda = {}
for k in sorted(cre["niveles"], key=float, reverse=True):
    for i, j in cre["niveles"][k]["celdas"]:
        cota_celda[(i, j)] = float(k)  # queda la cota más baja que alcanza la celda

# ---------- 1 · crecida del río por cota ----------
crec = []
for k in sorted(cre["niveles"], key=float):
    nv = cre["niveles"][k]
    g = unary_union([celda(i, j) for i, j in nv["celdas"]]).simplify(0.00012)
    crec.append(feat(g, cota_msnm=float(k), tierra_ha=nv["tierra_ha"], edificios_alcanzados=nv["edificios"],
                     metodo="relleno conectado (8 vecinos) desde agua permanente JRC > 50 % sobre NASADEM 30 m; sin defensas ni drenaje",
                     fuente="NASA NASADEM; JRC GSW v1.4; edificios OSM + Google Open Buildings", fecha=HOY,
                     calidad="modelo; subestima familias (asentamientos informales fuera del mapa, edificios multifamiliares)"))
guardar_capa("crecida_rio", crec)

# ---------- barrios (OpenStreetMap, nombres normalizados) para filtrar sin librerías geográficas en el servidor ----------
import re
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
norm_b = lambda n: re.sub(r"^(ba\.|bº|barrio)\s*", "", (n or "sin nombre").strip(), flags=re.I).strip().title()
BARRIOS = [(norm_b(f["properties"].get("nombre")), shape(f["geometry"])) for f in cargar(OUT / "capas" / "barrios_osm.geojson")["features"]] \
    if (OUT / "capas" / "barrios_osm.geojson").exists() else []
ARB_B = STRtree([g for _, g in BARRIOS]) if BARRIOS else None


def barrio_de(lon, lat):
    if not ARB_B:
        return None
    p = Point(lon, lat)
    return next((BARRIOS[i][0] for i in ARB_B.query(p) if BARRIOS[i][1].contains(p)), None)


# ---------- 2 · edificios con cota de alcance, calor y año de aparición ----------
lst = cargar(SC / "lst_cde.json")
LT = np.array(lst["lst_c"], float); LT[LT < -9000] = np.nan
lw, ls_, le, ln_ = lst["bbox"]; lR, lC = LT.shape
anio_osm = cargar(M3D / "salida" / "construcciones_por_anio.json")
eds, nuevos_riesgo = [], Counter()
for f in cargar(M3D / "salida" / "edificios_cde_altura.geojson")["features"]:
    ring = f["geometry"]["coordinates"][0]
    lo = sum(p[0] for p in ring) / len(ring); la = sum(p[1] for p in ring) / len(ring)
    cota = cota_celda.get((int((N - la) / dla), int((lo - W) / dlo)))
    li, lj = int((ln_ - la) / ((ln_ - ls_) / lR)), int((lo - lw) / ((le - lw) / lC))
    t = float(LT[li, lj]) if 0 <= li < lR and 0 <= lj < lC and not np.isnan(LT[li, lj]) else None
    pr = f["properties"]
    anio = anio_osm.get(str(pr.get("osm_id")))
    if cota is not None and cota <= 121.19 and anio and 2018 <= anio <= 2023:
        nuevos_riesgo[anio] += 1
    eds.append(feat(f["geometry"], osm_id=pr.get("osm_id"), barrio=barrio_de(lo, la), altura_m=pr.get("altura_m"), fuente_altura=pr.get("fuente_altura"),
                    cota_alcance_msnm=cota, lst_verano_c=round(t, 1) if t is not None else None, anio_aparicion=anio,
                    fuente="OSM (ODbL); alturas Google Open Buildings 2.5D / 3D-GloBFP; cota: modelo NASADEM; LST: Landsat 8/9 dic–feb 2023–2026",
                    calidad="altura null = sin dato (no imputada); anio_aparicion = primer año en Open Buildings Temporal (2016–2023)"))
guardar_capa("edificios", eds)

# ---------- 2b · validación del modelo de crecida contra los barrios afectados (registro oficial, QZ 18/10/2026) ----------
AFECTADOS = [("San Rafael y San Agustín", ("San Rafael", "San Agustín", "San Agustin"), 380), ("Ex Cantera", ("Cantera",), 260),
             ("Remansito", ("Remansito",), 155), ("Che la Reina", ("Reina",), 130), ("Belén (asentamiento)", ("Belén", "Belen"), 100),
             ("Santa Ana", ("Santa Ana",), 80), ("Km 9 Monday y 8 de Diciembre", ("Kilómetro 9", "Km 9", "8 De Diciembre"), 70),
             ("Km 10 Acaray y Yrendague", ("Kilómetro 10 Acaray", "Km 10", "Yrendague"), 50), ("23 de Octubre", ("23 De Octubre",), 5)]
val = []
for nombre, claves, familias in AFECTADOS:
    osm = sorted({b for b, _ in BARRIOS if any(k.lower() in b.lower() for k in claves)})
    e121 = sum(1 for e in eds if e["properties"]["barrio"] in osm and (e["properties"]["cota_alcance_msnm"] or 999) <= 121.19)
    e128 = sum(1 for e in eds if e["properties"]["barrio"] in osm and (e["properties"]["cota_alcance_msnm"] or 999) <= 128)
    val.append({"barrio_registro": nombre, "familias_afectadas": familias, "barrios_osm": ", ".join(osm) or None,
                "edificios_modelo_121": e121, "edificios_modelo_128": e128,
                "resultado": "sin barrio en OSM: no se puede comparar" if not osm else "el modelo lo capta" if e121 else "el modelo NO lo capta",
                "confianza": "[CONFIRMADO CON EVIDENCIA]" if osm else "[INCIERTO]",
                "fuente": "QZ Noticias 18/10/2026 («registro oficial») vs modelo NASADEM", "calidad": "barrios de OSM; un edificio no es una familia"})
guardar_tabla("validacion_crecida_barrios", val)
captados = sum(1 for v in val if v["resultado"] == "el modelo lo capta")
comparables = sum(1 for v in val if v["barrios_osm"])

# ---------- 3 · calles con riesgo de baches ----------
B = cargar(SC / "baches.json")
_vistos, _unicos = set(), []
for t in B["tramos"]:  # la capa vial trae tramos repetidos (misma geometría y atributos): se cuentan una vez
    k = json.dumps(t, sort_keys=True, ensure_ascii=False)
    if k not in _vistos:
        _vistos.add(k); _unicos.append(t)
print("calles: tramos duplicados quitados:", len(B["tramos"]) - len(_unicos))
B["tramos"] = _unicos
KM = lambda clase: round(sum(t["km"] for t in B["tramos"] if t["clase"] == clase), 1)
N_ = lambda clase: sum(1 for t in B["tramos"] if t["clase"] == clase)
guardar_capa("calles", [feat({"type": "MultiLineString", "coordinates": t["geom"]}, nombre=t["nombre"] or None,
                             barrio=barrio_de(*t["geom"][0][len(t["geom"][0]) // 2]), superficie=t["sup"], tipo=t["tipo"],
                             riesgo_baches=t["clase"], cauce_ha=t["aguas_ha"], bajo_cota_118=t["en118"], largo_km=t["km"],
                             fuente="capa vial vias.geojson (proyecto TwinDigitalGobernance; origen a confirmar); drenaje NASADEM",
                             calidad="riesgo modelado, no baches observados; validar con reportes municipales") for t in B["tramos"]])

# ---------- 4 · cauces (drenaje D8 sobre NASADEM con pozos rellenados) ----------
Ef = np.where(np.isnan(E), np.nanmax(E) + 100, E).copy()
hecho = np.zeros((R, C), bool); cola = []
for i in range(R):
    for j in range(C):
        if i in (0, R - 1) or j in (0, C - 1):
            heapq.heappush(cola, (Ef[i, j], i, j)); hecho[i, j] = True
V8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
while cola:
    z, i, j = heapq.heappop(cola)
    for di, dj in V8:
        a, b = i + di, j + dj
        if 0 <= a < R and 0 <= b < C and not hecho[a, b]:
            hecho[a, b] = True; Ef[a, b] = max(Ef[a, b], z + 1e-4); heapq.heappush(cola, (Ef[a, b], a, b))
acc = np.ones((R, C)); dest = {}
for idx in np.argsort(-Ef, axis=None):
    i, j = divmod(int(idx), C)
    mejor, d_ = 0.0, None
    for di, dj in V8:
        a, b = i + di, j + dj
        if 0 <= a < R and 0 <= b < C:
            p_ = (Ef[i, j] - Ef[a, b]) / math.hypot(di, dj)
            if p_ > mejor:
                mejor, d_ = p_, (a, b)
    if d_:
        acc[d_] += acc[i, j]; dest[(i, j)] = d_
ha_celda = dlo * 111195 * math.cos(math.radians((S + N) / 2)) * dla * 111195 / 1e4
centro = lambda i, j: (W + (j + .5) * dlo, N - (i + .5) * dla)
guardar_capa("cauces", [feat({"type": "LineString", "coordinates": [centro(i, j), centro(a, b)]}, area_aguas_arriba_ha=round(acc[i, j] * ha_celda, 1),
                             orden="arroyo" if acc[i, j] * ha_celda >= 500 else "cauce" if acc[i, j] * ha_celda >= 100 else "escurrimiento",
                             fuente="NASA NASADEM 30 m; relleno priority-flood + D8", calidad="derivado del terreno; no incluye desagües construidos")
                        for (i, j), (a, b) in dest.items() if acc[i, j] * ha_celda >= 20])

# ---------- 5 · valle, agua observada, calor, cobertura, zonas de análisis ----------
v = next(z for z in cargar(GEMELO / "web" / "public" / "data" / "zonas.json")["zonas"] if z["id"] == "valle")
hip = dict((round(e - v["fondo"]["elev_m"]), a) for e, a in v["hipsometria"])
geo_valle = {"type": "Polygon", "coordinates": [v["poligono"] + v["poligono"][:1]]}
guardar_capa("valle", [feat(geo_valle, nombre=v["nombre"], fondo_msnm=v["fondo"]["elev_m"], area_ha=round(v["hipsometria"][-1][1], 1),
                            inundado_ha_mas3m=hip.get(3), inundado_ha_mas10m=hip.get(10), agua_radar_2026_max_ha=0.22,
                            fuente="NASADEM ∩ Copernicus GLO-30; modelo de bañera; radar Sentinel-1 2026",
                            calidad="susceptibilidad topográfica; el radar no vio agua en el valle en 2026")])
ap = cargar(SC / "agua_por_anio_poligonos.json")
guardar_capa("agua_anual", [feat(p["geom"], anio=int(a), clase="permanente" if p["clase"] == 3 else "estacional",
                                 fuente="JRC GSW v1.4 (Landsat)" if int(a) <= 2021 else "Copernicus Sentinel-2 L2A (método propio)",
                                 calidad="2022–2026 con otro método: comparar con cautela") for a, ps in ap.items() for p in ps])
s1 = cargar(SC / "s1_agua_clasificada.geojson")
guardar_capa("agua_radar_20261015", [feat(f["geometry"], clase=f["properties"]["clase"], area_ha=round(f["properties"]["ha"], 2),
                                          elev_msnm=round(f["properties"]["elev"]), fuente="Copernicus Sentinel-1 GRD órbita 170, 03/10 vs 15/10/2026",
                                          calidad="plausible < 120 m; dudosa > 120 m; descartada = agua permanente") for f in s1["features"]])
v80, v90, v97 = (float(np.nanpercentile(LT, q)) for q in (80, 90, 97))
dx, dy = (le - lw) / lC, (ln_ - ls_) / lR
cal = []
for lo_, hi_, nom in ((v80, v90, "p80–p90"), (v90, v97, "p90–p97"), (v97, 99.0, "> p97")):
    cel = [box(lw + j * dx, ln_ - (i + 1) * dy, lw + (j + 1) * dx, ln_ - i * dy) for i in range(lR) for j in range(lC)
           if not np.isnan(LT[i, j]) and lo_ <= LT[i, j] < hi_]
    cal.append(feat(unary_union(cel).simplify(0.0003), clase=nom, desde_c=round(lo_, 1), hasta_c=round(hi_, 1) if hi_ < 99 else None,
                    fuente="Landsat 8/9 C2 L2 ST_B10, mediana dic–feb 2023–2026 (46 escenas)", calidad="temperatura del suelo y techos, no del aire"))
guardar_capa("calor_verano", cal)
rt = cargar(SC / "regiones_trend.json")
guardar_capa("cobertura", [feat(p["geom"], clase=k, area_ha=round(p["ha"], 1), fuente="ESA WorldCover v200 (2021)", calidad="vectorizado a 40 m, simplificado 30 m")
                           for k in ("urbano", "arbolado") for p in rt[k]])
guardar_capa("zonas_analisis", [
    feat(rect(-54.640, -25.520, -54.585, -25.490), zona="ribera_valle_parana", uso="agua superficial por año (indicador del dashboard)"),
    feat(rect(W, S, Ea, N), zona="caja_ciudad", uso="agua, luz nocturna y población de toda la ciudad"),
    feat(rect(-54.6875, -25.75, -54.0625, -25.25), zona="celda_power_aprox", uso="lluvia NASA POWER (celda MERRA-2 aproximada, sin verificar)")])

# ---------- 6 · tablas ----------
T = cargar(SC / "tendencias.json")
guardar_tabla("tendencias", [{k: v_[k] for k in ("variable", "region", "unidad", "fuente", "definicion", "n", "sen_por_decada", "sen_ic95_decada", "mk_p",
                                                 "ols_por_decada", "ols_ic95_decada", "ols_p", "r2", "significativa_95", "direccion")} for v_ in T["tendencias"]])
guardar_tabla("relacion_oni", T["relacion_oni"])
guardar_tabla("series_anuales", [{"variable": v_["variable"], "region": v_["region"], "anio": a, "valor": y, "unidad": v_["unidad"]}
                                 for v_ in T["tendencias"] for a, y in zip(v_["anios"], v_["valores"])])
guardar_tabla("eventos_crecida_2026", [
    {"fecha": "2026-10-12", "hecho": "Paraná en cota 116; lluvia del día IMERG 105,6 mm, POWER 65 mm", "lugar": "CDE", "fuente": "Hoy (13/10) cita SEN; NASA"},
    {"fecha": "2026-10-13", "hecho": "Más de 100 familias evacuadas (110–120 personas)", "lugar": "San Rafael", "fuente": "Hoy, SEN, Itaipú"},
    {"fecha": "2026-10-14", "hecho": "Al menos 287 familias dejaron sus hogares", "lugar": "CDE", "fuente": "La Nación (sin atribución)"},
    {"fecha": "2026-10-15", "hecho": "Radar Sentinel-1: 155 ha de agua en la ribera, máximo del año", "lugar": "ribera", "fuente": "Copernicus (cálculo propio)"},
    {"fecha": "2026-10-16", "hecho": "Paraná a 121,19 msnm; 1.300 familias reubicadas en Alto Paraná", "lugar": "Alto Paraná", "fuente": "EFE/Infobae: Itaipú y SEN"},
    {"fecha": "2026-10-16", "hecho": "~1.000 familias y ~3.000 personas fuera de sus casas; 1 fallecido; 5 barrios", "lugar": "CDE (Remansito, San Rafael…)", "fuente": "1140 AM: intendente Pedro Acuña"},
    {"fecha": "2026-10-18", "hecho": "1.210 familias afectadas en 12 barrios: San Rafael y San Agustín 380, Ex Cantera 260, Remansito 155, Che la Reina 130, Belén 100, Santa Ana 80, Km 9 Monday y 8 de Diciembre 70, Km 10 Acaray y Yrendague 50, 23 de Octubre 5", "lugar": "CDE", "fuente": "QZ Noticias («registro oficial», sin atribución)"},
    {"fecha": "2026-10-26", "hecho": "Sentinel-2: 278 ha de agua en la ribera, máximo del año", "lugar": "ribera", "fuente": "Copernicus (cálculo propio)"}])
guardar_tabla("fuentes", [
    {"dato": "GPM IMERG V07", "proveedor": "NASA", "resolucion": "0,1° · 30 min", "periodo": "2000–", "acceso": "Earth Engine NASA/GPM_L3/IMERG_V07", "licencia": "abierta (NASA)"},
    {"dato": "POWER PRECTOTCORR", "proveedor": "NASA (modelo MERRA-2/GEOS)", "resolucion": "~0,5° · diario", "periodo": "1981–", "acceso": "API power.larc.nasa.gov", "licencia": "abierta"},
    {"dato": "Landsat 5/7/8/9 C2 L2 ST", "proveedor": "NASA/USGS", "resolucion": "30 m (térmico 100 m) · 8–16 días", "periodo": "1984–", "acceso": "Earth Engine", "licencia": "abierta"},
    {"dato": "NASADEM", "proveedor": "NASA", "resolucion": "30 m", "periodo": "2000", "acceso": "Earth Engine NASA/NASADEM_HGT/001", "licencia": "abierta"},
    {"dato": "Black Marble VNP46A2", "proveedor": "NASA", "resolucion": "500 m · diario", "periodo": "2012–", "acceso": "Earth Engine NASA/VIIRS/002/VNP46A2", "licencia": "abierta"},
    {"dato": "FIRMS VIIRS S-NPP NRT", "proveedor": "NASA", "resolucion": "375 m · casi tiempo real", "periodo": "últimos 5 días", "acceso": "API FIRMS (MAP_KEY)", "licencia": "abierta"},
    {"dato": "JRC Global Surface Water v1.4", "proveedor": "Comisión Europea JRC (sobre Landsat)", "resolucion": "30 m · anual/mensual", "periodo": "1984–2021", "acceso": "Earth Engine", "licencia": "abierta"},
    {"dato": "Sentinel-1 GRD / Sentinel-2 L2A", "proveedor": "ESA/Copernicus", "resolucion": "10 m · 5–12 días", "periodo": "2014– / 2017–", "acceso": "Earth Engine", "licencia": "abierta Copernicus"},
    {"dato": "Copernicus DEM GLO-30", "proveedor": "ESA/Copernicus", "resolucion": "30 m", "periodo": "2011–2015", "acceso": "Earth Engine", "licencia": "COP-DEM-GLO-30-F"},
    {"dato": "ESA WorldCover v200", "proveedor": "ESA", "resolucion": "10 m", "periodo": "2021", "acceso": "Earth Engine", "licencia": "CC BY 4.0"},
    {"dato": "GHSL GHS-POP R2023A", "proveedor": "JRC", "resolucion": "100 m · cada 5 años", "periodo": "1975–2030 (modelado)", "acceso": "Earth Engine", "licencia": "abierta"},
    {"dato": "ONI", "proveedor": "NOAA CPC", "resolucion": "mensual (Niño 3.4)", "periodo": "1950–", "acceso": "cpc.ncep.noaa.gov", "licencia": "dominio público"},
    {"dato": "OSM calles y edificios", "proveedor": "OpenStreetMap", "resolucion": "vector", "periodo": "base 2026-11-10", "acceso": "Overpass", "licencia": "ODbL"},
    {"dato": "Alturas Open Buildings 2.5D / 3D-GloBFP", "proveedor": "Google / Che et al. 2024", "resolucion": "vector / 4 m", "periodo": "2016–2023 / 2020", "acceso": "Earth Engine / figshare", "licencia": "a verificar / CC BY 4.0"},
    {"dato": "Capa vial vias.geojson", "proveedor": "proyecto TwinDigitalGobernance", "resolucion": "vector", "periodo": "s/d", "acceso": "archivo local", "licencia": "origen a confirmar"},
    {"dato": "Evacuados octubre 2026", "proveedor": "SEN, Municipalidad, Itaipú vía prensa", "resolucion": "por barrio", "periodo": "13–18/10/2026", "acceso": "notas de prensa", "licencia": "cita"}])

# ---------- 6b · series Copernicus (Sentinel-1, Sentinel-2, Sentinel-5P) ----------
import csv
SER = GEMELO / "export" / "series"
leer_csv = lambda n: list(csv.DictReader(open(SER / n, encoding="utf-8")))
num = lambda x: float(x) if x not in ("", None) else None
plat = cargar(SC / "s1_plataformas.json")
guardar_tabla("serie_sentinel1", [{"fecha": r["fecha"], "zona": r["zona"], "agua_ha": num(r["agua_ha"]), "observado_pct": num(r["observado_pct"]),
                                   "satelite": "/".join(plat.get(r["fecha"], [])) or None,
                                   "usar": plat.get(r["fecha"]) != ["S1D"],
                                   "fuente": "Copernicus Sentinel-1 GRD órbita 170; agua = VV < -16 dB, pendiente < 5°",
                                   "calidad": "S1D (nuevo, pasa 1 día después) da valores atípicos: usar = false"}
                                  for r in leer_csv("agua_sentinel1_orbita170_2025_2026.csv")])
guardar_tabla("serie_sentinel2", [{"fecha": r["fecha"], "zona": r["zona"], "agua_ha": num(r["agua_ha"]), "observado_pct": num(r["observado_pct"]),
                                   "usar": num(r["observado_pct"]) is not None and num(r["observado_pct"]) >= 80,
                                   "fuente": "Copernicus Sentinel-2 L2A; agua = MNDWI (B3, B11) > 0 sin nubes (SCL)",
                                   "calidad": "solo escenas con ≥ 80 % de la zona observada: usar = true"}
                                  for r in leer_csv("agua_sentinel2_escenas_2026.csv")])
guardar_tabla("agua_anual_sentinel2_ha", [{"anio": int(r["anio"]), "zona": r["zona"], "permanente_ha": num(r["permanente_ha"]), "estacional_ha": num(r["estacional_ha"]),
                                           "fuente": "Copernicus Sentinel-2 L2A, meses con agua / meses observados (permanente ≥ 90 %)",
                                           "calidad": "2021 se calculó para comparar con JRC: total 239 vs 224 ha; el reparto permanente/estacional difiere"}
                                          for r in leer_csv("agua_anual_sentinel2_2021_2026.csv")])
snap = cargar(GEMELO / "web" / "public" / "data" / "snapshot.json")
guardar_tabla("pasadas_copernicus", [{"coleccion": col, "producto_id": x["id"], "fecha": x["fecha"], "nubes_pct": x.get("nubes_pct"), "plataforma": x.get("plataforma"),
                                      "fuente": "Copernicus Data Space STAC (búsqueda sin cuenta)", "generado": snap["generado"],
                                      "calidad": "solo metadatos de pasadas; Sentinel-5P NO₂ NRTI sin medición usada"}
                                     for col, lista in (snap["copernicus"]["datos"] or {}).items() for x in lista])

# ---------- 7 · registro de problemas (curado) ----------
geo_crecida = next(f for f in crec if f["properties"]["cota_msnm"] == 121.19)["geometry"]
alto = [t["geom"] for t in B["tramos"] if t["clase"] == "alto"]
nuevos = sum(nuevos_riesgo.values())
PROB = [
    {"id": "P1", "problema": "Crecida del río Paraná (remanso hacia los barrios ribereños)", "sector": "agua y emergencias", "geom": geo_crecida,
     "indicadores": {"pico_msnm": 121.19, "cota_segura_sen_msnm": 118, "edificios_modelo_121": cre["niveles"]["121.19"]["edificios"],
                     "tierra_ha_121": cre["niveles"]["121.19"]["tierra_ha"], "familias_afectadas_registro": 1210, "agua_radar_15oct_ha": 155, "agua_s2_26oct_ha": 278},
     "evidencia": ["eventos_crecida_2026", "crecida_rio", "agua_radar_20261015", "agua_anual"],
     "confianza": "[CONFIRMADO CON EVIDENCIA] el evento ocurrió (prensa + Itaipú + radar); [SOSPECHOSO - REQUIERE VALIDACIÓN] el modelo subestima familias y "
                  f"solo capta {captados} de {comparables} barrios afectados comparables: NO alcanza San Rafael ni Che la Reina hasta 128 m. "
                  "No alertar por crecida con este modelo en esos barrios: usar las cotas de referencia locales (cotas_referencia).",
     "causas": ["El Niño (ONI +2,46 ASO-2026)", "lluvias en el sur de Brasil", "caudal del Iguazú y del Acaray", "operación de Itaipú (vertedero)",
                "remanso sobre el arroyo Acaraymí (hipótesis del documento del dueño; explicaría la falla del modelo en San Rafael)"],
     "datos_faltantes": ["nivel horario de Itaipú", "padrón de familias por barrio", "asentamientos informales mapeados",
                         "trazado del arroyo Acaraymí (no figura en la hidrografía oficial ni en OSM)", "modelo de terreno sin techos ni árboles (DTM) en San Rafael"],
     "intervenciones": ["alerta por cota con umbrales por barrio (108,40 m: puente peatonal de San Rafael)", "reubicación preventiva de todos los que viven por debajo de 118 m",
                        "prohibir construcciones nuevas por debajo de 121 m", "refugios y rutas fuera de la mancha de 128 m"]},
    {"id": "P2", "problema": "Construcción nueva dentro de la zona de crecida", "sector": "vivienda y suelo", "geom": geo_crecida,
     "indicadores": {"edificios_nuevos_2018_2023_bajo_121": nuevos, "por_anio": dict(sorted(nuevos_riesgo.items())),
                     "luz_nocturna_km2_por_decada": 58.45, "poblacion_modelada_por_decada": 84647},
     "evidencia": ["edificios (anio_aparicion, cota_alcance_msnm)", "tendencias"],
     "confianza": "[CONFIRMADO CON EVIDENCIA] hay edificios que aparecen entre 2018 y 2023 bajo la cota 121 (Open Buildings Temporal); la cifra depende del modelo de crecida",
     "causas": ["crecimiento urbano rápido", "suelo barato en la ribera", "falta de control de uso del suelo"],
     "datos_faltantes": ["catastro municipal", "permisos de construcción"],
     "intervenciones": ["zonificación: la planicie como parque", "alerta anual de construcción nueva por satélite"]},
    {"id": "P3", "problema": "Baches y calles intransitables después de lluvias fuertes", "sector": "movilidad e infraestructura",
     "geom": {"type": "MultiLineString", "coordinates": [ln for g in alto for ln in g]},
     "indicadores": {"tramos_alto": N_("alto"), "km_alto": KM("alto"), "tramos_medio": N_("medio"), "km_medio": KM("medio"), "vias_principales_km_alto": dict(B["top"][:8]),
                     "dias_50mm_tendencia_p": 0.3021},
     "evidencia": ["calles", "cauces", "tendencias"], "confianza": "[SOSPECHOSO - REQUIERE VALIDACIÓN] modelo sin reportes de baches",
     "causas": ["escurrimiento que cruza la calzada", "tránsito pesado", "calles de tierra sobre cauces", "falta de desagües"],
     "datos_faltantes": ["reportes de baches municipales", "red de desagües", "estado del pavimento"],
     "intervenciones": ["mantenimiento preventivo antes de octubre en los cruces de cauce de PY02 y PY07", "alcantarillas y badenes en cruces de cauce",
                        "pavimento permeable en calles de tierra sobre cauces"]},
    {"id": "P4", "problema": "Isla de calor urbana en crecimiento", "sector": "clima y salud", "geom": cal[2]["geometry"],
     "indicadores": {"isla_calor_c_por_decada": 0.562, "isla_p": 0.0001, "lst_urbano_c_por_decada": 1.569, "lst_arbolado_c_por_decada": 0.931,
                     "umbral_p97_c": round(v97, 1)},
     "evidencia": ["tendencias", "calor_verano", "cobertura"], "confianza": "[CONFIRMADO CON EVIDENCIA] tendencia (Mann-Kendall p = 0,0001); causa urbana [SOSPECHOSO]",
     "causas": ["más superficie construida", "menos árboles", "techos y asfalto"], "datos_faltantes": ["temperatura del aire por barrio", "consumo eléctrico ANDE"],
     "intervenciones": ["arbolado prioritario en el calor > p97 sin árboles", "techos fríos en edificios públicos", "corredores verdes sobre cauces"]},
    {"id": "P5", "problema": "Menos agua permanente y más agua estacional en la ribera", "sector": "agua", "geom": rect(-54.640, -25.520, -54.585, -25.490),
     "indicadores": {"permanente_ha_por_decada": -6.05, "p": 0.0004, "estacional_ha_por_decada": 2.9, "p_estacional": 0.0263},
     "evidencia": ["tendencias", "agua_anual"], "confianza": "[CONFIRMADO CON EVIDENCIA] tendencia JRC 1990–2021; causa [INCIERTO]",
     "causas": ["operación de represas", "bajante 2019–2021", "cambio del cauce (hipótesis)"], "datos_faltantes": ["caudales de Itaipú y Acaray"],
     "intervenciones": ["monitoreo anual con Sentinel-2", "la planicie que se inunda y se seca como parque, sin viviendas"]},
    {"id": "P6", "problema": "Anegamiento del valle bajo de arroyo por lluvia", "sector": "agua", "geom": geo_valle,
     "indicadores": {"fondo_msnm": 129, "area_ha": 54, "inundado_ha_mas3m": hip.get(3), "inundado_ha_mas10m": hip.get(10), "agua_radar_2026_max_ha": 0.22},
     "evidencia": ["valle", "cauces"], "confianza": "[INCIERTO] susceptibilidad topográfica; el radar no lo vio inundado en 2026",
     "causas": ["forma del terreno", "drenaje insuficiente (hipótesis)"], "datos_faltantes": ["registros municipales de anegamiento"],
     "intervenciones": ["franjas de retención vegetal (método BIDARA)", "limpieza del cauce antes de octubre"]},
    {"id": "P7", "problema": "Dengue después de lluvias y calor", "sector": "salud", "geom": None, "indicadores": {},
     "evidencia": [], "confianza": "[INCIERTO] hipótesis sin datos de casos", "causas": ["lluvia + calor → agua estancada → mosquitos"],
     "datos_faltantes": ["casos semanales del Ministerio de Salud por barrio"], "intervenciones": ["descacharrado 2–3 semanas después de lluvias fuertes (a validar)"]},
    {"id": "P8", "problema": "Bajante, sequía e incendios después de El Niño", "sector": "ambiente", "geom": None,
     "indicadores": {"agua_permanente_minima_ha": 155.9, "anio_minimo": 2021, "focos_firms_ultimos_5_dias": 0},
     "evidencia": ["series_anuales", "fuentes (FIRMS)"], "confianza": "[INCIERTO] para el ciclo próximo; [CONFIRMADO CON EVIDENCIA] el mínimo de 2021 en JRC",
     "causas": ["La Niña", "operación de represas"], "datos_faltantes": ["humedad del suelo SMAP", "caudales"],
     "intervenciones": ["vigilancia de focos FIRMS y humo", "prohibición de quemas en sequía"]},
]
if (OUT / "tablas" / "quemas_por_barrio.json").exists():
    qb = cargar(OUT / "tablas" / "quemas_por_barrio.json"); qm = cargar(OUT / "tablas" / "quemas_por_mes.json")
    aa = {r["anio"]: r for r in cargar(OUT / "tablas" / "aire_anual.json")}
    tb = cargar(OUT / "tablas" / "turbidez_por_barrio.json")
    dens = sorted([b for b in qb if b.get("focos_por_km2") and b["focos"] >= 10], key=lambda b: -b["focos_por_km2"])[:6]
    PROB.append({"id": "P9", "problema": "Quemas y calidad del aire (humo, quema de basura, smog)", "sector": "aire y salud", "geom": None,
                 "indicadores": {"focos_firms_cde_2012_2026": sum(b["focos"] for b in qb), "meses_pico": {m["nombre"]: m["focos_total"] for m in qm if m["mes"] in (7, 8, 9)},
                                 "barrios_mas_focos": {b["barrio"]: b["focos"] for b in qb[:6]}, "barrios_mas_focos_por_km2": {b["barrio"]: b["focos_por_km2"] for b in dens},
                                 "barrios_aire_mas_turbio": {b["barrio"]: b["anios_en_20pct_mas_turbio_prom"] for b in tb[:5]},
                                 "dias_humo_2024": aa.get(2024, {}).get("dias_humo_ai_mayor_1"), "no2_cde_vs_region_pct": 52,
                                 "viento_vs_no2_rho": -0.092, "viento_vs_no2_p": "< 0,0001"},
                 "evidencia": ["focos_historicos_cde", "sitios_quema_persistente", "quemas_por_barrio", "quemas_por_mes", "turbidez_temporada_seca", "aire_anual", "aire_diario"],
                 "confianza": "[CONFIRMADO CON EVIDENCIA] temporada de quemas jul–sep y humo regional 2024; [SOSPECHOSO - REQUIERE VALIDACIÓN] que los focos sean basura (FIRMS no distingue); quemas chicas no se ven",
                 "causas": ["temporada seca", "quema de basura y de pastizales (hipótesis)", "humo regional de incendios", "tránsito (NO₂)", "aire estancado con poco viento"],
                 "datos_faltantes": ["denuncias de quema por barrio (Municipalidad, MADES, bomberos)", "sensores de PM2.5 en terreno", "ubicación de basurales y olerías"],
                 "intervenciones": ["recolección reforzada y campaña contra la quema antes de julio en los barrios con más focos",
                                    "inspección de los sitios de quema persistente", "alerta de humo y prohibición de quemas en días sin viento"]})
guardar_capa("problemas", [feat(p["geom"], **{k: (json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else x) for k, x in p.items() if k != "geom"})
                           for p in PROB])

# ---------- 7b · base de conocimientos del dueño (2026-11-15): cotas locales, afirmaciones verificadas y tareas propuestas ----------
DOC = "documento «Base de Conocimientos: CDE Smart Digital Twin City» del dueño (2026-11-15), sin citas"
C_, S_, I_ = "[CONFIRMADO CON EVIDENCIA]", "[SOSPECHOSO - REQUIERE VALIDACIÓN]", "[INCIERTO]"
guardar_tabla("cotas_referencia", [
    {"cota_m": 108.40, "efecto": "Inunda el puente peatonal de San Rafael", "referencia": "Puente de la Amistad (escala a confirmar)", "fuente": DOC,
     "contraste": "En el modelo NASADEM, 108 m es la primera cota que alcanza edificios (14, en Remansito); a San Rafael no llega ni a 128 m.", "confianza": S_},
    {"cota_m": 112.30, "efecto": "Inunda calles de concreto", "referencia": "Puente de la Amistad (escala a confirmar)", "fuente": DOC,
     "contraste": "Sin dato propio para contrastar.", "confianza": S_},
    {"cota_m": 116.00, "efecto": "Alcanza el Club Lenteros Unidos", "referencia": "Puente de la Amistad (escala a confirmar)", "fuente": DOC,
     "contraste": "La SEN citó «cota 116» el 12/10/2026, cuando empezaron las evacuaciones en San Rafael (Hoy, 13/10).", "confianza": S_},
    {"cota_m": 121.60, "efecto": "Bloquea el acceso a la escuela San Rafael", "referencia": "Puente de la Amistad (escala a confirmar)", "fuente": DOC,
     "contraste": "Itaipú midió 121,19 msnm el 16/10/2026, día de más familias fuera de sus casas.", "confianza": S_}])
K = [
    ("Población del distrito 325.819 hab.; área metropolitana > 500.000; densidad 2.348,99 hab./km²", "dato", "JRC GHSL (modelado) da 532.408 en la caja de la ciudad en 2025, que incluye parte del área metropolitana: mismo orden.", S_),
    ("La ciudad está delimitada por los ríos Paraná (este), Acaray (norte) y Monday (sur)", "dato", "La hidrografía oficial recortada a CDE tiene Río Paraná, Río Acaray y Río Monday.", C_),
    ("San Rafael y Che La Reina son zonas deprimidas atravesadas por el arroyo Acaraymí", "dato", "Las familias afectadas sí están registradas (380 y 130). El arroyo no figura con nombre en la hidrografía oficial ni en OSM; el modelo NASADEM no los ve deprimidos.", S_),
    ("Cotas de referencia 108,40 / 112,30 / 116,00 / 121,60 m (Puente de la Amistad)", "referencia", "116 coincide con la cota citada por la SEN el 12/10; 121,60 está cerca del pico de 121,19 del 16/10. Falta confirmar la escala.", S_),
    ("Itaipú abre el vertedero y libera más de 11,3 millones de litros por segundo (11.300 m³/s)", "dato", "La base no tiene caudales de Itaipú para contrastarlo.", I_),
    ("El vertido de Itaipú produce remanso sobre el arroyo Acaraymí e inunda la ciudad", "hipótesis", "Coherente con que el modelo de relleno desde el río no capte San Rafael; no probado.", S_),
    ("Sentinel-1 (SAR banda C) detecta agua como píxeles oscuros en VV/VH", "método", "Es lo que usa la base (VV < -16 dB y caída ≥ 3 dB).", C_),
    ("Umbral probabilístico con distribución Gamma y método de Otsu para separar agua y suelo urbano", "método", "La base usa un umbral fijo; Gamma/Otsu no está implementado ni evaluado en CDE.", I_),
    ("FIRMS VIIRS 375 m es ideal para micro-basurales e incendios de 1 a 5 ha", "dato", "En la base, FIRMS detecta quemas persistentes pero pierde muchas quemas chicas y cortas; «ideal» no se sostiene.", S_),
    ("FRP en MW; la FRE se obtiene integrando el FRP con la regla trapezoidal entre pasadas", "método", "Correcto como definición; la base guarda FRP por foco pero no calcula FRE.", C_),
    ("Sentinel-5P TROPOMI tiene píxeles de 3,5 × 5,5 km", "dato", "Coincide con la resolución usada en la base.", C_),
    ("El índice UVAI detecta el hollín del tráfico stop-and-go y el humo de basura", "dato", "En la base el índice sobre CDE dio negativo (−0,49) en los últimos 30 días y una celda de ~5 km no distingue el tránsito de una calle.", S_),
    ("Nodos LoRaWAN SX1262 + ESP32 (reposo 1,62 µA, sensibilidad −148 dBm), banda AU915, ChirpStack", "propuesta", "Especificación de diseño; sin red instalada. Banda y consumo a verificar con la hoja de datos y la CONATEL.", I_),
    ("Sensores JSN-SR04T (nivel del río) y Sensirion SPS30 (PM2.5)", "propuesta", "Sin sensores instalados: es justo la verdad de terreno que falta para quemas y crecidas.", I_),
    ("Ubicar gateways con COST 231 Hata y optimización bioinspirada (PSODE)", "propuesta", "Método de planificación; no evaluado en CDE.", I_),
    ("Filtro de Kalman extendido con modelo CTRV para fusionar satélite y sensores", "propuesta", "CTRV es un modelo de movimiento de vehículos; para nivel del río o PM2.5 haría falta otro modelo de estado.", S_),
    ("PINNs con ecuaciones de Saint-Venant para reemplazar HEC-RAS", "propuesta", "Requiere batimetría, caudales y un terreno sin edificios; la base no los tiene.", I_),
    ("Aprendizaje por refuerzo (DQN + SUMO) para «olas verdes» en semáforos", "propuesta", "No hay datos de tránsito ni de semáforos en la base.", I_),
    ("Accesibilidad 2SFCA (PySAL/GeoPandas) para la ciudad de 15 minutos", "propuesta", "Factible con edificios y calles de la base; faltan servicios (hospitales, bomberos) y población por manzana.", I_),
    ("La quema de basura está penada por la Ley 3956/09 (multas de 100 a 1.000 jornales) y la Ley 716", "norma", "Leyes conocidas de Paraguay; los montos no están verificados en esta sesión.", S_),
    ("La vigilancia con sensores debe cumplir protección de datos (LGPD de Brasil por la frontera; edge y anonimización)", "norma", "Principio de diseño; la base no tiene datos personales.", I_)]
DOC2 = "documento «Flujograma lógico y grafo causal» del dueño (2026-11-15), sin citas"
DOC3 = "anexo «BIDARA y misiones NASA» del dueño (2026-11-15), sin citas"
DOC4 = "documento «Curación 1990–2026 y activación del cerebro dual» del dueño (2026-11-15), sin citas"
DOC5 = "texto del dueño sobre ECOSTRESS y GEDI (2026-11-15), recibido vía otra sesión del equipo, sin citas"
DOC6 = "documento «Arquitectura: BIDARA Local Edge» del dueño (2026-11-15), recibido vía otra sesión del equipo, sin citas"
K2 = [
    ("El gemelo opera en un ciclo OODA de cuatro capas: adquisición, fusión, razonamiento predictivo y acción", "arquitectura", "Las tareas propuestas se ordenan por capa OODA; hoy solo la capa 1 (satélites) tiene datos en la base.", S_, DOC2),
    ("Sentinel-5P mide el índice UVAI para mapear la densidad del smog", "dato", "El UVAI sobre CDE dio −0,49 (sin humo) en los últimos 30 días y una celda de ~5 km no separa el smog de un barrio.", S_, DOC2),
    ("El 2SFCA cruza el censo 2022 con isócronas de tiempo de viaje", "método", "El censo 2022 no está en la base; la población disponible es GHSL (modelada, 2025).", I_, DOC2),
    ("Regla de acción: si la predicción supera 108,40 m, alerta de evacuación preventiva en San Rafael", "regla", "108,40 está en cotas_referencia (escala sin confirmar) y no hay predicción PINN ni sensor: hoy la regla no se puede disparar.", S_, DOC2),
    ("Regla de acción: atasco más pico de PM2.5 cambia la fase de los semáforos («olas verdes»)", "regla", "No hay datos de tránsito, semáforos ni PM2.5 de terreno en la base.", I_, DOC2),
    ("Regla de acción: foco VIIRS con FRP alto en zona residencial dispara fiscalización bajo la Ley 3956/09", "regla", "Los focos están en la base con barrio, pero un foco no prueba quema de basura: sirve para priorizar inspecciones, no para sancionar.", S_, DOC2),
    ("Regla de acción: un desierto de servicios (2SFCA) sugiere al POUT dónde construir plazas o dispensarios", "regla", "El POUT y los servicios públicos georreferenciados no están en la base.", I_, DOC2),
    ("La migración desde Brasil y la inversión inmobiliaria expanden la ciudad y crean desiertos de servicios", "hipótesis", "La luz nocturna crece +58 km²/década y la población modelada sube; la migración y los servicios no están medidos.", S_, DOC2),
    ("El smog es sinérgico: quema de basura + tráfico stop-and-go + inversión térmica del valle", "hipótesis", "El NO₂ de CDE es 52 % mayor que el de la región (medido); el criterio de aire estancado no discrimina y no hay PM2.5 de terreno.", S_, DOC2),
    ("El costo en salud del smog se valora con el Valor Estadístico de la Vida (VSL)", "método", "No hay datos de salud ni de exposición en la base.", I_, DOC2),
    ("BIDARA (proyecto PeTaL de la NASA) es un asistente de IA para diseño bioinspirado", "dato", "No está integrado al gemelo; su uso aquí es una propuesta.", S_, DOC3),
    ("Enrutamiento inspirado en el moho Physarum polycephalum para optimizar el flujo de vehículos y de agua", "propuesta", "Método con antecedentes en redes de transporte; no evaluado en CDE y sin aforos viales en la base.", I_, DOC3),
    ("Semáforos descentralizados en edge, inspirados en el sistema nervioso distribuido del pulpo", "propuesta", "Analogía de diseño; no hay red semafórica ni datos de tránsito en la base.", I_, DOC3),
    ("GPM IMERG mide la lluvia cada 30 minutos desde el espacio", "dato", "La resolución es de 30 min y ~0,1°, pero la versión temprana llega con horas de retraso: no es tiempo real. No está cargada: la lluvia de la base es NASA POWER (~0,5°).", S_, DOC3),
    ("Con GPM en la cuenca alta se puede alertar antes de que Itaipú abra el vertedero", "hipótesis", "Plausible por la distancia de la cuenca; requiere caudales de Itaipú y el modelo hidráulico (T5), que no existen.", I_, DOC3),
    ("SEDAC da densidad poblacional, flujos migratorios y vulnerabilidad en tiempo real", "dato", "SEDAC (GPWv4) publica por quinquenios hasta 2020: no es tiempo real. La base usa GHSL 2025 (modelado).", S_, DOC3),
    ("SMAP mide la humedad del suelo", "dato", "Correcto, pero con píxeles de 9 a 36 km: unos pocos para toda la ciudad. No está cargado en la base.", S_, DOC3),
    ("Suelo saturado (SMAP) más lluvia inminente (GPM) indica riesgo de deslizamiento en el Acaraymí", "hipótesis", "No hay registros de deslizamientos ni relieve fino; un píxel de SMAP es más grande que la cuenca del Acaraymí.", I_, DOC3),
    ("La memoria histórica 1990–2026 se arma con series de Landsat y MODIS (expansión urbana, vegetación, barrios)", "método", "Hecho en la base: series anuales y tendencias de calor, agua, lluvia y luz nocturna desde 1990 (Mann-Kendall y Sen).", C_, DOC4),
    ("Se digitalizan los historiales diarios del nivel del Paraná, del arroyo Acaraymí y del vertido de Itaipú", "dato", "No están en la base: solo hay eventos con cota de octubre 2026 (SEN, Itaipú, prensa). El Acaraymí no está mapeado.", I_, DOC4),
    ("Los censos históricos hasta el de 2022 (más de 325.000 habitantes) modelan migración, densidad y demanda", "dato", "Los censos no están en la base; la población es GHSL (modelada). La cifra del distrito coincide en orden con GHSL.", S_, DOC4),
    ("Los datos se centralizan en PostGIS con un mismo sistema de coordenadas", "método", "La base usa un único CRS (EPSG:4326) en GeoPackage y SQLite en el Orin; PostGIS no está en uso.", S_, DOC4),
    ("En tiempo real, sensores LoRaWAN reportan nivel de agua y PM2.5 cada minuto y el EKF fusiona todo", "propuesta", "No hay sensores ni fusión: hoy el gemelo trabaja con pasadas de satélite de días a semanas y con datos diarios.", I_, DOC4),
    ("Las PINN calculan la escorrentía en segundos y alertan a San Rafael antes de que suba el agua", "propuesta", "No hay modelo PINN y el modelo actual da 0 edificios en San Rafael: hoy esa alerta no es posible (T5, T14).", I_, DOC4),
    ("El foco VIIRS se cruza con el catastro municipal para emitir la orden de fiscalización", "propuesta", "Los focos tienen coordenadas y barrio OSM; el catastro municipal no está en la base y un foco no prueba quema de basura.", S_, DOC4),
    ("ECOSTRESS (en la ISS) mide la temperatura de superficie a ~70 m (píxel nativo ~38 × 69 m) y distingue una calle asfaltada, un techo comercial y un parque", "dato", "La base ya mide la isla de calor con Landsat C2 ST (térmico ~100 m, pasada a media mañana): +0,56 °C/década. ECOSTRESS suma mediciones a distintas horas del día, no mucho más detalle: a ~70 m un techo chico queda mezclado (la diferencia calle/techo a escala de lote no se sostiene; un parque grande sí). Que siga operando en 2026 no está verificado; no hay datos ECOSTRESS en la base.", S_, DOC5),
    ("Regla de acción: los mapas de microclima guían arbolado en corredores, techos fríos y centros de enfriamiento", "regla", "La base tiene el calor por cobertura (construido contra arbolado) y zonas calientes de verano con Landsat, no microclima por barrio a 70 m ni horario.", I_, DOC5),
    ("GEDI (lidar en la ISS) mide la altura del dosel y la estructura del bosque", "dato", "Correcto como definición del instrumento, pero son huellas de ~25 m en franjas separadas, no un mapa continuo; el producto en grilla (L4B) es de 1 km. La base no tiene datos GEDI.", S_, DOC5),
    ("Con GEDI el gemelo mide la biomasa perdida por expansión urbana y dicta políticas en tiempo real", "propuesta", "El muestreo disperso de GEDI no alcanza a nivel de barrio sin Landsat o Sentinel-2, y «tiempo real» no se sostiene. La base no tiene tabla de vegetación ni de biomasa.", S_, DOC5),
    ("La deforestación de las cuencas del Paraná y del Monday empeora las inundaciones", "hipótesis", "La base no tiene cobertura forestal por cuenca ni caudales para probarlo.", I_, DOC5),
    ("BIDARA corre local en un Jetson AGX Xavier de 32 GB", "arquitectura", "El Xavier se apagó el 2026-10-15. El equipo real es el Jetson AGX Orin de 61 GB, compartido: Qwen3.5-35B ocupa ~27 GB y, tras retirar Ollama y Kokoro, quedaban ~22 GB disponibles (medido el 2026-11-15).", S_, DOC6),
    ("BIDARA es un prompt de sistema publicado por la NASA (proyecto PeTaL)", "dato", "El prompt se publicó, pero no hay repositorio oficial ni licencia verificados, solo copias de terceros con muchas versiones modificadas. La base no tiene ese prompt.", S_, DOC6),
    ("Llama-3-8B o Mistral-Nemo-12B en Q4 ocupan menos de 8 GB y dejan lugar para tráfico e hidrología", "propuesta", "Los pesos pesan ~5 y ~7,5 GB, más la caché KV. Hoy entrarían en memoria (~22 GB libres), pero competirían con Qwen3.5, la visión y Qwen TTS, y el dueño pidió dejar solo esos modelos en el Orin.", S_, DOC6),
    ("RAG local con ChromaDB o Qdrant sobre los papers de PeTaL", "propuesta", "No hay ningún motor vectorial instalado en el Orin para esto y los papers tienen derechos de editorial sin licencia verificada.", I_, DOC6),
    ("Docker Compose con Ollama y Chroma sin exponer puertos", "propuesta", "El ejemplo publica 11434 y 8000 en todas las interfaces (falta «127.0.0.1:»), usa imágenes «:latest» sin versión fija ni veredicto de APOLO, y Ollama fue retirado del Orin. Verificado por otra sesión del equipo: Docker 29.9.3, Compose v5.7.0 y runtime nvidia (no por defecto).", S_, DOC6),
    ("El DQN de tráfico detecta congestión, dispara a BIDARA y este alimenta a SUMO", "propuesta", "No existe: es la tarea T6 (con T12 y T15), sin datos de tránsito. Es un plan, no algo que funcione hoy.", I_, DOC6)]
guardar_tabla("conocimiento_cde", [{"afirmacion": a, "tipo": t, "contraste_con_la_base": c, "confianza": cf, "fuente": DOC} for a, t, c, cf in K]
              + [{"afirmacion": a, "tipo": t, "contraste_con_la_base": c, "confianza": cf, "fuente": f} for a, t, c, cf, f in K2])
guardar_tabla("tareas_propuestas", [
    {"id": "T1", "tarea": "Red LoRaWAN de sensores de nivel (JSN-SR04T) en el puente peatonal de San Rafael y el arroyo Acaraymí", "capa_ooda": "observar",
     "estado": "propuesto", "dato_que_falta": "ubicación del Acaraymí y escala de las cotas", "como_se_valida": "lectura del sensor a 108,40 m vs inundación del puente"},
    {"id": "T2", "tarea": "Sensores de PM2.5 (SPS30) en Monday, Bella Vista, Acaray y Las Américas", "capa_ooda": "observar", "estado": "propuesto",
     "dato_que_falta": "permisos y energía", "como_se_valida": "picos de PM2.5 vs focos FIRMS y denuncias de quema"},
    {"id": "T3", "tarea": "Detección de agua con Sentinel-1 por umbral Gamma/Otsu", "capa_ooda": "observar", "estado": "propuesto",
     "dato_que_falta": "zonas de entrenamiento agua/suelo urbano", "como_se_valida": "comparar con el umbral fijo actual en la crecida de octubre 2026"},
    {"id": "T4", "tarea": "Fusión satélite + sensores con filtro de Kalman (modelo de estado hidrológico, no CTRV)", "capa_ooda": "orientar", "estado": "propuesto",
     "dato_que_falta": "series de sensores (T1, T2)", "como_se_valida": "error de pronóstico del nivel a 6–24 h"},
    {"id": "T5", "tarea": "Modelo de crecida con terreno sin techos (DTM) y remanso del Acaraymí (PINN o HEC-RAS)", "capa_ooda": "orientar", "estado": "propuesto",
     "dato_que_falta": "DTM, batimetría, caudales de Itaipú", "como_se_valida": "que capte San Rafael y Che la Reina (hoy 0 edificios)"},
    {"id": "T6", "tarea": "Semáforos con aprendizaje por refuerzo (DQN + SUMO)", "capa_ooda": "decidir", "estado": "propuesto",
     "dato_que_falta": "conteos de tránsito y red semafórica", "como_se_valida": "demora acumulada simulada vs actual"},
    {"id": "T7", "tarea": "Accesibilidad 2SFCA a hospitales y bomberos (ciudad de 15 minutos)", "capa_ooda": "decidir", "estado": "propuesto",
     "dato_que_falta": "servicios georreferenciados y población por manzana", "como_se_valida": "zonas sin cobertura vs reclamos vecinales"},
    {"id": "T8", "tarea": "Protocolo de datos: edge en el Orin, anonimización y transparencia (LGPD/fronteriza)", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "marco legal paraguayo de datos personales", "como_se_valida": "auditoría de que ningún dato personal sale del borde"},
    {"id": "T9", "tarea": "Cargar la lluvia GPM IMERG (30 min) de la cuenca alta y de CDE", "capa_ooda": "observar", "estado": "propuesto",
     "dato_que_falta": "ninguno: está en Earth Engine", "como_se_valida": "comparar con la lluvia NASA POWER y con la crecida de octubre 2026"},
    {"id": "T10", "tarea": "Cargar la humedad de suelo SMAP para CDE", "capa_ooda": "observar", "estado": "propuesto",
     "dato_que_falta": "ninguno: está en Earth Engine (píxel 9 km)", "como_se_valida": "humedad previa a las crecidas 2023–2026"},
    {"id": "T11", "tarea": "Comparar la población SEDAC (GPWv4) con GHSL para el 2SFCA", "capa_ooda": "orientar", "estado": "propuesto",
     "dato_que_falta": "censo 2022 por manzana", "como_se_valida": "diferencia por barrio entre las dos fuentes"},
    {"id": "T12", "tarea": "Probar BIDARA para un rediseño vial bioinspirado (Physarum)", "capa_ooda": "decidir", "estado": "propuesto",
     "dato_que_falta": "aforos viales y red semafórica", "como_se_valida": "demora simulada en SUMO frente a la red actual"},
    {"id": "T13", "tarea": "Protocolo común de las reglas de acción (umbral, responsable y fuente de dato) para las decisiones T14–T17", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "protocolos de la SEN y del municipio", "como_se_valida": "simulacro con la crecida de octubre 2026"},
    {"id": "T14", "tarea": "Decisión A: alerta temprana de evacuación en San Rafael antes de que suba el agua", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "depende de T1 (sensor de nivel) y T5 (modelo con remanso); hoy el modelo da 0 edificios en San Rafael",
     "como_se_valida": "la alerta se dispara antes de que el agua llegue al puente peatonal (108,40 m)"},
    {"id": "T15", "tarea": "Decisión B: semáforos sincronizados («olas verdes») para disipar atascos", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "depende de T6 (DQN + SUMO) y T2 (PM2.5); no hay datos de tránsito",
     "como_se_valida": "menos demora y menos PM2.5 en las esquinas intervenidas"},
    {"id": "T16", "tarea": "Decisión C: enviar fiscalizadores a las coordenadas de los focos de quema", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "protocolo municipal; los 95 sitios persistentes de FIRMS ya están en la base, pero un foco no prueba quema de basura",
     "como_se_valida": "porcentaje de sitios inspeccionados donde se confirma quema de basura"},
    {"id": "T17", "tarea": "Decisión D: sugerir al gobierno dónde construir un hospital o una plaza", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "depende de T7 (2SFCA) y T11 (población); faltan servicios georreferenciados",
     "como_se_valida": "la sugerencia cae en una zona con déficit de cobertura y reclamos vecinales"},
    {"id": "T18", "tarea": "Digitalizar las series diarias del nivel del Paraná, del arroyo Acaraymí y del vertido de Itaipú (1990–2026)", "capa_ooda": "observar", "estado": "propuesto",
     "dato_que_falta": "registros de Itaipú, ANNP o la Dirección de Meteorología e Hidrología; trazado del Acaraymí",
     "como_se_valida": "reproducir las cotas conocidas de octubre 2026 (116 m el 12/10, 121,19 m el 16/10)"},
    {"id": "T19", "tarea": "Cargar los censos históricos y el censo 2022 por barrio o manzana", "capa_ooda": "orientar", "estado": "propuesto",
     "dato_que_falta": "microdatos del INE por área censal", "como_se_valida": "comparar con la población modelada GHSL por barrio"},
    {"id": "T20", "tarea": "Centralizar la base en PostGIS (hoy GeoPackage + SQLite en el Orin)", "capa_ooda": "orientar", "estado": "propuesto",
     "dato_que_falta": "decisión de arquitectura del dueño", "como_se_valida": "las 25 consultas de la guía dan lo mismo en PostGIS y en SQLite"},
    {"id": "T21", "tarea": "Cruzar los focos VIIRS con el catastro municipal para identificar el lote", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "catastro municipal georreferenciado", "como_se_valida": "inspección en campo de una muestra de lotes señalados (base para T16)"},
    {"id": "T22", "tarea": "Decisión C2: recolección de basura orgánica en los 95 sitios de quema persistente (sitios_quema_persistente), con el humo como alerta (aerosoles_diarios_cde y focos VIIRS)", "capa_ooda": "actuar", "estado": "propuesto",
     "dato_que_falta": "circuito y frecuencia de recolección del municipio; depende de T16 y T21",
     "como_se_valida": "bajan los focos en esos sitios después de empezar la recolección"},
    {"id": "T23", "tarea": "Calor por hora del día con ECOSTRESS por barrio, contrastado con Landsat", "capa_ooda": "observar", "estado": "propuesto",
     "dato_que_falta": "verificar que ECOSTRESS siga operando y cubra CDE", "como_se_valida": "coincidencia con las zonas calientes de verano de Landsat (calor_verano)"},
    {"id": "T24", "tarea": "Pérdida de bosque y biomasa por cuenca (Paraná, Monday, Acaraymí) con GEDI L4A/L4B más Landsat o Sentinel-2", "capa_ooda": "orientar", "estado": "propuesto",
     "dato_que_falta": "límites de cuenca y trazado del Acaraymí", "como_se_valida": "comparar con la cobertura ESA WorldCover de la base"}])

# ---------- 8 · grafo causal ----------
NODOS = ["El Niño (ONI)", "lluvia en la cuenca", "operación de Itaipú", "nivel del Paraná", "mancha de crecida", "edificios expuestos", "familias evacuadas",
         "lluvia fuerte local", "escurrimiento en cauces", "baches", "crecimiento urbano", "pérdida de árboles", "isla de calor", "agua estancada", "dengue",
         "bajante", "incendios", "construcción en zona de crecida",
         # documento «Flujograma lógico y grafo causal» y anexo «BIDARA y misiones NASA» del dueño (2026-11-15)
         "apertura del vertedero de Itaipú", "remanso del arroyo Acaraymí", "inundación de San Rafael y Che la Reina",
         "falta de recolección de basura", "quema de basura", "diseño vial obsoleto", "tráfico stop-and-go", "NO₂ y hollín",
         "inversión térmica en el valle", "smog", "costos de salud (VSL)", "migración transfronteriza e inversión inmobiliaria",
         "desiertos de servicios", "volumen entrante al Paraná (PINN)", "suelo saturado (SMAP)", "deslizamientos en el Acaraymí",
         "enfermedades respiratorias", "deforestación de las cuencas"]
ARISTAS = [
    ("El Niño (ONI)", "lluvia en la cuenca", "correlación probada", "lluvia anual ρ = +0,39, p = 0,019 (Spearman, 1990–2025)"),
    ("El Niño (ONI)", "lluvia fuerte local", "correlación probada", "día más lluvioso ρ = +0,36, p = 0,030"),
    ("lluvia en la cuenca", "nivel del Paraná", "evidencia documental", "EFE/SEN: lluvias en el sur de Brasil y caudal del Iguazú"),
    ("operación de Itaipú", "nivel del Paraná", "evidencia documental", "Itaipú mide y advierte la cota; peso no cuantificado"),
    ("nivel del Paraná", "mancha de crecida", "modelo + observación", "NASADEM; radar 15/10 y Sentinel-2 26/10 con máximos del año"),
    ("mancha de crecida", "edificios expuestos", "modelo", f"{cre['niveles']['121.19']['edificios']} edificios a 121,19 m"),
    ("edificios expuestos", "familias evacuadas", "observación (el modelo subestima)", "1.210 familias registradas"),
    ("construcción en zona de crecida", "edificios expuestos", "observación", f"{nuevos} edificios nuevos 2018–2023 bajo 121 m"),
    ("crecimiento urbano", "construcción en zona de crecida", "hipótesis", "luz nocturna +58 km²/década; población modelada"),
    ("lluvia fuerte local", "escurrimiento en cauces", "física (modelo)", "D8 sobre NASADEM"),
    ("escurrimiento en cauces", "baches", "hipótesis", "sin reportes de baches para validar"),
    ("crecimiento urbano", "isla de calor", "hipótesis (ambas con tendencia significativa)", "relación causal no probada"),
    ("pérdida de árboles", "isla de calor", "hipótesis", "la LST arbolada sube menos que la urbana"),
    ("lluvia fuerte local", "agua estancada", "hipótesis", "sin datos"),
    ("agua estancada", "dengue", "hipótesis", "sin casos"),
    ("El Niño (ONI)", "bajante", "hipótesis", "mínimo 2021 con La Niña"),
    ("bajante", "incendios", "hipótesis", "FIRMS: 0 focos en noviembre 2026"),
    ("lluvia en la cuenca", "apertura del vertedero de Itaipú", "evidencia documental", "embalse lleno → vertido (documento del dueño); sin caudales en la base"),
    ("apertura del vertedero de Itaipú", "nivel del Paraná", "evidencia documental", "Itaipú midió 121,19 msnm el 16/10/2026"),
    ("nivel del Paraná", "remanso del arroyo Acaraymí", "hipótesis", "explicaría que el modelo no capte San Rafael; el arroyo no está mapeado"),
    ("remanso del arroyo Acaraymí", "inundación de San Rafael y Che la Reina", "hipótesis (inundación observada; mecanismo no probado)", "380 y 130 familias registradas; el modelo da 0 edificios"),
    ("lluvia fuerte local", "inundación de San Rafael y Che la Reina", "hipótesis", "sin pluviómetro local"),
    ("falta de recolección de basura", "quema de basura", "hipótesis", "sin datos de recolección"),
    ("quema de basura", "incendios", "hipótesis (focos medidos; atribución a basura no probada)", "1.474 focos FIRMS 2012–2026; 95 sitios persistentes"),
    ("diseño vial obsoleto", "tráfico stop-and-go", "hipótesis", "sin datos de tránsito"),
    ("tráfico stop-and-go", "NO₂ y hollín", "hipótesis (NO₂ medido)", "NO₂ CDE 14,6 vs región 9,6 µmol/m² (52 % más); sin conteos de tránsito"),
    ("quema de basura", "smog", "hipótesis", "UVAI sobre CDE −0,49 en 30 días"),
    ("NO₂ y hollín", "smog", "hipótesis", "sin PM2.5 de terreno"),
    ("inversión térmica en el valle", "smog", "hipótesis (el criterio de aire estancado no discrimina)", "viento vs NO₂ ρ = −0,092"),
    ("smog", "enfermedades respiratorias", "hipótesis", "sin datos de salud"),
    ("enfermedades respiratorias", "costos de salud (VSL)", "hipótesis", "sin datos de salud ni de costos"),
    ("crecimiento urbano", "tráfico stop-and-go", "hipótesis", "luz nocturna +58 km²/década; sin conteos de tránsito"),
    ("deforestación de las cuencas", "escurrimiento en cauces", "hipótesis", "sin cobertura forestal por cuenca (T24)"),
    ("deforestación de las cuencas", "nivel del Paraná", "hipótesis", "sin caudales ni cobertura por cuenca"),
    ("migración transfronteriza e inversión inmobiliaria", "crecimiento urbano", "hipótesis", "luz nocturna +58 km²/década; migración no medida"),
    ("crecimiento urbano", "desiertos de servicios", "hipótesis", "faltan servicios georreferenciados y población por manzana"),
    ("lluvia en la cuenca", "volumen entrante al Paraná (PINN)", "hipótesis (propuesta GPM IMERG + PINN)", "GPM no está cargado (T9); no hay modelo PINN (T5)"),
    ("volumen entrante al Paraná (PINN)", "nivel del Paraná", "hipótesis", "requiere caudales de Itaipú"),
    ("suelo saturado (SMAP)", "escurrimiento en cauces", "hipótesis (propuesta SMAP)", "SMAP no está cargado (T10); píxel de 9 km"),
    ("suelo saturado (SMAP)", "deslizamientos en el Acaraymí", "hipótesis", "sin registros de deslizamientos")]
assert all(a in NODOS and b in NODOS for a, b, _, _ in ARISTAS), "arista con nodo inexistente"
guardar_tabla("grafo_nodos", [{"id": i + 1, "nodo": n_} for i, n_ in enumerate(NODOS)])
guardar_tabla("grafo_aristas", [{"desde": a, "hacia": b, "estado": e_, "evidencia": ev} for a, b, e_, ev in ARISTAS])

# ---------- 9 · contexto compacto para el chat de StrateIA Dual Brain ----------
ctx = {"ciudad": "Ciudad del Este, Paraguay", "fecha": HOY, "crs": "EPSG:4326",
       "capas": sorted(p.stem for p in (OUT / "capas").glob("*.geojson")),
       "problemas": [{k: p[k] for k in ("id", "problema", "sector", "indicadores", "confianza", "causas", "datos_faltantes", "intervenciones", "evidencia")} for p in PROB],
       "grafo": [{"desde": a, "hacia": b, "estado": e_} for a, b, e_, _ in ARISTAS],
       "tendencias_significativas": [f'{t["variable"]} · {t["region"]}: {t["sen_por_decada"]:+g} {t["unidad"]}/década (p {t["mk_p"]})'
                                     for t in T["tendencias"] if t["significativa_95"]],
       "limites": ["los satélites no ven personas, nacionalidad ni seguridad", "la lluvia POWER es modelo (~0,5°)", "el agua 2022–2026 usa otro método",
                   "el riesgo de baches es modelado", "no hay casos de dengue"]}
json.dump(ctx, open(OUT / "contexto_dualbrain.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("contexto_dualbrain.json ·", len(json.dumps(ctx, ensure_ascii=False)) // 1024, "KB · edificios nuevos bajo 121:", nuevos, dict(sorted(nuevos_riesgo.items())))
