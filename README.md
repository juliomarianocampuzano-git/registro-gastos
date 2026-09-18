# Gastos del mes

Slug: `gastos-del-mes`

App en Python, HTML/JS y SQLite para registrar gastos del hogar por categoria, ver totales del mes y detectar en que se va la plata. Automatiza el control de plata diaria/mensual sin planillas complicadas.

Este repo es un ejercicio junior de portfolio (SQL / Python / automatizacion).
No es un producto de produccion: cubre un caso feliz, trae datos de ejemplo y tests cortos.

## Stack

python, html, javascript, sqlite

## Como correrlo

```bash
python main.py
python -m pytest -q
```

## Features

- CLI con --help
- Carga de datos de ejemplo
- Resumen imprimible
- Tests del caso feliz

## Datos de ejemplo

El archivo `data/sample.csv` alcanza para ver el flujo completo sin APIs externas.

## Limite honesto

No hay autenticacion, ni UI, ni escala. Sirve para leer el codigo de una sentada y
mostrar criterio de junior: un entry point, una tabla SQLite y tests del camino feliz.

## Publicacion

Repo: https://github.com/juliomarianocampuzano-git/gastos-del-mes

Audiencia: AR/LATAM/EU/US
Nivel: junior
Dominio: Python/SQL/IA Automation

Este README se completo en el paso documentar del ciclo local. El post de LinkedIn
vive en LINKEDIN.md (espanol rioplatense, tono junior, con un limite honesto).