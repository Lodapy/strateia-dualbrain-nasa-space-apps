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
# metadatos de uso de IA exigidos por las reglas SI de Space Apps
USO_IA = ("Uso de IA (SI) / AI use (SI): los scripts que arman esta base se escribieron con ayuda de Claude Code (Anthropic), "
          "bajo revisión humana; cada cifra se recalcula desde los datos fuente. Las respuestas del chat las genera un modelo local "
          "(Qwen3.5-35B-A3B) a partir de consultas SQL. / The scripts that build this database were written with the help of "
          "Claude Code (Anthropic) under human review; every figure is recomputed from the source data. Chat answers are generated "
          "by a local model (Qwen3.5-35B-A3B) from SQL results.")
c.execute("DELETE FROM _acerca WHERE tema = 'uso de IA (SI)'")
c.execute("INSERT INTO _acerca (tema, texto) VALUES ('uso de IA (SI)', ?)", (USO_IA,))
c.commit()
c.execute("VACUUM")
quedan = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE '\\_%' ESCAPE '\\'").fetchone()[0]
guia = c.execute("SELECT COUNT(*) FROM _guia_consultas").fetchone()[0]
print(f"copia pública: {quedan} tablas · guía {guia} consultas · sin {', '.join(SIN_LICENCIA)}")
