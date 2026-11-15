"""AI version of the curated database: cde_ia.sqlite (flat tables + dictionary + quality + query guide).
Meant for the StrateIA Dual Brain chat (node servidor.js cde_ia.sqlite) and any LLM that reads the schema and runs SELECT.
No binary geometries: each feature carries the lon/lat of its centre; small layers also carry their GeoJSON for drawing.
Usage: python construir_ia.py  (Python 3.12, shapely)."""
import json
import sqlite3
from pathlib import Path

from shapely.geometry import shape

import sys

D = Path(__file__).parent
SAL = D / (sys.argv[1] if len(sys.argv) > 1 else "cde_ia.sqlite")  # alternative name if the database is open in the chat
if SAL.exists():
    SAL.unlink()
con = sqlite3.connect(SAL)

TABLAS = {  # table: (description, source, period, resolution, quality)
    "edificios": ("Cada edificio de Ciudad del Este con su altura, barrio, cota del río que lo alcanza, calor del suelo y año de aparición. «Construcción nueva» = anio_aparicion entre 2018 y 2023; 2016 es la línea de base de Open Buildings Temporal (ya existía), no un año de construcción.", "OSM + Google Open Buildings; NASADEM; Landsat", "base 2026; aparición 2016–2023", "edificio", "los edificios alcanzados por la crecida NO dependen de la altura: dependen de cota_alcance_msnm (terreno NASADEM, modelo que subestima familias); altura = estimación satelital, null = sin dato"),
    "calles": ("Tramos de calle (cada fila es un tramo de ~95 m, no una calle entera: decir «tramos», no «calles») con superficie, tipo, barrio y riesgo de baches por lluvia. «Vías principales» (indicador de P3) = las calles con nombre que suman más km de riesgo alto, de cualquier tipo (avenida, ruta o calle urbana), sin los tramos «S/N»; para avenidas y rutas solamente, filtrar por tipo.", "capa vial municipal (origen a confirmar); NASADEM", "s/d", "tramo", "riesgo modelado, no baches observados"),
    "cauces": ("Líneas por donde corre el agua de lluvia, con el área que drena.", "NASA NASADEM 30 m", "2000", "30 m", "no incluye desagües construidos"),
    "crecida_rio": ("Mancha de crecida del río Paraná para cada cota del río.", "NASADEM; JRC", "modelo", "30 m", "modelo sin defensas; subestima familias"),
    "valle": ("Valle bajo de arroyo con su modelo de anegamiento por lluvia.", "NASADEM ∩ Copernicus GLO-30", "modelo", "30 m", "susceptibilidad, no observado"),
    "agua_anual": ("Polígonos de agua de cada año, permanente o estacional.", "JRC GSW (Landsat) 1990–2021; Sentinel-2 2022–2026", "1990–2026", "30 m / 10 m", "2022–2026 con otro método"),
    "agua_radar_20261015": ("Agua nueva vista por radar después de la crecida de octubre 2026.", "Copernicus Sentinel-1", "03/10 vs 15/10/2026", "10 m", "plausible < 120 m"),
    "calor_verano": ("Zonas de la ciudad con el suelo más caliente en verano.", "Landsat 8/9", "dic–feb 2023–2026", "100 m", "temperatura del suelo, no del aire"),
    "cobertura": ("Zonas urbanas y arboladas.", "ESA WorldCover", "2021", "10 m", "vectorizado a 40 m"),
    "zonas_analisis": ("Recortes usados por los indicadores.", "propio", "-", "-", "celda POWER aproximada"),
    "problemas": ("Registro curado de problemas con indicadores, confianza, causas, datos faltantes e intervenciones.", "curado", "2026-11", "-", "confianza marcada en cada fila"),
    "barrios_osm": ("Barrios de Ciudad del Este con nombre y límite.", "OpenStreetMap (ODbL)", "2026-11", "vector", "cobertura a verificar con la Municipalidad"),
    "no2_ultimos_30_dias": ("NO₂ (tránsito y combustión) por celda de ~3,5 km, último mes: valores por píxel para ver zonas. Para el promedio de la ciudad usar aire_actual.", "Copernicus Sentinel-5P", "15/10–14/11/2026", "~3,5 km", "muestra zonas, no calles"),
    "focos_calor_region": ("Focos de fuego en la región (~130 km), últimos 5 días.", "NASA FIRMS", "nov 2026", "375 m", "quemas chicas pueden no verse"),
    "turbidez_temporada_seca": ("Turbidez del aire en temporada seca por celda: zonas más cargadas año tras año.", "NASA MODIS MAIAC", "jul–sep 2001–2026", "1 km", "humo + tránsito + polvo; sobre agua = error"),
    "focos_historicos_cde": ("Focos de fuego dentro de la ciudad desde 2012, con fecha y barrio.", "NASA FIRMS VIIRS", "2012–2026", "375 m", "un foco no prueba quema de basura"),
    "hidrografia_oficial": ("Ríos y arroyos oficiales con nombre (Paraná, Acaray, Monday, Cedroty, Guayaki, Saltito, lago Itaipú).", "capa oficial (proyecto QGIS)", "s/d", "vector", "el arroyo Acaraymí no figura"),
    "validacion_crecida_barrios": ("Barrios con familias afectadas en oct-2026 frente a lo que alcanza el modelo de crecida: dice qué barrios capta y cuáles no.", "QZ (registro oficial) + modelo NASADEM", "oct 2026", "barrio", "el modelo no capta San Rafael ni Che la Reina"),
    "cotas_referencia": ("Cotas locales del río y su efecto en San Rafael (108,40 puente peatonal … 121,60 escuela).", "documento del dueño", "-", "cota", "escala a confirmar con SEN o Itaipú"),
    "conocimiento_cde": ("Afirmaciones de los documentos del dueño (base de conocimientos, flujograma OODA y grafo causal, anexo BIDARA/GPM/SEDAC/SMAP, reglas de acción, curación 1990–2026, cerebro dual en tiempo real, ECOSTRESS y GEDI), cada una contrastada con los datos y con su confianza.", "documento del dueño", "2026-11-15", "-", "varias no verificadas o contradichas"),
    "tareas_propuestas": ("Tareas propuestas T1–T24 para el gemelo (sensores, fusión, modelos, GPM, SMAP, SEDAC, BIDARA, decisiones A–D: alerta en San Rafael, olas verdes, fiscalización de quemas, dónde construir; recolección de basura orgánica; series diarias del Paraná e Itaipú, censos, PostGIS, catastro; ECOSTRESS y GEDI), con el dato que falta y cómo validarlas.", "documento del dueño", "2026-11-15", "-", "estado propuesto"),
    "sitios_quema_persistente": ("Lugares con focos en 3 o más años: posibles basurales o quemas habituales.", "NASA FIRMS VIIRS", "2012–2026", "375 m", "validar en terreno"),
}
COLUMNAS = {
    "cota_alcance_msnm": ("cota del río (m sobre el nivel del mar) a la que el agua alcanza el elemento; null = no se inunda hasta 128 m; sale del terreno (NASADEM), no de la altura del edificio", "msnm"),
    "lst_verano_c": ("temperatura del suelo y techos en verano (mediana dic–feb)", "°C"), "anio_aparicion": ("primer año en que el edificio aparece en Open Buildings", "año"),
    "altura_m": ("altura del edificio estimada por satélite (Open Buildings 2.5D / 3D-GloBFP); no se usa para la crecida", "m"), "riesgo_baches": ("riesgo de baches por lluvia: alto, medio o bajo", ""), "cauce_ha": ("área que drena el cauce que cruza la calle", "ha"),
    "bajo_cota_118": ("1 si la calle queda bajo la cota segura de la SEN (118 m)", "0/1"), "largo_km": ("largo del tramo", "km"),
    "area_aguas_arriba_ha": ("área que drena hacia ese punto", "ha"), "cota_msnm": ("cota del río", "msnm"), "tierra_ha": ("tierra inundada", "ha"),
    "edificios_alcanzados": ("edificios alcanzados por la crecida", "edificios"), "sen_por_decada": ("cambio por década (pendiente de Sen)", "unidad de la variable"),
    "mk_p": ("valor p de Mann-Kendall; < 0,05 = tendencia significativa", ""), "significativa_95": ("1 si la tendencia es significativa al 95 %", "0/1"),
    "agua_ha": ("superficie de agua", "ha"), "observado_pct": ("porcentaje de la zona sin nubes", "%"), "usar": ("1 si el dato es confiable para series", "0/1"),
    "no2_umol_m2": ("NO₂ troposférico", "µmol/m²"), "frp_mw": ("potencia radiativa del fuego", "MW"), "aod_media_jul_sep": ("turbidez del aire (espesor óptico de aerosoles a 470 nm)", "adimensional"),
    "anios_en_20pct_mas_turbio": ("años en que la celda estuvo entre el 20 % más turbio de la ciudad", "años"), "confianza": ("nivel de evidencia: CONFIRMADO, SOSPECHOSO o INCIERTO", ""),
    "lon": ("longitud del centro del elemento", "grados"), "lat": ("latitud del centro del elemento", "grados"),
    "fila_id": ("número de fila; une con _geometrias(tabla, fila_id) para dibujar", ""),
    "barrio": ("barrio de OpenStreetMap que contiene el elemento", ""), "fuente": ("de dónde sale el dato", ""), "calidad": ("advertencia de uso del dato", ""),
}
CHICAS = {"crecida_rio", "valle", "calor_verano", "zonas_analisis", "problemas", "barrios_osm", "no2_ultimos_30_dias", "sitios_quema_persistente", "agua_radar_20261015"}


# Confidence level (owner's anti-bias protocol: three categories, no numeric scores)
CONF, SOSP, INC = "[CONFIRMADO CON EVIDENCIA]", "[SOSPECHOSO - REQUIERE VALIDACIÓN]", "[INCIERTO]"
CONF_TABLA = {  # table: (level, reason)
    "edificios": (SOSP, "huella de OSM; altura estimada por satélite; cota_alcance_msnm es un modelo de terreno que subestima familias (el conteo por crecida no usa la altura)"),
    "calles": (SOSP, "riesgo de baches modelado, sin reportes municipales"), "cauces": (CONF, "derivado del terreno NASADEM; no incluye desagües"),
    "crecida_rio": (SOSP, "modelo sin defensas ni drenaje; el evento de 2026 sí ocurrió"), "valle": (INC, "susceptibilidad topográfica; el radar no lo vio inundado"),
    "agua_anual": (CONF, "JRC 1990–2021 medido; 2022–2026 con método propio (ver fila)"), "agua_radar_20261015": (SOSP, "cambio de radar; ver clase por fila"),
    "calor_verano": (CONF, "medido por Landsat; es suelo y techos, no aire"), "cobertura": (CONF, "ESA WorldCover"),
    "zonas_analisis": (CONF, "recortes de análisis; la celda POWER es aproximada (ver fila)"), "barrios_osm": (SOSP, "OpenStreetMap, no oficial"),
    "no2_ultimos_30_dias": (CONF, "medido por Sentinel-5P; celda de ~3,5 km"), "focos_calor_region": (CONF, "hubo foco; no prueba que sea basura"),
    "focos_historicos_cde": (CONF, "hubo foco; no prueba que sea basura; quemas chicas no se ven"), "sitios_quema_persistente": (SOSP, "posible basural u olería: validar en terreno"),
    "turbidez_temporada_seca": (CONF, "medido por MODIS MAIAC; celdas sobre agua son error (ver fila)"), "tendencias": (CONF, "pruebas estadísticas; ver fila"),
    "series_anuales": (CONF, "valores medidos o de modelo según la fuente"), "relacion_oni": (CONF, "correlación de Spearman; ver fila"),
    "eventos_crecida_2026": (CONF, "prensa que cita a SEN, Itaipú o la Municipalidad; ver fila"), "fuentes": (CONF, "catálogo"),
    "serie_sentinel1": (CONF, "ver columna usar por fila"), "serie_sentinel2": (CONF, "ver columna usar por fila"),
    "agua_anual_sentinel2_ha": (SOSP, "método propio; difiere de JRC en el reparto permanente/estacional"), "pasadas_copernicus": (CONF, "metadatos de pasadas"),
    "grafo_nodos": (CONF, "nodos del grafo"), "grafo_aristas": (CONF, "ver estado por fila"), "problemas": (CONF, "cada problema trae su propia confianza"),
    "aire_actual": (CONF, "medido"), "aire_anual": (CONF, "medido"), "aire_diario": (CONF, "medido; viento POWER es modelo"),
    "aerosoles_diarios_cde": (CONF, "medido"), "no2_diario_cde": (CONF, "medido"), "estancamiento_aire": (SOSP, "criterio propio que marca demasiados días"),
    "turbidez_anual": (CONF, "medido"), "turbidez_por_barrio": (SOSP, "mezcla humo, tránsito y polvo; barrios OSM"),
    "quemas_por_anio": (CONF, "conteo FIRMS"), "quemas_por_mes": (CONF, "conteo FIRMS"), "quemas_por_dia_semana": (CONF, "conteo FIRMS; pasadas fijas"),
    "quemas_dia_noche": (CONF, "conteo FIRMS"), "quemas_fechas_pico": (CONF, "conteo FIRMS"), "quemas_por_barrio": (SOSP, "conteo FIRMS confirmado; barrios y áreas de OSM"),
    "hidrografia_oficial": (CONF, "capa oficial del proyecto QGIS; el arroyo Acaraymí no figura con nombre"),
    "validacion_crecida_barrios": (CONF, "comparación observada: registro oficial de familias vs modelo; ver resultado por fila"),
    "cotas_referencia": (SOSP, "cotas locales del documento del dueño; escala sin confirmar con SEN o Itaipú"),
    "conocimiento_cde": (SOSP, "afirmaciones del documento del dueño contrastadas con la base; ver confianza por fila"),
    "tareas_propuestas": (INC, "tareas en estado propuesto: no son datos"),
}


def conf_fila(tabla, p):
    """Per-row confidence where it varies within the table; otherwise the table's own."""
    if tabla == "tendencias":
        return CONF if p.get("significativa_95") else INC
    if tabla == "relacion_oni":
        return CONF if (p.get("p") or 1) < 0.05 else INC
    if tabla == "agua_radar_20261015":
        return {"plausible": SOSP}.get(p.get("clase"), INC)
    if tabla in ("serie_sentinel1", "serie_sentinel2"):
        return CONF if p.get("usar") else INC
    if tabla == "agua_anual":
        return CONF if (p.get("anio") or 0) <= 2021 else SOSP
    if tabla == "turbidez_temporada_seca":
        return INC if p.get("sobre_agua") else CONF
    if tabla == "zonas_analisis":
        return INC if p.get("zona") == "celda_power_aprox" else CONF
    if tabla == "eventos_crecida_2026":
        return SOSP if "sin atribución" in (p.get("fuente") or "") else CONF
    if tabla == "grafo_aristas":
        e = p.get("estado") or ""
        return INC if e.startswith("hipótesis") else SOSP if e in ("evidencia documental", "modelo") else CONF
    return CONF_TABLA.get(tabla, (INC, ""))[0]


def tipo(v):
    return "REAL" if isinstance(v, float) else "INTEGER" if isinstance(v, (int, bool)) else "TEXT"


def cargar(nombre, filas):
    if not filas:
        return
    if nombre not in ("problemas", "conocimiento_cde", "cotas_referencia", "validacion_crecida_barrios"):  # these carry their own curated confidence
        for f in filas:
            f["confianza"] = conf_fila(nombre, f)
    vistos, unicas = set(), []
    for f in filas:  # drop rows repeated in the source (same data except fila_id)
        k = json.dumps({a: b for a, b in f.items() if a != "fila_id"}, sort_keys=True, ensure_ascii=False, default=str)
        if k not in vistos:
            vistos.add(k); unicas.append(f)
    if len(unicas) < len(filas):
        print(f"  {nombre}: {len(filas) - len(unicas)} duplicate rows removed")
    filas[:] = unicas
    cols = list(dict.fromkeys(k for f in filas for k in f))
    muestra = {c: next((f[c] for f in filas if f.get(c) is not None), "") for c in cols}
    con.execute(f'CREATE TABLE "{nombre}" (' + ", ".join(f'"{c}" {tipo(muestra[c])}' for c in cols) + ")")
    val = lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else int(v) if isinstance(v, bool) else v
    con.executemany(f'INSERT INTO "{nombre}" VALUES (' + ",".join("?" * len(cols)) + ")", [[val(f.get(c)) for c in cols] for f in filas])
    return cols


registro, geometrias = [], []  # geometries go separately: the schema the LLM sees must not show polygons as "values"
for capa in sorted((D / "capas").glob("*.geojson")):
    fc = json.load(open(capa, encoding="utf-8"))
    filas = []
    for k, f in enumerate(fc["features"]):
        p = {"fila_id": k, **f["properties"]}
        if f.get("geometry"):
            g = shape(f["geometry"]); c = g.representative_point() if g.geom_type.endswith("Polygon") else g.centroid
            p["lon"], p["lat"] = round(c.x, 6), round(c.y, 6)
            if capa.stem in CHICAS:
                geometrias.append((capa.stem, k, json.dumps(f["geometry"], separators=(",", ":"))))
        filas.append(p)
    cols = cargar(capa.stem, filas)
    registro.append((capa.stem, "capa", len(filas), cols))
    print("layer", capa.stem, len(filas))
for t in sorted((D / "tablas").glob("*.json")):
    filas = json.load(open(t, encoding="utf-8"))
    if isinstance(filas, dict):
        filas = filas.get("serie", [])
    if filas and isinstance(filas[0], dict):
        cols = cargar(t.stem, filas)
        registro.append((t.stem, "tabla", len(filas), cols))
        print("table", t.stem, len(filas))

con.execute("CREATE TABLE _geometrias (tabla TEXT, fila_id INTEGER, geojson TEXT)")
con.executemany("INSERT INTO _geometrias VALUES (?,?,?)", geometrias)
def periodo_real(n, cols):
    """Period covered by the table's data, read from its anio or fecha column (so the model does not search out of range)."""
    for c in ("anio", "fecha"):
        if c in (cols or []):
            a, b = con.execute(f'SELECT MIN("{c}"), MAX("{c}") FROM "{n}"').fetchone()
            if a is not None:
                return f" Período de los datos: {a} a {b}."
    return ""


TABLAS = {n: (v[0] + periodo_real(n, next((c for nn, _, _, c in registro if nn == n), None)),) + v[1:] for n, v in TABLAS.items()}
for n, _, _, cols in registro:
    if n not in TABLAS:
        TABLAS[n] = ("Tabla de análisis; ver columnas fuente y calidad en cada fila." + periodo_real(n, cols), "", "", "", "")
con.execute("CREATE TABLE _diccionario_tablas (tabla TEXT, tipo TEXT, descripcion TEXT, fuente TEXT, periodo TEXT, resolucion TEXT, calidad TEXT, filas INTEGER, "
            "confianza TEXT, motivo_confianza TEXT)")
con.executemany("INSERT INTO _diccionario_tablas VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(n, tp, *(TABLAS.get(n) or ("tabla de análisis; ver columnas fuente y calidad en cada fila", "", "", "", "")), k,
                  *CONF_TABLA.get(n, (INC, "sin nivel asignado"))) for n, tp, k, _ in registro])
con.execute("CREATE TABLE _diccionario_columnas (tabla TEXT, columna TEXT, descripcion TEXT, unidad TEXT)")
con.executemany("INSERT INTO _diccionario_columnas VALUES (?,?,?,?)",
                [(n, c, *(COLUMNAS.get(c) or ("", ""))) for n, _, _, cols in registro for c in (cols or [])])
con.execute("CREATE TABLE _guia_consultas (pregunta TEXT, sql TEXT, grafico TEXT)")
con.executemany("INSERT INTO _guia_consultas VALUES (?,?,?)", [
    ("¿Cuántos edificios alcanza el río a 121,19 m y en qué barrios?", "SELECT barrio, COUNT(*) AS edificios FROM edificios WHERE cota_alcance_msnm <= 121.19 GROUP BY barrio ORDER BY edificios DESC", "barras"),
    ("¿Cuántos edificios nuevos (2018–2023) hay en zona de crecida?", "SELECT anio_aparicion, COUNT(*) FROM edificios WHERE cota_alcance_msnm <= 121.19 AND anio_aparicion BETWEEN 2018 AND 2023 GROUP BY anio_aparicion", "barras por año"),
    ("¿Cuántas construcciones nuevas se detectaron y en qué barrios? («nuevo» = aparece entre 2018 y 2023)",
     "SELECT barrio, COUNT(*) AS nuevas, MIN(confianza) AS confianza FROM edificios WHERE anio_aparicion BETWEEN 2018 AND 2023 GROUP BY barrio ORDER BY nuevas DESC", "barras"),
    ("¿Cuántos tramos de calle tienen riesgo alto de baches? (cada fila es un tramo, no una calle)",
     "SELECT COUNT(*) AS tramos, ROUND(SUM(largo_km),1) AS km, MIN(confianza) AS confianza FROM calles WHERE riesgo_baches='alto'", "número"),
    ("¿Qué calles tienen más kilómetros de tramos con riesgo de baches?", "SELECT nombre, ROUND(SUM(largo_km),2) AS km FROM calles WHERE riesgo_baches='alto' AND nombre IS NOT NULL AND nombre <> 'S/N' GROUP BY nombre ORDER BY km DESC LIMIT 10", "barras horizontales"),
    ("¿Cómo cambió el agua permanente de la ribera?", "SELECT anio, valor FROM series_anuales WHERE variable='Permanent surface water' AND region LIKE 'Riverbank%' ORDER BY anio", "línea"),
    ("¿Qué tendencias son significativas?", "SELECT variable, region, sen_por_decada, unidad, mk_p FROM tendencias WHERE significativa_95 = 1", "tabla"),
    ("¿Qué pasó en la crecida de octubre 2026?", "SELECT fecha, hecho, fuente FROM eventos_crecida_2026 ORDER BY fecha", "línea de tiempo"),
    ("¿En qué meses se quema más?", "SELECT nombre, focos_total FROM quemas_por_mes ORDER BY mes", "barras por mes"),
    ("¿Qué barrios tienen más focos de quema?", "SELECT barrio, focos, anios_distintos FROM quemas_por_barrio ORDER BY focos DESC LIMIT 10", "barras"),
    ("¿Cómo varió el humo y el NO₂ por año?", "SELECT anio, dias_humo_ai_mayor_1, no2_cde_media, aod_cde FROM aire_anual WHERE anio >= 2019 ORDER BY anio", "línea doble"),
    ("¿Cuánta agua vio el radar en 2026?", "SELECT fecha, agua_ha FROM serie_sentinel1 WHERE zona='ribera_valle_parana' AND usar=1 AND fecha >= '2026' ORDER BY fecha", "línea"),
    ("¿Qué problemas tiene la ciudad y qué tan seguros estamos?", "SELECT id, problema, confianza FROM problemas ORDER BY id", "tabla"),
    # Questions that failed in the chat (chat report, 2026-11-15)
    ("¿Cuánta agua hubo en Ciudad del Este en un año entre 1990 y 2021? (sumar permanente + estacional de UNA región; no sumar regiones)",
     "SELECT anio, region, SUM(valor) AS agua_total_ha, MIN(confianza) AS confianza FROM series_anuales WHERE variable IN ('Permanent surface water','Seasonal surface water') "
     "AND region = 'Whole city box' AND anio = 2015 GROUP BY anio, region", "número"),
    ("¿Cuánta agua hubo en 2023 (o cualquier año 2022–2026)? (zona 'cde' = toda la ciudad; 'ribera_valle_parana' y 'valle' están DENTRO de 'cde': nunca sumar zonas)",
     "SELECT anio, zona, permanente_ha, estacional_ha, permanente_ha + estacional_ha AS agua_total_ha, confianza FROM agua_anual_sentinel2_ha WHERE anio = 2023 AND zona = 'cde'", "número"),
    ("¿Cómo cambió el agua de toda la ciudad de 1990 a 2026? (JRC hasta 2021, Sentinel-2 desde 2022)",
     "SELECT anio, SUM(valor) AS agua_total_ha, 'JRC Landsat' AS fuente, MIN(confianza) AS confianza FROM series_anuales WHERE region = 'Whole city box' "
     "AND variable IN ('Permanent surface water','Seasonal surface water') GROUP BY anio UNION ALL SELECT anio, permanente_ha + estacional_ha, 'Sentinel-2', confianza "
     "FROM agua_anual_sentinel2_ha WHERE zona = 'cde' AND anio >= 2022 ORDER BY anio", "línea (marcar el cambio de fuente en 2022)"),
    ("¿Cuál es la tendencia de la isla de calor? (filtrar solo por variable; su región es 'Built-up vs tree cover')",
     "SELECT variable, region, sen_por_decada, unidad, sen_ic95_decada, mk_p, significativa_95, confianza FROM tendencias WHERE variable LIKE '%heat island%'", "número + IC"),
    ("¿Cuál es la tendencia de una variable? (filtrar solo por variable con LIKE; no adivinar la región)",
     "SELECT variable, region, sen_por_decada, unidad, mk_p, significativa_95, confianza FROM tendencias WHERE variable LIKE '%rainfall%'", "tabla"),
    ("¿Cómo está o cómo estuvo el aire / el NO₂ el último mes? (promedio de la ciudad vs mismo período de 2025)",
     "SELECT variable, periodo, cde, region_130km, confianza FROM aire_actual ORDER BY variable, periodo", "barras agrupadas"),
    ("¿El modelo de crecida coincide con los barrios que se inundaron? (registro oficial vs modelo)",
     "SELECT barrio_registro, familias_afectadas, edificios_modelo_121, resultado, confianza FROM validacion_crecida_barrios ORDER BY familias_afectadas DESC", "tabla"),
    ("¿A qué cota se inunda San Rafael? (cotas de referencia locales; el modelo no capta San Rafael)",
     "SELECT cota_m, efecto, contraste, confianza FROM cotas_referencia ORDER BY cota_m", "escala de cotas"),
    ("¿Qué afirmaciones del documento de conocimiento están confirmadas por los datos?",
     "SELECT afirmacion, tipo, contraste_con_la_base, confianza FROM conocimiento_cde ORDER BY confianza", "tabla"),
    ("¿Qué tareas están propuestas para el gemelo y qué dato les falta?",
     "SELECT id, tarea, capa_ooda, estado, dato_que_falta, como_se_valida FROM tareas_propuestas", "tabla"),
    ("¿Qué tan confiable es la base? (resumen de la auditoría de calidad)",
     "SELECT indicador, valor FROM _calidad_resumen", "tabla"),
    ("¿Qué tan confiable es cada tabla? (porcentaje de filas por etiqueta de confianza y hallazgos)",
     "SELECT tabla, filas, pct_confirmado, pct_sospechoso, pct_incierto, hallazgos FROM _calidad_tablas ORDER BY filas DESC", "barras apiladas"),
    ("¿Cómo varió el NO₂ día a día? (2019–2026)",
     "SELECT fecha, no2, viento_ms, confianza FROM aire_diario WHERE no2 IS NOT NULL AND fecha >= '2026-10-01' ORDER BY fecha", "línea"),
])
con.execute("CREATE TABLE _acerca (tema TEXT, texto TEXT)")  # the first thing the LLM reads: what the whole database is about
con.executemany("INSERT INTO _acerca VALUES (?,?)", [
    ("área", "Toda la base es de Ciudad del Este (Alto Paraná, Paraguay), frontera con Foz do Iguaçu (Brasil) y Puerto Iguazú (Argentina), sobre el río Paraná. "
             "Caja de la ciudad: lon −54,740 a −54,594; lat −25,600 a −25,387. Salvo que una columna zona o region diga otra cosa (ribera, región de 130 km, "
             "celda NASA POWER, Niño 3.4 en el Pacífico), cada fila se refiere a Ciudad del Este."),
    ("período y fuentes", "Datos de 1990 a noviembre de 2026 (agua 1990–2026, lluvia 1990–2026, aire 2001–2026, focos de fuego 2012–2026, crecida de octubre 2026). "
                          "Fuentes: NASA (GPM IMERG, POWER, Landsat, NASADEM, Black Marble, FIRMS, MODIS MAIAC), ESA/Copernicus (Sentinel-1, Sentinel-2, Sentinel-5P, "
                          "GLO-30, WorldCover), JRC (agua, población modelada), NOAA (ONI), OpenStreetMap (calles, edificios, barrios) y SEN/Municipalidad/Itaipú vía prensa."),
    ("cómo responder", "Cada fila trae confianza: [CONFIRMADO CON EVIDENCIA], [SOSPECHOSO - REQUIERE VALIDACIÓN] o [INCIERTO]; decirla con la cifra. "
                       "Al unir tablas (UNION o JOIN), incluir la columna confianza de cada parte. Unidades en _diccionario_columnas; límites en _limites. "
                       "Coordenadas en EPSG:4326 (lon, lat). Base curada el 2026-11-15 para el gemelo digital de Ciudad del Este (NASA Space Apps 2026)."),
])
con.execute("CREATE TABLE _limites (tema TEXT, limite TEXT)")
con.executemany("INSERT INTO _limites VALUES (?,?)", [
    ("personas", "Los satélites no ven personas, nacionalidad ni seguridad. La población es modelada (JRC)."),
    ("crecida", "El modelo de crecida subestima familias: un edificio puede tener varias y los asentamientos informales no están en el mapa."),
    ("baches", "El riesgo de baches es un modelo; no hay reportes municipales para validarlo."),
    ("quemas", "FIRMS ve fuegos de 375 m dos veces por día; las quemas chicas de basura muchas veces no aparecen. Un foco no prueba que sea basura."),
    ("lluvia", "La lluvia de NASA POWER es un modelo de ~0,5°; IMERG es satelital de 10 km."),
    ("agua", "El agua 2022–2026 usa Sentinel-2 con otro método que JRC; comparar con cautela."),
    ("dengue", "No hay datos de casos: todo lo de dengue es hipótesis."),
    ("confianza", "Cada fila trae su columna confianza: [CONFIRMADO CON EVIDENCIA], [SOSPECHOSO - REQUIERE VALIDACIÓN] o [INCIERTO]. "
                  "Decirla al dar la cifra, no subirla nunca y no presentar una hipótesis del grafo como causa. Sin puntajes numéricos."),
])
con.commit()
con.execute("VACUUM")
con.close()
print("cde_ia.sqlite ready:", SAL.stat().st_size // 1024, "KB ·", len(registro), "tables + 4 of dictionary/guide")
