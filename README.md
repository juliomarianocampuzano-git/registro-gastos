# Gastos del mes

App junior para anotar gastos del hogar, guardarlos en **SQLite** y ver totales del mes por categoría desde una pantalla **HTML + JavaScript**.

## Qué automatiza
El control mensual de plata personal/hogar: cargar gastos del día, agruparlos por categoría y ver en qué se va el presupuesto sin armar una planilla a mano.

## Stack
- **Python + Flask**: API y lógica
- **HTML + JavaScript**: interfaz
- **SQLite**: persistencia real (archivo `data/gastos.db`)

## Instalación
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución
```bash
python app.py
```
Abrí http://127.0.0.1:5000

## Tests
```bash
pytest -q
```

## Límites honestos
No tiene usuarios ni login, no sincroniza con el banco y no reemplaza un Excel contable. Es un ejercicio claro de backend + frontend + SQL.
