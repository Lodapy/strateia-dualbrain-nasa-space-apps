# StrateIA Dual Brain · NASA Space Apps 2026

**Smart City Decision Intelligence for Ciudad del Este, Paraguay · Challenge: “Be An Earth System Trend Detective!”**

▶ **Demo video (30 s, 4K):** [`media/strateia-dualbrain-30s.mp4`](media/strateia-dualbrain-30s.mp4)

Ciudad del Este grows fast on the bank of the Paraná River. In October 2026 the river rose to 121.19 m and 1,210 families were affected.
We built a curated database of the city from NASA and Copernicus satellite data (1990–2026) and a local AI that answers questions **only from that data**, then turns the evidence into proposed decisions with their limits in plain sight.
Every row carries its source, a quality note and a confidence label. The AI does not invent numbers: each figure comes from an SQL query.

## What we built

| Part | What it does | Where |
|---|---|---|
| **1. Curated database** | 45 tables (public copy), 116,080 rows, each with source, quality note and confidence label: water, rain, heat, air, fires, flood stages, buildings, trends, 9 city problems and 24 proposed tasks. | `data/cde_ia.sqlite`, built by `scripts/` |
| **2. Dual Brain chat** | Answers questions in English or Spanish: picks the tables, writes SQL, quotes the number with its source and confidence. Runs offline on an NVIDIA Jetson AGX Orin. | Local service (not in this repository) |
| **3. City Case Decision Intelligence** | For each city problem, lays out the evidence in six stages — case, entities, events, telemetry, analysis, closure — and ends in a proposed decision. Every node states which database field it comes from. | Local web app (not in this repository) |
| **4. Satellites over the city** | A 3D model of Ciudad del Este with the satellites we use and what each one detects, each labelled with its confidence. | Shown in the demo video |

The chat and the web app read this same database. Their code lives in the team's private repository; everything a judge needs to check the figures is here.

## How a decision is made

```
 question ──► Dual Brain picks tables ──► writes SQL ──► curated database
                                                            │
 answer: number + source + confidence label ◄───────────────┘
    │
    ▼
 "Next: smart decision case" ──► proposed task, read as-is from tareas_propuestas
                                  (status PROPOSED · what data is missing · how to validate it)
    │
    ▼
 City Case: evidence in six stages ──► proposed decision ──► humans decide
```

The proposed-task text is read straight from the database, not written by the model, so it cannot be invented or presented as done.

### Answers from the working chat (tested 15 Nov 2026, in English)

| Question | Answer | Proposed decision shown |
|---|---|---|
| How many buildings are below the 121.19 m flood stage, and how sure are we? | **356**, *suspect – needs validation* (the terrain model underestimates the families affected) | T14 · early evacuation alert for San Rafael |
| Does the flood model capture the San Rafael neighbourhood? | **No** (San Rafael and San Agustín), *confirmed with evidence* against official family counts | T14 |
| In which month do fire hotspots peak? | **August, 313 detections**, *confirmed* (NASA FIRMS) | T16 · inspectors at persistent burn sites |
| How many fire hotspots were detected in the city since 2012? | **1,474**, *confirmed* | T16 |
| How many street segments have a high pothole risk? | **757 segments, about 113.5 km**, *suspect* (modelled, no municipal reports) | City Case P3 |

## City cases

| Case | Problem | Confidence (from the database) |
|---|---|---|
| P1 | Paraná River flood (backwater into riverside neighbourhoods) | Event confirmed; flood model suspect (reaches 1 of 6 comparable neighbourhoods) |
| P2 | New construction inside the flood zone | Confirmed: 154 buildings first seen in 2018–2023 below 121 m |
| P3 | Potholes and impassable streets after heavy rain | Suspect: modelled, no pothole reports |
| P4 | Growing urban heat island | Trend confirmed (p = 0.0001); urban cause suspect |
| P5 | Less permanent and more seasonal water on the river bank | Trend confirmed (JRC 1990–2021); cause uncertain |
| P6 | Rain flooding of a low stream valley | Uncertain: topographic susceptibility, radar did not see it flooded in 2026 |
| P7 | Dengue after rain and heat | Uncertain: hypothesis, no case data |
| P8 | Low water, drought and fires after El Niño | Uncertain for the next cycle; 2021 minimum confirmed |
| P9 | Burning and air quality | Burning season and 2024 regional smoke confirmed; that hotspots are waste burning is suspect |
| P10 | Traffic at critical nodes of Route PY02 | Data contributed by the team, **not verified** (satellites do not see cars) |

The 24 proposed tasks (T1–T24: sensors, data fusion, hydraulic and traffic models, the decisions above) are all in status **PROPOSED**. None is implemented.

## What the data shows (verified trends)

| Trend (1990–2026) | Change per decade | Test |
|---|---|---|
| Urban heat island (built-up minus trees, Landsat) | **+0.56 °C** | Mann-Kendall p = 0.0001 |
| Permanent river-bank water (JRC / Sentinel-2) | **−6.05 ha** | p = 0.0004 |
| Annual rainfall (NASA POWER, 0.5° cell) | **−150 mm** | p = 0.016 |
| Lit area at night (NASA Black Marble, 2012–2026) | **+58 km²** | p < 0.001 |

Other verified results:

- **Flood exposure:** 356 buildings are below the 121.19 m stage reached on 16 Oct 2026 (NASADEM terrain model). 154 of them first appear in 2018–2023 (Google Open Buildings Temporal).
- **Waste burning:** NASA FIRMS VIIRS shows 1,474 fire hotspots in the city in 2012–2026. The peak is in August, and July–September has about half of them. There are 95 sites that burn in 3 or more years.
- **Air:** tropospheric NO₂ (Sentinel-5P) is 52 % higher in the city than in the 130 km region (14.6 vs 9.6 µmol/m², last 30 days).

## What the data does not show (limits we declare)

- The flood model reaches only 1 of 6 comparable affected neighbourhoods. It misses San Rafael (380 families). Our hypothesis is backwater on the Acaraymí stream plus a terrain model with roofs. The model is not used for alerts in those areas.
- A fire hotspot (375 m) does not prove waste burning. Small, short fires are missed.
- Satellites do not see people, nationality or security. Population is modelled (GHSL), not census.
- **We do not predict disasters yet.** Sensors (LoRaWAN), data fusion (EKF), hydraulic AI (PINN), traffic AI (DQN) and accessibility (2SFCA) are **proposed next steps** (tasks T1–T24 in the database), not working parts.
- The pothole model and the traffic data are not validated: there are no municipal pothole reports or street counts yet.

## Repository

| Path | Content |
|---|---|
| `data/cde_ia.sqlite` | Curated database (public copy): 45 tables, 116,080 confidence-labelled rows. SHA-256 in `data/SHA256SUMS`. |
| `data/DATA_DICTIONARY.md` | Every table in English, with rows and confidence. Cell contents are in Spanish. |
| `scripts/` | Build, audit and query scripts (Python 3.12, comments and messages in English). `insumos/` holds the intermediate Earth Engine results. |
| `DATA_SOURCES.md` | Every dataset with provider and licence. |
| `media/strateia-dualbrain-30s.mp4` | 30-second demo video (4K): satellites over the city and City Case Decision Intelligence. The narration is an AI-generated voice (Qwen3-TTS cloned from the team owner's own voice, with consent) and the satellites are an AI-generated illustration; both are labelled on screen and in the metadata. |

**Language:** code comments and docs are in English; database identifiers and cell contents are in Spanish (the local municipal language), fully explained in `data/DATA_DICTIONARY.md`.

Quick check with Python only (no extra packages):

```bash
sha256sum -c data/SHA256SUMS
python -c "import sqlite3; c=sqlite3.connect('data/cde_ia.sqlite'); print(c.execute('SELECT COUNT(*) FROM edificios WHERE cota_alcance_msnm <= 121.19').fetchone())"   # 356
python scripts/auditar_ia.py data/cde_ia.sqlite   # quality audit: 8/8 cross-checks
```

The table `_guia_consultas` has 24 example questions with their SQL. The audit results are in `_calidad_resumen`. The city cases are in `problemas` and the proposed tasks in `tareas_propuestas`.

Two tables are left out of this public copy because their licence is not confirmed: the municipal street layer and the official hydrography (see `DATA_SOURCES.md`); `scripts/publicar_base.py` makes this copy. The P3 indicators (757 segments) stay in `problemas`. Rebuilding the database from scratch also needs the building layer with heights and the twin-app data, which are not in this repository (see “Pre-existing components”).

## How the AI answers

The chat runs on a local NVIDIA Jetson AGX Orin, without cloud. A language model (Qwen3.5-35B-A3B, open weights, served with llama.cpp) works in two steps:

1. It reads a short catalogue and picks the tables.
2. It writes an SQL query against `cde_ia.sqlite`, and the answer quotes the result with its source and confidence. If a query returns nothing, it retries with fewer filters; if the data is missing, it says so.

## Use of Super Intelligence (SI) tools

- **Code and data processing:** written with the help of Claude Code (Anthropic), under human review. Every figure in this README was re-computed from the database.
- **Chat answers in the demo:** generated by the local language model from SQL results. They are SI-generated text.
- **Voice in the demo video:** synthesised with Qwen3-TTS from the team owner's own recorded voice, with the owner's consent. It is SI-generated audio: the video shows a visible "AI-generated voice" label, and the MP4 metadata says so.
- **Images:** the satellites over the 3D city model are an AI-generated illustration, and the Singapore photo in the presentation was made with Meta AI; both carry a visible mark. The 3D city model itself is a real Rhino capture. Other city photos in the presentation are from Google Maps and are credited on each photo.
- **Database metadata:** the table `_acerca` in `data/cde_ia.sqlite` has a row `uso de IA (SI)` that declares this use.
- **Knowledge documents:** some planning documents loaded into `conocimiento_cde` were drafted with SI assistants. Each claim was contrasted with the data and labelled; several are marked as not supported.
- **No NASA logos, flags or mission identifiers** were generated or modified with SI.

## Pre-existing components (declared)

- **Building footprints with heights:** OpenStreetMap + Google Open Buildings 2.5D, prepared on 10 Nov 2026 for a 3D model of the city.
- **Digital-twin app scaffold:** started on 13 Nov 2026.
- **Local AI infrastructure:** Jetson AGX Orin with the model server, from before the event.

Built during the hackathon (14–15 Nov 2026): the curated database, the satellite series and trend tests, the flood validation, the fire and air analyses, the confidence labels and audit, the question guide, the city cases and proposed tasks, the chat's decision step, the City Case views in English, and the demo video.

## Licences

- **Code (`scripts/`):** Apache License 2.0 (`LICENSE`).
- **Database (`data/`):** Open Database License (ODbL) 1.0, because it contains data derived from OpenStreetMap. Other sources keep their own terms; see `DATA_SOURCES.md`.

## Team

StrateIA · Ciudad del Este, Paraguay. Local event: NASA Space Apps Ciudad del Este 2026.
