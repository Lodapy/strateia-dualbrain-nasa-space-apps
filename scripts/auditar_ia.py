"""Auditoría de curado y calidad de la base para IA (cde_ia*.sqlite): confianza, fuentes, vacíos, ubicación, duplicados, rangos y cifras cruzadas.
Uso: python auditar_ia.py cde_ia_v4.sqlite  → imprime el resumen y escribe calidad_<base>.json. Sin puntajes inventados: solo conteos y porcentajes de filas."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

D = Path(__file__).parent
ARG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cde_ia.sqlite")
BASE = ARG if ARG.exists() else D / ARG  # ruta desde el directorio actual o junto al script
c = sqlite3.connect(BASE)
ETIQ = ("[CONFIRMADO CON EVIDENCIA]", "[SOSPECHOSO - REQUIERE VALIDACIÓN]", "[INCIERTO]")
W, S, E, N, MARGEN = -54.7402209, -25.6002611, -54.5938773, -25.386714, 0.01
FUERA_PERMITIDO = {"focos_calor_region", "zonas_analisis", "turbidez_temporada_seca", "no2_ultimos_30_dias", "barrios_osm", "agua_anual", "agua_radar_20261015"}
RANGOS = {"aod_media_jul_sep": (0, 5), "aod_cde": (0, 5), "lst_verano_c": (-10, 80), "anio": (1950, 2026), "anio_aparicion": (2000, 2026), "frp_mw": (0, 5000),
          "agua_ha": (0, 1e5), "area_ha": (0, 1e5), "largo_km": (0, 100), "focos": (0, 1e5), "focos_total": (0, 1e5), "altura_m": (0, 400),
          "cota_msnm": (90, 250), "cota_alcance_msnm": (90, 250)}  # nombres exactos de columna (no partes del nombre)
q = lambda s, a=(): c.execute(s, a).fetchall()
tablas = [t for (t,) in q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
informe, hallazgos, total_conf = {}, [], Counter()
for t in tablas:
    cols = [r[1] for r in q(f'PRAGMA table_info("{t}")')]
    n = q(f'SELECT COUNT(*) FROM "{t}"')[0][0]
    r = {"filas": n}
    # confianza
    if "confianza" in cols and t != "problemas":
        cnt = dict(q(f'SELECT confianza, COUNT(*) FROM "{t}" GROUP BY confianza'))
        invalidas = sum(v for k, v in cnt.items() if k not in ETIQ)
        r["confianza_pct"] = {k: round(100 * v / n, 1) for k, v in cnt.items()}
        total_conf.update({k: v for k, v in cnt.items() if k in ETIQ})
        if invalidas:
            hallazgos.append(("crítico", t, f"{invalidas} filas con etiqueta de confianza no válida"))
    elif t == "problemas":
        r["confianza_pct"] = {"curada por problema (texto con una o más etiquetas)": 100.0}
        malas = q("SELECT id FROM problemas WHERE confianza NOT LIKE '%[CONFIRMADO%' AND confianza NOT LIKE '%[SOSPECHOSO%' AND confianza NOT LIKE '%[INCIERTO%'")
        if malas:
            hallazgos.append(("crítico", t, f"problemas sin etiqueta válida: {malas}"))
    else:
        hallazgos.append(("crítico", t, "sin columna confianza"))
    # fuente y calidad
    for k in ("fuente", "calidad"):
        if k in cols:
            vac = q(f'SELECT COUNT(*) FROM "{t}" WHERE "{k}" IS NULL OR "{k}" = ""')[0][0]
            if vac:
                hallazgos.append(("importante", t, f"{vac} filas sin {k}"))
    r["tiene_fuente"] = "fuente" in cols or t in ("problemas", "grafo_nodos", "grafo_aristas", "relacion_oni", "tendencias", "series_anuales")
    # vacíos por columna (> 50 %)
    vacios = {}
    for col in cols:
        v = q(f'SELECT COUNT(*) FROM "{t}" WHERE "{col}" IS NULL')[0][0]
        if n and v / n > 0.5:
            vacios[col] = round(100 * v / n, 1)
    r["columnas_mas_50pct_vacias"] = vacios
    # ubicación
    if "lon" in cols and "lat" in cols:
        fuera = q(f'SELECT COUNT(*) FROM "{t}" WHERE lon < ? OR lon > ? OR lat < ? OR lat > ?', (W - MARGEN, E + MARGEN, S - MARGEN, N + MARGEN))[0][0]
        r["pct_fuera_de_cde"] = round(100 * fuera / n, 1) if n else 0
        if fuera and t not in FUERA_PERMITIDO:
            hallazgos.append(("importante", t, f"{fuera} filas con coordenadas fuera de Ciudad del Este"))
    # duplicados (sin fila_id)
    cs = [x for x in cols if x not in ("fila_id",)]
    dup = q(f'SELECT COUNT(*) - COUNT(DISTINCT ' + " || '|' || ".join(f'COALESCE(CAST("{x}" AS TEXT), \'\')' for x in cs) + f') FROM "{t}"')[0][0]
    r["duplicados"] = dup
    if dup:
        hallazgos.append(("menor" if t in ("cauces", "agua_anual") else "importante", t, f"{dup} filas duplicadas"))
    # rangos
    for col in cols:
        if col in RANGOS:
            lo, hi = RANGOS[col]
            tipo = q(f'SELECT typeof("{col}") FROM "{t}" WHERE "{col}" IS NOT NULL LIMIT 1')
            if tipo and tipo[0][0] in ("integer", "real"):
                malos = q(f'SELECT COUNT(*) FROM "{t}" WHERE "{col}" < ? OR "{col}" > ?', (lo, hi))[0][0]
                if malos:
                    hallazgos.append(("importante", t, f"{malos} valores de {col} fuera de [{lo}, {hi}]"))
    # fechas futuras
    if "fecha" in cols:
        fut = q(f'SELECT COUNT(*) FROM "{t}" WHERE fecha > "2026-11-15"')[0][0]
        if fut:
            hallazgos.append(("importante", t, f"{fut} fechas posteriores a hoy"))
    informe[t] = r

# Cifras cruzadas
focos = q("SELECT COUNT(*) FROM focos_historicos_cde")[0][0]
cruces = {
    "edificios bajo 121,19 m = 356": q("SELECT COUNT(*) FROM edificios WHERE cota_alcance_msnm <= 121.19")[0][0] == 356,
    "quemas_por_mes suma = focos": q("SELECT SUM(focos_total) FROM quemas_por_mes")[0][0] == focos,
    "quemas_por_anio suma = focos": q("SELECT SUM(focos) FROM quemas_por_anio")[0][0] == focos,
    "quemas_por_barrio suma = focos": q("SELECT SUM(focos) FROM quemas_por_barrio")[0][0] == focos,
    "quemas_dia_noche suma = focos": q("SELECT SUM(focos) FROM quemas_dia_noche")[0][0] == focos,
    "tendencias n = filas en series_anuales": all(
        q("SELECT COUNT(*) FROM series_anuales WHERE variable = ? AND region = ?", (v, rg))[0][0] == nn
        for v, rg, nn in q("SELECT variable, region, n FROM tendencias")),
    "eventos: 8 hitos de la crecida": q("SELECT COUNT(*) FROM eventos_crecida_2026")[0][0] == 8,
    "crecida: edificios crecen con la cota": [r[0] for r in q("SELECT edificios_alcanzados FROM crecida_rio ORDER BY cota_msnm")] ==
                                            sorted(r[0] for r in q("SELECT edificios_alcanzados FROM crecida_rio")),
}
if q("SELECT COUNT(*) FROM sqlite_master WHERE name = 'calles'")[0][0]:  # la copia pública no trae calles (licencia sin confirmar)
    cruces["calles alto = 757 tramos (sin duplicados de la capa vial)"] = q("SELECT COUNT(*) FROM calles WHERE riesgo_baches = 'alto'")[0][0] == 757
    cruces["problemas P3 coincide con calles"] = str(q("SELECT COUNT(*) FROM calles WHERE riesgo_baches = 'alto'")[0][0]) in q("SELECT indicadores FROM problemas WHERE id = 'P3'")[0][0]
for k, ok in cruces.items():
    if not ok:
        hallazgos.append(("crítico", "cruce", f"no se cumple: {k}"))
tot = sum(total_conf.values())
resumen = {"base": BASE.name, "tablas_auditadas": len(tablas), "filas_con_etiqueta": tot,
           "pct_filas_por_confianza": {k: round(100 * v / tot, 1) for k, v in total_conf.most_common()},
           "cruces_ok": sum(cruces.values()), "cruces_total": len(cruces),
           "hallazgos_por_gravedad": dict(Counter(h[0] for h in hallazgos))}
if "--escribir" in sys.argv:  # guarda la auditoría dentro de la base para que el chat pueda responder sobre su calidad
    por_tabla = Counter(next(iter(r.get("confianza_pct", {"?": 0})), "?") if len(r.get("confianza_pct", {})) == 1 else "mixta" for r in informe.values())
    c.execute("DROP TABLE IF EXISTS _calidad_tablas")
    c.execute("CREATE TABLE _calidad_tablas (tabla TEXT, filas INTEGER, pct_confirmado REAL, pct_sospechoso REAL, pct_incierto REAL, duplicados INTEGER, "
              "columnas_mas_50pct_vacias TEXT, pct_fuera_de_cde REAL, hallazgos TEXT)")
    c.executemany("INSERT INTO _calidad_tablas VALUES (?,?,?,?,?,?,?,?,?)", [
        (t, r["filas"], r.get("confianza_pct", {}).get(ETIQ[0]), r.get("confianza_pct", {}).get(ETIQ[1]), r.get("confianza_pct", {}).get(ETIQ[2]),
         r["duplicados"], json.dumps(r["columnas_mas_50pct_vacias"], ensure_ascii=False), r.get("pct_fuera_de_cde"),
         "; ".join(h[2] for h in hallazgos if h[1] == t) or "sin hallazgos") for t, r in informe.items()])
    c.execute("DROP TABLE IF EXISTS _calidad_resumen")
    c.execute("CREATE TABLE _calidad_resumen (indicador TEXT, valor TEXT)")
    c.executemany("INSERT INTO _calidad_resumen VALUES (?,?)", [
        ("tablas auditadas", str(resumen["tablas_auditadas"])), ("filas con etiqueta de confianza", str(tot)),
        ("filas confirmadas", f'{resumen["pct_filas_por_confianza"].get(ETIQ[0], 0)} %'),
        ("filas sospechosas", f'{resumen["pct_filas_por_confianza"].get(ETIQ[1], 0)} % (los 86.229 edificios pesan: su cota de alcance es un modelo)'),
        ("filas inciertas", f'{resumen["pct_filas_por_confianza"].get(ETIQ[2], 0)} %'),
        ("tablas por confianza", ", ".join(f"{k}: {v}" for k, v in por_tabla.most_common())),
        ("cifras cruzadas verificadas", f'{resumen["cruces_ok"]} de {resumen["cruces_total"]}: ' + "; ".join(k for k, ok in cruces.items() if ok)),
        ("hallazgos", "; ".join(f"{h[0]} · {h[1]} · {h[2]}" for h in hallazgos) or "ninguno"),
        ("cómo leer estos porcentajes", "Son porcentajes de FILAS, no una medida de cuánto confiar en la base. En edificios, lo sospechoso es la cota de alcance "
                                         "(modelo de crecida); la forma y la altura de los edificios son medidas. «Confirmado» significa medido o probado, no "
                                         "«sin dudas»: cada fila trae calidad y límites (_limites) que hay que mencionar cuando afectan a la respuesta."),
        ("método", "conteos sobre la base; sin puntajes inventados (protocolo anti-sesgo)"), ("fecha de auditoría", "2026-11-15")])
    c.commit()
    print("auditoría guardada en la base: _calidad_tablas y _calidad_resumen")
json.dump({"resumen": resumen, "cruces": cruces, "hallazgos": hallazgos, "tablas": informe},
          open(D / f"calidad_{BASE.stem}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(resumen, ensure_ascii=False, indent=1))
for h in hallazgos:
    print(*h, sep=" | ")
