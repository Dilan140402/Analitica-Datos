# scraper.py
import requests
import csv
from datetime import datetime
from bs4 import BeautifulSoup
from math import radians, sin, cos, sqrt, atan2
import pytz

# === Constantes ===
CITYBIKES_URL = "https://api.citybik.es/v2/networks/citybike-lima"
CLIMA_MIRAFLORES_URL = "https://www.clima.com/peru/lima/miraflores-4"
LIMA_TZ = pytz.timezone("America/Lima")


# === Utilidades ===
def haversine_km(lat1, lon1, lat2, lon2):
    """Calcula distancia entre 2 coordenadas en kilómetros."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def now_iso():
    """Devuelve hora local ISO Lima."""
    return datetime.now(tz=LIMA_TZ).isoformat()


# === CityBikes API ===
def try_citybikes_api():
    """Intenta obtener datos de estaciones desde la API de CityBikes."""
    try:
        r = requests.get(CITYBIKES_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        stations = data['network']['stations']
        return stations
    except Exception as e:
        print("CityBikes API error:", e)
        return None


# === Clima Miraflores ===
def scrape_clima_miraflores():
    """Obtiene temperatura y descripción de clima desde clima.com."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(CLIMA_MIRAFLORES_URL, headers=headers, timeout=12)
        r.raise_for_status()
        text = r.text
        soup = BeautifulSoup(text, 'html.parser')

        # Buscar temperatura (primer número seguido de °)
        import re
        m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*°", text)
        temp = float(m.group(1)) if m else None

        # Buscar descripción (atributo alt de imagen)
        desc = None
        img = soup.find('img', alt=True)
        if img:
            desc = img.get('alt')

        return {'temp_C': temp, 'clima': desc}
    except Exception as e:
        print('Clima scrape error', e)
        return None


# === Capturar snapshot ===
def collect_snapshot(owm_key=None):
    """Obtiene snapshot de estaciones + clima + hora."""
    stations = try_citybikes_api()
    if not stations:
        return []

    ts = now_iso()
    clima = scrape_clima_miraflores()

    rows = []
    MIRAFLORES_CENTER = (-12.117880, -77.033043)
    MIRAFLORES_RADIUS_KM = 2.0

    for s in stations:
        lat = s.get('latitude') or s.get('lat')
        lon = s.get('longitude') or s.get('lon')
        in_miraf = False

        try:
            if lat and lon:
                d = haversine_km(float(lat), float(lon), MIRAFLORES_CENTER[0], MIRAFLORES_CENTER[1])
                in_miraf = d <= MIRAFLORES_RADIUS_KM
        except:
            in_miraf = False

        temp_assigned = clima.get('temp_C') if (in_miraf and clima) else None
        clima_assigned = clima.get('clima') if (in_miraf and clima) else None

        row = {
            'scrape_timestamp': ts,
            'station_id': s.get('id'),
            'station_name': s.get('name'),
            'lat': lat,
            'lon': lon,
            'capacity': s.get('extra', {}).get('slots') or s.get('capacity'),
            'free_bikes': s.get('free_bikes'),
            'empty_slots': s.get('empty_slots'),
            'day_of_week': datetime.now(tz=LIMA_TZ).strftime('%A'),
            'periodo_dia': (
                'mañana' if 5 <= datetime.now(tz=LIMA_TZ).hour < 12 else
                'tarde' if 12 <= datetime.now(tz=LIMA_TZ).hour < 18 else
                'noche'
            ),
            'weather_main': None,
            'weather_desc': None,
            'temp_C': temp_assigned,
            'wind_speed': None,
            'clima_miraflores': clima_assigned,
            'temp_miraflores': clima.get('temp_C') if clima else None,
            'in_miraflores': in_miraf
        }

        rows.append(row)

    return rows


# === Guardar CSV ===
def append_to_csv(rows, csv_path):
    """Agrega nuevas filas a un CSV existente o lo crea si no existe."""
    if not rows:
        return

    header = list(rows[0].keys())
    import os
    exists = os.path.exists(csv_path)

    with open(csv_path, 'a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)
