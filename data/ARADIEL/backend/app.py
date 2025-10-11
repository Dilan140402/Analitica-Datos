# ============================================================
# app.py — Backend principal del proyecto CityBike Lima
# ============================================================

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import mysql.connector 
from models import init_db, check_user
from scraper import collect_snapshot, append_to_csv
from data_utils import load_full_history, station_average_occupancy, DATA_DIR
from pathlib import Path
from data_processor import procesar_citybike_csv
import pandas as pd
import requests
from apscheduler.schedulers.background import BackgroundScheduler
# ============================================================
# 1. Inicialización del servidor Flask y Base de Datos
# ============================================================

init_db()  # crea la base con usuario admin/1234 si no existe
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

DATA_DIR = Path(DATA_DIR)
LIVE_CSV = DATA_DIR / 'citybike_live.csv'

# ============================================================
# 🔗 Conexión a MySQL
# ============================================================

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",       # deja vacío si no tienes contraseña
        database="citybike_db"
    )

def check_user(username, password):
    """Verifica si el usuario existe en la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE nombre = %s AND password = %s", (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user is not None


# ============================================================
# 2. Rutas de Autenticación (Login)
# ============================================================
@app.route('/api/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type debe ser application/json"}), 415

    """Verifica usuario y contraseña desde MySQL"""
    data = request.get_json()
    user = data.get('username')
    pwd = data.get('password')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Ajusta si tus columnas tienen otros nombres
        query = "SELECT * FROM usuarios WHERE nombre = %s AND password = %s"
        cursor.execute(query, (user, pwd))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Usuario o contraseña incorrectos"})

    except mysql.connector.Error as err:
        print(f"❌ Error MySQL: {err}")
        return jsonify({"success": False, "error": "Error en el servidor"}), 500

# ============================================================
# . 
# ============================================================
@app.route('/api/usuarios', methods=['GET'])
def get_usuarios():
    """Devuelve todos los usuarios de la base de datos"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nombre, correo FROM usuarios")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)



# ============================================================
# 3. Servir páginas del Frontend
# ============================================================

@app.route('/')
def index():
    """Carga el panel principal (mapa y estaciones)"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/login')
def login_page():
    return send_from_directory(app.static_folder, 'login.html')


# ============================================================
# 4. Endpoint: Tomar snapshot en tiempo real (scraping)
# ============================================================

@app.route('/api/snapshot', methods=['POST'])
def api_snapshot():
    """Ejecuta scraping de CityBike y guarda en CSV"""
    rows = collect_snapshot()
    append_to_csv(rows, str(LIVE_CSV))
    # Procesar historico actualizado
    input_file = str(LIVE_CSV)
    output_file = str(DATA_DIR / 'citybike_procesado.csv')
    procesar_citybike_csv(input_file, output_file)
    return jsonify({'saved': len(rows)})


# ============================================================
# 5. Endpoint: Listar estaciones (histórico + live)
# ============================================================

@app.route('/api/stations', methods=['GET'])
def api_stations():
    print("🔍 Cargando histórico desde Excel y generando lista de estaciones...")

    df = load_full_history()
    if df.empty:
        print("⚠️ Dataset vacío, no se pueden generar estaciones.")
        return jsonify([])

    # Asegurar nombres coherentes
    rename_map = {
        "scrape_timestamp": "scrape_timestamp",
        "station_id": "station_id",
        "station_name": "station_name",
        "lat": "lat",
        "lon": "lon",
        "capacity": "capacity",
        "free_bikes": "free_bikes",
        "empty_slots": "empty_slots"
    }
    df = df.rename(columns=rename_map)

    # Forzar tipos numéricos
    for col in ['lat', 'lon', 'capacity', 'free_bikes', 'empty_slots']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Verificar existencia de columna de tiempo
    if 'scrape_timestamp' not in df.columns:
        print("⚠️ No se encontró 'scrape_timestamp', se usará un timestamp simulado.")
        df['scrape_timestamp'] = pd.Timestamp.now()

    # Calcular promedios de ocupación por estación
    averages = station_average_occupancy(df)

    # Quitar duplicados y ordenar
    df = df.sort_values('scrape_timestamp').drop_duplicates('station_id', keep='last')
    df = df.dropna(subset=['lat', 'lon'])
    df['station_id'] = df['station_id'].astype(str)

    # Crear lista de estaciones con ocupación promedio real
    stations = []
    for _, r in df.iterrows():
        sid = str(r['station_id'])
        avg_occ = averages.get(sid, 0)
        try:
            avg_occ = float(avg_occ) if avg_occ is not None else 0
        except:
            avg_occ = 0

        station = {
            'station_id': sid,
            'station_name': r.get('station_name', ''),
            'lat': float(r['lat']),
            'lon': float(r['lon']),
            'free_bikes': float(r['free_bikes']) if not pd.isna(r.get('free_bikes')) else None,
            'empty_slots': float(r['empty_slots']) if not pd.isna(r.get('empty_slots')) else None,
            'capacity': float(r['capacity']) if not pd.isna(r.get('capacity')) else None,
            'avg_occupancy': avg_occ
        }
        stations.append(station)

    print(f"✅ Estaciones procesadas: {len(stations)} con ocupación promedio calculada.")
    return jsonify(stations)


# ============================================================
# 6. Endpoint: Recomendaciones de redistribución
# ============================================================
@app.route('/api/redistribution', methods=['GET'])
def api_redistribution():
    """Detecta estaciones con pocas bicicletas y sugiere posibles donantes"""
    df = load_full_history()
    if df.empty:
        return jsonify({"error": "No hay datos disponibles"}), 400

    # Usar última captura por estación
    df = df.sort_values('scrape_timestamp').drop_duplicates('station_id', keep='last')

    # Filtrar columnas necesarias
    df = df[['station_id', 'station_name', 'lat', 'lon', 'free_bikes', 'capacity']].copy()
    df['free_bikes'] = pd.to_numeric(df['free_bikes'], errors='coerce')
    df['capacity'] = pd.to_numeric(df['capacity'], errors='coerce')

    # Estaciones con pocas bicicletas
    low_stations = df[df['free_bikes'] <= 5].to_dict(orient='records')

    results = []

    for low in low_stations:
        # Encontrar posibles donantes (≥ 10 bicis y distintas)
        donors = df[(df['free_bikes'] >= 10) & (df['station_id'] != low['station_id'])]

        if donors.empty:
            continue

        # Calcular distancia aproximada (Haversine)
        def haversine(lat1, lon1, lat2, lon2):
            import math
            R = 6371
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        donors = donors.copy()
        donors['distance_km'] = donors.apply(
            lambda r: haversine(low['lat'], low['lon'], r['lat'], r['lon']), axis=1
        )

        # Seleccionar los 3 más cercanos
        best_donors = donors.nsmallest(3, 'distance_km')

        # Agregar rutas OSRM
        donor_routes = []
        for _, donor in best_donors.iterrows():
            coords = f"{donor['lon']},{donor['lat']};{low['lon']},{low['lat']}"
            url = f"http://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"
            try:
                r = requests.get(url, timeout=10)
                route = r.json()['routes'][0]
                donor_routes.append({
                    "donor_id": donor['station_id'],
                    "donor_name": donor['station_name'],
                    "distance_km": round(route['distance'] / 1000, 2),
                    "duration_min": round(route['duration'] / 60, 1),
                    "geometry": route['geometry']
                })
            except:
                pass

        results.append({
            "target_station": low,
            "suggested_donors": donor_routes
        })

    return jsonify(results)

# ============================================================
# X. Endpoint: Procesar histórico CityBike
# ============================================================
from data_processor import procesar_citybike_csv
from pathlib import Path

@app.route('/api/process_history', methods=['POST'])
def api_process_history():
    """Procesa el archivo histórico CSV y genera citybike_procesado.csv"""
    data_dir = Path(__file__).parent / "data"
    input_file = data_dir / "citybike_lima(5).csv"
    output_file = data_dir / "citybike_procesado.csv"

    try:
        df = procesar_citybike_csv(input_file, output_file)
        return {"success": True, "rows": len(df)}, 200
    except Exception as e:
        return {"success": False, "error": str(e)}, 500

# ============================================================
# 7. Endpoint: Data histórica completa
# ============================================================

@app.route('/api/history', methods=['GET'])
def api_history():
    """Devuelve toda la base de datos histórica procesada"""
    processed_file = DATA_DIR / 'citybike_procesado.csv'
    if not processed_file.exists():
        return jsonify({"error": "No existe el archivo procesado"}), 404

    df = pd.read_csv(processed_file)
    return jsonify(df.to_dict(orient='records'))


# ============================================================
# 8. Endpoint: Estimar ruta (API pública OSRM)
# ============================================================

@app.route('/api/estimate_route', methods=['POST'])
def api_estimate_route():
    """Calcula la ruta entre dos estaciones y devuelve distancia y tiempo"""
    payload = request.get_json()
    src = payload.get('src')  # {lat, lon}
    dst = payload.get('dst')

    if not src or not dst:
        return jsonify({'error': 'missing src/dst'}), 400

    # Llamar al servidor OSRM
    coords = f"{src['lon']},{src['lat']};{dst['lon']},{dst['lat']}"
    url = f"http://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=true"

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        jr = r.json()
        route = jr['routes'][0]
        return jsonify({
            'duration': route['duration'],
            'distance': route['distance'],
            'geometry': route['geometry']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# 9. Tarea programada: tomar snapshot cada 5 minutos
# ============================================================

from apscheduler.schedulers.background import BackgroundScheduler

def auto_snapshot():
    print("⏱️ [Scheduler] Ejecutando snapshot automático...")
    try:
        rows = collect_snapshot()
        append_to_csv(rows, str(LIVE_CSV))
        print(f"✅ Snapshot automático guardado ({len(rows)} registros).")
    except Exception as e:
        print(f"❌ Error en snapshot automático: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(auto_snapshot, 'interval', minutes=5)
scheduler.start()





# ============================================================
# 10. Ejecutar servidor
# ============================================================

if __name__ == '__main__':
    app.run(debug=True,use_reloader=False)  # use_reloader=False para evitar doble scheduler

