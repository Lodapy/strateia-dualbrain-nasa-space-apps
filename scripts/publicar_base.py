"""Arma la copia pública de la base para el repo de la entrega: quita las tablas sin licencia confirmada
(calles, hidrografia_oficial) y sus filas en el diccionario, la guía, las geometrías y la auditoría.
Uso: python publicar_base.py <origen.sqlite> <destino.sqlite>   y después: python auditar_ia.py <destino> --escribir"""
import shutil
import sqlite3
import sys

SIN_LICENCIA = ("calles", "hidrografia_oficial")
origen, destino = sys.argv[1], sys.argv[2]
shutil.copyfile(origen, destino)
c = sqlite3.connect(destino)
for t in SIN_LICENCIA:
    c.execute(f'DROP TABLE IF EXISTS "{t}"')
    for aux in ("_diccionario_tablas", "_diccionario_columnas", "_geometrias", "_calidad_tablas"):
        c.execute(f"DELETE FROM {aux} WHERE tabla = ?", (t,))
    c.execute("DELETE FROM _guia_consultas WHERE sql LIKE ?", (f"%{t}%",))
c.commit()
c.execute("VACUUM")
quedan = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE '\\_%' ESCAPE '\\'").fetchone()[0]
guia = c.execute("SELECT COUNT(*) FROM _guia_consultas").fetchone()[0]
print(f"copia pública: {quedan} tablas · guía {guia} consultas · sin {', '.join(SIN_LICENCIA)}")
