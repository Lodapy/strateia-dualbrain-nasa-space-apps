# Data dictionary (English)

Database: `data/cde_ia.sqlite` (SQLite, EPSG:4326, lon/lat columns; geometries in `_geometrias`). Cell contents are in Spanish; this page explains every table.
Each row carries `fuente` (source), `calidad` (quality note) and `confianza` (confidence). Confidence labels, never numeric scores:

| Label in the data | Meaning |
|---|---|
| `[CONFIRMADO CON EVIDENCIA]` | Confirmed with evidence (measured, with the raw source cited) |
| `[SOSPECHOSO - REQUIERE VALIDACIÓN]` | Suspect – needs validation (modelled, unofficial or partially checked) |
| `[INCIERTO]` | Uncertain (hypothesis or proposal, not data) |

Helper tables: `_diccionario_tablas` / `_diccionario_columnas` (dictionary, Spanish), `_guia_consultas` (24 example questions with SQL), `_acerca`, `_limites`, `_calidad_tablas` and `_calidad_resumen` (audit of this public copy: 8/8 cross-checks).

| Table | Kind | Rows | Confidence | Description |
|---|---|---|---|---|
| `aerosoles_diarios_cde` | table | 30 | CONFIRMED WITH EVIDENCE | Daily aerosol optical depth over the city (smoke/haze indicator). |
| `agua_anual` | layer | 8332 | CONFIRMED WITH EVIDENCE | Yearly surface-water polygons, permanent or seasonal (JRC GSW from Landsat 1990–2021; own Sentinel-2 method 2022–2026). |
| `agua_anual_sentinel2_ha` | table | 18 | SUSPECT – NEEDS VALIDATION | Yearly water area (ha) from Sentinel-2 MNDWI, own method. |
| `agua_radar_20261015` | layer | 20 | SUSPECT – NEEDS VALIDATION | New water seen by Sentinel-1 radar after the October 2026 flood (3 Oct vs 15 Oct 2026). |
| `aire_actual` | table | 8 | CONFIRMED WITH EVIDENCE | Air indicators for the last 30 days vs the same period of 2025: city mean vs 130 km region (NO2, aerosols). |
| `aire_anual` | table | 26 | CONFIRMED WITH EVIDENCE | Yearly air indicators (MODIS MAIAC aerosol optical depth), 2001–2026. |
| `aire_diario` | table | 2873 | CONFIRMED WITH EVIDENCE | Daily NO2 (Sentinel-5P), aerosols, wind and rain for the city, 2019–2026. |
| `barrios_osm` | layer | 98 | SUSPECT – NEEDS VALIDATION | Neighbourhoods of Ciudad del Este with name and boundary (OpenStreetMap, not official). |
| `calor_verano` | layer | 3 | CONFIRMED WITH EVIDENCE | Hottest land-surface zones in summer (Landsat 8/9, Dec–Feb 2023–2026). Ground and roofs, not air. |
| `cauces` | layer | 14897 | CONFIRMED WITH EVIDENCE | Rain-runoff flow lines with drained area (D8 on NASADEM 30 m). Built drains not included. |
| `cobertura` | layer | 261 | CONFIRMED WITH EVIDENCE | Built-up and tree-covered zones (ESA WorldCover 2021). |
| `conocimiento_cde` | table | 57 | SUSPECT – NEEDS VALIDATION | Claims from the owner's knowledge documents, each contrasted with the data and labelled with confidence. |
| `cotas_referencia` | table | 4 | SUSPECT – NEEDS VALIDATION | Local river stages and their effect in San Rafael (108.40 m footbridge … 121.60 m school). Scale to be confirmed. |
| `crecida_rio` | layer | 6 | SUSPECT – NEEDS VALIDATION | Paraná River flood extent for each river stage (terrain model, no levees). Underestimates affected families. |
| `edificios` | layer | 86229 | SUSPECT – NEEDS VALIDATION | Every building with height, neighbourhood, flood stage that reaches it, summer surface heat and year first seen. New construction = first seen 2018–2023. |
| `estancamiento_aire` | table | 29 | SUSPECT – NEEDS VALIDATION | Days with stagnant air (low wind, no rain). Own criterion; flags too many days. |
| `eventos_crecida_2026` | table | 8 | CONFIRMED WITH EVIDENCE | October 2026 flood events with river stage, from press citing SEN, Itaipú or the municipality. |
| `focos_calor_region` | layer | 22 | CONFIRMED WITH EVIDENCE | Fire hotspots in the ~130 km region, last 5 days (NASA FIRMS). |
| `focos_historicos_cde` | layer | 1474 | CONFIRMED WITH EVIDENCE | Fire hotspots inside the city since 2012 with date and neighbourhood (NASA FIRMS VIIRS). A hotspot does not prove waste burning. |
| `fuentes` | table | 16 | CONFIRMED WITH EVIDENCE | Catalogue of data sources with provider, resolution, period and access. |
| `grafo_aristas` | table | 40 | CONFIRMED WITH EVIDENCE | Causal graph edges (cause → effect) with status: proven correlation, documentary evidence, model or hypothesis. |
| `grafo_nodos` | table | 36 | CONFIRMED WITH EVIDENCE | Causal graph nodes. |
| `no2_diario_cde` | table | 29 | CONFIRMED WITH EVIDENCE | Daily tropospheric NO2 over the city (Sentinel-5P), last month. |
| `no2_ultimos_30_dias` | layer | 48 | CONFIRMED WITH EVIDENCE | NO2 per ~3.5 km pixel, last month (zones, not streets). For the city mean use aire_actual. |
| `pasadas_copernicus` | table | 9 | CONFIRMED WITH EVIDENCE | Recent Copernicus overpass metadata (Sentinel-1/2/5P). |
| `problemas` | layer | 9 | CONFIRMED WITH EVIDENCE | Curated register of city problems with indicators, confidence, causes, missing data and interventions. |
| `quemas_dia_noche` | table | 2 | CONFIRMED WITH EVIDENCE | Fire hotspots by day vs night. |
| `quemas_fechas_pico` | table | 15 | CONFIRMED WITH EVIDENCE | Peak fire dates, 2012–2026. |
| `quemas_por_anio` | table | 15 | CONFIRMED WITH EVIDENCE | Fire hotspots per year, 2012–2026. |
| `quemas_por_barrio` | table | 53 | SUSPECT – NEEDS VALIDATION | Fire hotspots per neighbourhood, with area and density. |
| `quemas_por_dia_semana` | table | 7 | CONFIRMED WITH EVIDENCE | Fire hotspots per weekday (fixed satellite overpasses). |
| `quemas_por_mes` | table | 12 | CONFIRMED WITH EVIDENCE | Fire hotspots per month (peak in August). |
| `relacion_oni` | table | 9 | CONFIRMED WITH EVIDENCE | Spearman correlations between the El Niño index (ONI) and local variables. |
| `serie_sentinel1` | table | 183 | CONFIRMED WITH EVIDENCE | Sentinel-1 radar water series per pass (2025–2026). |
| `serie_sentinel2` | table | 168 | CONFIRMED WITH EVIDENCE | Sentinel-2 water series per scene (2026). |
| `series_anuales` | table | 405 | CONFIRMED WITH EVIDENCE | Yearly series 1990–2026: rainfall, surface water, summer surface temperature, ONI, heat island, night lights, modelled population. |
| `sitios_quema_persistente` | layer | 95 | SUSPECT – NEEDS VALIDATION | Places with fire hotspots in 3 or more years: possible dumps or habitual burning. To be checked on the ground. |
| `tareas_propuestas` | table | 24 | UNCERTAIN | Proposed tasks T1–T24 (sensors, fusion, models, GPM, SMAP, SEDAC, BIDARA, decisions A–D, ECOSTRESS, GEDI) with missing data and validation. Proposals, not data. |
| `tendencias` | table | 14 | CONFIRMED WITH EVIDENCE | Trend tests (Mann-Kendall p-value, Sen slope per decade, OLS with 95% CI) for each yearly series. |
| `turbidez_anual` | table | 26 | CONFIRMED WITH EVIDENCE | Yearly dry-season air turbidity (MODIS MAIAC), 2001–2026. |
| `turbidez_por_barrio` | table | 58 | SUSPECT – NEEDS VALIDATION | Dry-season air turbidity per neighbourhood (mix of smoke, traffic and dust). |
| `turbidez_temporada_seca` | layer | 408 | CONFIRMED WITH EVIDENCE | Dry-season air turbidity per 1 km cell (MODIS MAIAC, Jul–Sep 2001–2026). Cells over water are artefacts. |
| `validacion_crecida_barrios` | table | 9 | CONFIRMED WITH EVIDENCE | Neighbourhoods with affected families in Oct 2026 vs what the flood model reaches: the model misses San Rafael and Che la Reina. |
| `valle` | layer | 1 | UNCERTAIN | Low stream valley with its rain-ponding susceptibility model (not observed flooded by radar). |
| `zonas_analisis` | layer | 3 | CONFIRMED WITH EVIDENCE | Analysis cut-outs used by the indicators. |
