# procesar_citybike_fix.py 
import pandas as pd
import numpy as np
from datetime import datetime

INPUT_CSV = "citybike_lima.csv"   # <- tu CSV crudo
OUTPUT_CSV = "citybike_procesado.csv"     # <- resultado

# --- Helpers ---
def periodo_de_dia(h):
    try:
        h = int(h)
    except Exception:
        return np.nan
    if 5 <= h < 12:
        return "mañana"
    if 12 <= h < 17:
        return "tarde"
    if 17 <= h < 21:
        return "noche"
    return "madrugada"

def safe_mode(series):
    s = series.dropna()
    if s.empty:
        return ""
    mode = s.mode()
    return mode.iloc[0] if not mode.empty else s.iloc[0]

# --- 1) Leer CSV ---
df = pd.read_csv(INPUT_CSV)
print("Columnas originales:", df.columns.tolist()[:30])

# --- 2) Normalizar/renombrar columnas frecuentes (español esperados) ---
# Mapas de alias comunes -> nombre objetivo
alias_map = {
    'id_estacion': ['id_estacion', 'station_id', 'stationid', 'station', 'station-id'],
    'nombre_estacion': ['nombre_estacion', 'station_name', 'stationname', 'name'],
    'latitud': ['lat', 'latitude', 'latitud', 'latitud_dec'],
    'longitud': ['lon', 'lng', 'longitude', 'longitud'],
    'capacidad': ['capacidad', 'capacity', 'dockcount', 'bike_stands', 'slots'],
    'bicis_libres': ['bicis_libres', 'free_bikes', 'available_bikes', 'num_bikes_available'],
    'espacios_vacios': ['espacios_vacios', 'empty_slots', 'num_docks_available', 'empty_docks'],
    'timestamp': ['timestamp', 'scrape_timestamp', 'datetime', 'date', 'fecha_hora'],
    'temp_c': ['temp_c', 'temp_C', 'temp', 'temperature'],
    'vel_viento': ['vel_viento', 'wind_speed', 'windspeed'],
    'en_miraflores': ['en_miraflores', 'in_miraflores']
}

# crear mapa lower->original para matching insensible a mayúsculas
col_lower_to_orig = {c.lower(): c for c in df.columns}

for target, aliases in alias_map.items():
    if target in df.columns:
        continue
    found = None
    for a in aliases:
        if a.lower() in col_lower_to_orig:
            found = col_lower_to_orig[a.lower()]
            break
    if found:
        df.rename(columns={found: target}, inplace=True)
        # actualizar mapa lower->orig porque renombramos
        col_lower_to_orig = {c.lower(): c for c in df.columns}

print("Columnas después de normalizar:", df.columns.tolist()[:60])

# --- 3) Tipos seguros ---
# timestamp
if 'timestamp' in df.columns:
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
else:
    df['timestamp'] = pd.NaT

# columnas numéricas
for c in ['latitud','longitud','capacidad','bicis_libres','espacios_vacios','temp_c','vel_viento']:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

# --- 4) espacios_vacios si falta (solo si hay capacidad y bicis_libres) ---
if 'espacios_vacios' not in df.columns:
    if 'capacidad' in df.columns and 'bicis_libres' in df.columns:
        df['espacios_vacios'] = (df['capacidad'] - df['bicis_libres']).clip(lower=0)
        print("Calculo espacios_vacios a partir de capacidad - bicis_libres")
    else:
        df['espacios_vacios'] = np.nan
        print("Aviso: no se encontró 'capacidad' o 'bicis_libres'. 'espacios_vacios' queda NaN")

# --- 5) ocupacion (si no existe) ---
if 'ocupacion' not in df.columns:
    if 'capacidad' in df.columns and 'bicis_libres' in df.columns:
        df['ocupacion'] = df['bicis_libres'] / df['capacidad'].replace({0: np.nan})
        print("Calculada 'ocupacion' = bicis_libres / capacidad")
    else:
        df['ocupacion'] = np.nan
        print("Aviso: no se pudo calcular 'ocupacion' (faltan columnas).")

# --- 6) fecha/hora/dia/periodo ---
df['fecha'] = df['timestamp'].dt.date
df['hora'] = df['timestamp'].dt.hour
df['dia_semana'] = df['timestamp'].dt.day_name()
df['periodo_dia'] = df['hora'].apply(lambda x: periodo_de_dia(x) if pd.notna(x) else np.nan)

# --- 7) codigo_estacion desde nombre si no existe id_estacion ---
if 'codigo_estacion' not in df.columns:
    if 'nombre_estacion' in df.columns:
        df['codigo_estacion'] = df['nombre_estacion'].astype(str).str.extract(r'(\d{5})')
    else:
        df['codigo_estacion'] = np.nan

# --- 8) station_summary (resumen por estación) ---
# elegir llave para agrupar: id_estacion preferido, si no usar codigo_estacion, si no usar nombre_estacion
if 'id_estacion' in df.columns:
    key = 'id_estacion'
elif 'codigo_estacion' in df.columns:
    key = 'codigo_estacion'
else:
    key = 'nombre_estacion'

grouped = df.groupby(key, observed=True)

station_summary = grouped.agg(
    nombre_estacion = ('nombre_estacion', lambda s: safe_mode(s) if 'nombre_estacion' in df.columns else ""),
    obs = (key, 'count'),
    bicis_promedio = ('bicis_libres', 'mean') if 'bicis_libres' in df.columns else pd.NamedAgg(column=key, aggfunc='count'),
    capacidad_promedio = ('capacidad', 'mean') if 'capacidad' in df.columns else pd.NamedAgg(column=key, aggfunc='count'),
    ocupacion_promedio = ('ocupacion', 'mean'),
    pct_vacia = ('bicis_libres', lambda x: (x == 0).mean() * 100) if 'bicis_libres' in df.columns else pd.NamedAgg(column=key, aggfunc=lambda x: np.nan),
    pct_llena = ('espacios_vacios', lambda x: (x == 0).mean() * 100) if 'espacios_vacios' in df.columns else pd.NamedAgg(column=key, aggfunc=lambda x: np.nan)
).reset_index().rename(columns={key: 'id_estacion'})

# hora pico
if 'hora' in df.columns:
    hp = (
        df.groupby([key, 'hora'], observed=True)['ocupacion']
          .mean()
          .reset_index()
          .sort_values([key, 'ocupacion'], ascending=[True, False])
          .groupby(key, observed=True)
          .first()
          .reset_index()[[key,'hora']]
          .rename(columns={key:'id_estacion','hora':'hora_pico'})
    )
    hp['id_estacion'] = hp['id_estacion'].astype(str)
    station_summary['id_estacion'] = station_summary['id_estacion'].astype(str)
    station_summary = station_summary.merge(hp, on='id_estacion', how='left')

# redondeos
for c in ['bicis_promedio','capacidad_promedio','ocupacion_promedio','pct_vacia','pct_llena']:
    if c in station_summary.columns:
        station_summary[c] = station_summary[c].round(3)

# --- 9) Categorías (instantánea y promedio) ---
BINS = [0, 0.35, 0.65, 1.0]
LABELS = ['Baja','Media','Alta']

# borrar columnas antiguas si existieran
for col in ['categoria_ocupacion','categoria_ocupacion_promedio','ocup_cat_fixed']:
    if col in df.columns:
        df.drop(columns=[col], inplace=True)

df['categoria_ocupacion'] = pd.cut(df['ocupacion'].fillna(0), bins=BINS, labels=LABELS, include_lowest=True)
station_summary['categoria_ocupacion_promedio'] = pd.cut(station_summary['ocupacion_promedio'].fillna(0), bins=BINS, labels=LABELS, include_lowest=True)

# unir info de station_summary al df (ocupacion_promedio, categoria_promedio, etc.)
df['id_estacion'] = df['id_estacion'].astype(str) if 'id_estacion' in df.columns else df[key].astype(str)
station_summary['id_estacion'] = station_summary['id_estacion'].astype(str)

df = df.merge(
    station_summary[['id_estacion','ocupacion_promedio','bicis_promedio','capacidad_promedio','categoria_ocupacion_promedio']],
    on='id_estacion',
    how='left',
    validate='many_to_one'
)

# --- 10) columnas finales ordenadas ---
cols_final = [
    'timestamp','fecha','hora','dia_semana','periodo_dia',
    'id_estacion','codigo_estacion','nombre_estacion',
    'latitud','longitud',
    'capacidad','capacidad_promedio',
    'bicis_libres','bicis_promedio','espacios_vacios',
    'ocupacion','ocupacion_promedio',
    'categoria_ocupacion','categoria_ocupacion_promedio',
    'pct_vacia','pct_llena','hora_pico',
    'temp_c','vel_viento','en_miraflores'
]
cols_final = [c for c in cols_final if c in df.columns]

# ---------------------------
# AÑADIDO: eliminar código 27042 (robusto a tipos)
# ---------------------------
# Normalizar codigo_estacion a str (si existe)
if 'codigo_estacion' in df.columns:
    # algunos valores vienen como float (NaN), otros como int o str. Convertimos a str y strip.
    df['codigo_estacion'] = df['codigo_estacion'].astype(str).str.strip()
    # Los NaN convertidos a 'nan' no queremos eliminar; filtramos explicitamente el literal '27042'
    before_len = len(df)
    df = df[~df['codigo_estacion'].isin(['27042', '27042.0', '27042.00'])].reset_index(drop=True)
    removed = before_len - len(df)
    print(f"Se eliminaron {removed} filas con codigo_estacion == 27042 (si existían).")
else:
    # por seguridad, también revisamos id_estacion por si el código aparece ahí
    if 'id_estacion' in df.columns:
        df['id_estacion'] = df['id_estacion'].astype(str).str.strip()
        before_len = len(df)
        df = df[~df['id_estacion'].isin(['27042', '27042.0', '27042.00'])].reset_index(drop=True)
        removed = before_len - len(df)
        if removed:
            print(f"Se eliminaron {removed} filas con id_estacion == 27042 (si existían).")

# Confirmación adicional: eliminar cualquier fila donde codigo_estacion contiene '27042' (por si había formato extraño)
if 'codigo_estacion' in df.columns:
    mask_contains = df['codigo_estacion'].str.contains('27042', na=False)
    if mask_contains.any():
        before_len = len(df)
        df = df[~mask_contains].reset_index(drop=True)
        print(f"Se eliminaron {before_len - len(df)} filas adicionales donde codigo_estacion contenía '27042'.")

# ---------------------------
# Guardados finales
# ---------------------------
df[cols_final].to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
station_summary.to_csv("station_summary_agg.csv", index=False, encoding='utf-8-sig')

# (Opcional) guardar una copia adicional con nombre fijo
df.to_csv("dataframe_procesado_final.csv", index=False, encoding='utf-8-sig')

print("✅ Procesado completado.")
print("Archivo guardado:", OUTPUT_CSV)
print("También guardado: dataframe_procesado_final.csv y station_summary_agg.csv")
print("Columnas guardadas:", cols_final)
