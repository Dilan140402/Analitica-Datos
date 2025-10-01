import os
import pandas as pd
from prueba_5 import collect_snapshot

# Carpeta de salida
os.makedirs("data", exist_ok=True)

EXCEL_PATH = "data/citybike_lima.xlsx"
CSV_PATH = "data/citybike_lima.csv"

# 1. Capturar snapshot
rows = collect_snapshot(owm_key=os.getenv("OWM_API_KEY"))

# 2. Guardar/actualizar Excel y CSV
if rows:
    df_new = pd.DataFrame(rows)

    if os.path.exists(EXCEL_PATH):
        df_old = pd.read_excel(EXCEL_PATH)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df.to_excel(EXCEL_PATH, index=False)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8")

    print(f"✅ Datos agregados: {len(rows)} filas nuevas.")
else:
    print("⚠️ No se obtuvieron datos en esta ejecución.")
