#!/usr/bin/env python3
"""Consulta la base cde_gemelo.gpkg sin GDAL (solo librería estándar; Python 3.8+), pensado para el Jetson Orin.

Uso:
  python3 consultar.py capas                 # capas y tablas con su cantidad de filas
  python3 consultar.py problemas             # registro de problemas (id, confianza, indicadores)
  python3 consultar.py contexto              # contexto compacto para el LLM (JSON)
  python3 consultar.py sql "SELECT ..."      # consulta de atributos (las geometrías vienen como BLOB GeoPackage)
  python3 consultar.py caja lon lat [radio_m] # elementos de cada capa cuya caja toca un punto (índice R-tree)
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DB = AQUI / "cde_gemelo.gpkg"


def conectar():
    con = sqlite3.connect("file:{}?mode=ro".format(DB), uri=True)
    con.row_factory = sqlite3.Row
    return con


def capas(con):
    for fila in con.execute("SELECT table_name, data_type FROM gpkg_contents ORDER BY data_type, table_name"):
        n = con.execute('SELECT COUNT(*) FROM "{}"'.format(fila["table_name"])).fetchone()[0]
        print("{:<22} {:<10} {:>7}".format(fila["table_name"], fila["data_type"], n))


def problemas(con):
    for f in con.execute("SELECT id, problema, confianza, indicadores FROM problemas ORDER BY id"):
        print("{} · {}\n   {}\n   {}\n".format(f["id"], f["problema"], f["confianza"], f["indicadores"]))


def caja(con, lon, lat, radio_m=150.0):
    dlat = radio_m / 111195.0
    dlon = radio_m / (111195.0 * math.cos(math.radians(lat)))
    tablas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rtree_%_geom'")]
    for t in tablas:
        capa = t[len("rtree_"):-len("_geom")]
        n = con.execute('SELECT COUNT(*) FROM "{}" WHERE maxx >= ? AND minx <= ? AND maxy >= ? AND miny <= ?'.format(t),
                        (lon - dlon, lon + dlon, lat - dlat, lat + dlat)).fetchone()[0]
        if n:
            print("{:<22} {:>6} elementos en {:.0f} m".format(capa, n, radio_m))


def main():
    if not DB.exists():
        sys.exit("No encuentro {}".format(DB))
    con = conectar()
    orden = sys.argv[1] if len(sys.argv) > 1 else "capas"
    if orden == "capas":
        capas(con)
    elif orden == "problemas":
        problemas(con)
    elif orden == "contexto":
        print((AQUI / "contexto_dualbrain.json").read_text(encoding="utf-8"))
    elif orden == "sql":
        for f in con.execute(sys.argv[2]):
            print(json.dumps({k: (None if isinstance(f[k], bytes) else f[k]) for k in f.keys()}, ensure_ascii=False))
    elif orden == "caja":
        caja(con, float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 150.0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
