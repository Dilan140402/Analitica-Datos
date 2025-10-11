# data_utils.py
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data'
HIST_XLSX = DATA_DIR / 'citybike_lima (5).xlsx'
LIVE_CSV = DATA_DIR / 'citybike_live.csv'

# === Cargar histórico completo ===

def load_full_history():
    frames = []

    # 📌 Nuevo: archivo procesado como base histórica
    PROCESSED_CSV = DATA_DIR / "citybike_procesado.csv"

    if PROCESSED_CSV.exists():
        print(f"✅ Leyendo histórico procesado desde: {PROCESSED_CSV}")
        df_hist = pd.read_csv(PROCESSED_CSV)
        frames.append(df_hist)
    else:
        print(f"⚠️ No se encontró el archivo histórico procesado: {PROCESSED_CSV}")

    # 📌 Datos en vivo
    if LIVE_CSV.exists():
        print(f"✅ Leyendo datos en vivo desde: {LIVE_CSV}")
        dfl = pd.read_csv(LIVE_CSV)
        frames.append(dfl)
    else:
        print("ℹ️ No hay archivo CSV en vivo todavía.")

    # 📌 Unir ambos si existen
    if frames:
        df = pd.concat(frames, ignore_index=True)
        print(f"✅ Dataset combinado con {df.shape[0]} registros y {df.shape[1]} columnas.")
    else:
        print("⚠️ No se pudo cargar ningún dataset (DataFrame vacío).")
        df = pd.DataFrame()

    return df



# === Calcular promedio de ocupación, bicis, etc. ===
# promedio de ocupación (por estación): ocupacion = free_bikes / capacity
def station_average_occupancy(df):
    if df.empty:
        print("⚠️ DataFrame vacío en station_average_occupancy()")
        return {}

    # Asegurar tipos numéricos
    df['capacity'] = pd.to_numeric(df['capacity'], errors='coerce')
    df['free_bikes'] = pd.to_numeric(df['free_bikes'], errors='coerce')
    df['empty_slots'] = pd.to_numeric(df['empty_slots'], errors='coerce')

    # Calcular ocupación: proporción de bicis libres respecto a capacidad
    df['avg_occupancy'] = df.apply(
        lambda r: (r['free_bikes'] / r['capacity'])
        if pd.notna(r['free_bikes']) and pd.notna(r['capacity']) and r['capacity'] > 0
        else None,
        axis=1
    )

    # Agrupar por estación
    res = df.groupby('station_id')['avg_occupancy'].mean().to_dict()

    # Debug para revisar valores
    print(f"✅ Calculados promedios de ocupación para {len(res)} estaciones")
    return res


