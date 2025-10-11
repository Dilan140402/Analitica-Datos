from data_processor import procesar_citybike_csv
from pathlib import Path

# 📂 Carpeta de datos
data_dir = Path(__file__).parent / "data"

# 📥 Archivo de entrada (el CSV original crudo)
input_file = data_dir / "citybike_lima (5).csv"   # ← pon el nombre real aquí

# 💾 Archivo de salida — exactamente como tú quieres
output_file = data_dir / "citybike_procesado.csv"

# 🧠 Procesar
print(f"🔸 Leyendo desde: {input_file}")
print(f"💾 Guardando en: {output_file}")
procesar_citybike_csv(input_file, output_file)