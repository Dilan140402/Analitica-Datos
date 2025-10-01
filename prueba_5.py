import requests
import time
import math
import pandas as pd
from datetime import datetime
from dateutil import tz
import xml.etree.ElementTree as ET
import logging
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
CITYBIKE_URL = "https://www.citybikelima.com/es#the-map"
GMAPS_KML = "https://www.google.com/maps/d/kml?mid=12PUl4VbbO3IBWRSaXrCMHH0u_NI&hl=es"

OUTPUT_EXCEL = "citybike_lima.xlsx"
OUTPUT_CSV = "citybike_lima.csv"

LIMA_TZ = tz.gettz("America/Lima")

OWM_BASE = "https://api.openweathermap.org/data/2.5/weather"
CLIMA_MIRAFLORES_URL = "https://www.clima.com/peru/lima/miraflores-4"

MIRAFLORES_CENTER = (-12.117880, -77.033043)  # lat, lon
MIRAFLORES_RADIUS_KM = 2.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------- UTILIDADES ----------
def now_ts():
    return datetime.now(tz=LIMA_TZ)

def periodo_del_dia(dt):
    h = dt.hour
    if 5 <= h < 12:
        return "mañana"
    if 12 <= h < 18:
        return "tarde"
    return "noche"

def fetch_kml_gmaps(kml_url):
    r = requests.get(kml_url, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    placemarks = []
    for pm in root.findall('.//kml:Placemark', ns):
        name_el = pm.find('kml:name', ns)
        name = name_el.text if name_el is not None else None
        desc_el = pm.find('kml:description', ns)
        desc = desc_el.text if desc_el is not None else None
        coord_el = pm.find('.//kml:coordinates', ns)
        if coord_el is not None:
            lonlatalt = coord_el.text.strip()
            lon, lat, *_ = lonlatalt.split(',')
            placemarks.append({
                'name': name,
                'description': desc,
                'lat': float(lat),
                'lon': float(lon)
            })
    return placemarks

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# ---------- CITYBIKE ----------
def try_citybikes_api():
    logging.info("Intentando API pública de CityBikes...")
    try:
        api_root = "https://api.citybik.es/v2/networks"
        resp = requests.get(api_root, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        networks = data.get('networks', [])
        target = None
        for net in networks:
            nname = (net.get('name') or "").lower()
            city = (net.get('location', {}).get('city') or "").lower()
            if 'lima' in nname or 'lima' in city or 'citybike' in nname:
                target = net.get('id')
                break
        if not target:
            return None
        r2 = requests.get(f"https://api.citybik.es/v2/networks/{target}", timeout=20)
        r2.raise_for_status()
        netdata = r2.json().get('network', {})
        stations = netdata.get('stations') or []
        out = []
        for s in stations:
            out.append({
                'id': s.get('id'),
                'name': s.get('name'),
                'lat': s.get('latitude'),
                'lon': s.get('longitude'),
                'capacity': s.get('extra', {}).get('slots') or s.get('capacity'),
                'free_bikes': s.get('free_bikes'),
                'empty_slots': s.get('empty_slots'),
                'timestamp': s.get('timestamp')
            })
        return out
    except Exception as e:
        logging.warning(f"CityBikes API fallo: {e}")
        return None

def selenium_scrape_citybike(url=CITYBIKE_URL, headless=True):
    logging.info("Usando Selenium con webdriver_manager...")
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
    except WebDriverException as e:
        logging.error("No se pudo iniciar Chrome: " + str(e))
        return None
    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        time.sleep(6)
        candidates = driver.find_elements("css selector", "[class*='station'], [class*='marker'], [data-lat]")
        stations = []
        for el in candidates:
            try:
                name = el.get_attribute("title") or el.get_attribute("data-name") or el.text
                lat = el.get_attribute("data-lat")
                lon = el.get_attribute("data-lon")
                if lat and lon:
                    stations.append({'name': name, 'lat': float(lat), 'lon': float(lon)})
            except Exception:
                continue
        driver.quit()
        return stations if stations else None
    except Exception as e:
        logging.error("Error Selenium: " + str(e))
        try: driver.quit()
        except: pass
        return None

# ---------- CLIMA ----------
def get_weather_for_coord(lat, lon, owm_key):
    if not owm_key:
        return None
    params = {"lat": lat, "lon": lon, "appid": owm_key, "units": "metric", "lang": "es"}
    try:
        r = requests.get(OWM_BASE, params=params, timeout=10)
        r.raise_for_status()
        j = r.json()
        return {
            'weather_main': j.get('weather', [{}])[0].get('main'),
            'weather_desc': j.get('weather', [{}])[0].get('description'),
            'temp_C': j.get('main', {}).get('temp'),
            'wind_speed': j.get('wind', {}).get('speed'),
        }
    except Exception as e:
        logging.warning(f"OWM fallo para {lat},{lon}: {e}")
        return None

def scrape_clima_miraflores():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(CLIMA_MIRAFLORES_URL, timeout=20, headers=headers)
        resp.raise_for_status()
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")
        temp = None
        clima_desc = None
        candidate = soup.find(string=re.compile(r'\d{1,2}(?:\.\d+)?\s*°'))
        if candidate:
            m = re.search(r'(\d{1,2}(?:\.\d+)?)\s*°', candidate)
            if m:
                temp = float(m.group(1))
        img = soup.find('img', alt=True)
        if img and img.get('alt'):
            clima_desc = img.get('alt').strip()
        return {'temp_C': temp, 'clima': clima_desc}
    except Exception as e:
        logging.warning(f"No se pudo scrapear Clima.com Miraflores: {e}")
        return None

# ---------- PRINCIPAL ----------
def collect_snapshot(owm_key=None):
    stations = try_citybikes_api()
    if not stations:
        stations = selenium_scrape_citybike(CITYBIKE_URL)
    if not stations:
        logging.error("No se pudo obtener lista de estaciones.")
        return []

    ts = now_ts()
    clima_miraf = scrape_clima_miraflores()

    rows = []
    for s in stations:
        lat = s.get('lat')
        lon = s.get('lon')
        free_bikes = s.get('free_bikes') if 'free_bikes' in s else None
        empty_slots = s.get('empty_slots') if 'empty_slots' in s else None
        weather = None
        if (not clima_miraf) and lat and lon and owm_key:
            weather = get_weather_for_coord(lat, lon, owm_key)
        in_miraflores = False
        try:
            if lat is not None and lon is not None:
                dkm = haversine_km(float(lat), float(lon), MIRAFLORES_CENTER[0], MIRAFLORES_CENTER[1])
                in_miraflores = (dkm <= MIRAFLORES_RADIUS_KM)
        except:
            pass
        if in_miraflores and clima_miraf:
            temp_assigned = clima_miraf.get('temp_C')
            clima_assigned = clima_miraf.get('clima')
        else:
            temp_assigned = weather.get('temp_C') if weather else (clima_miraf.get('temp_C') if clima_miraf else None)
            clima_assigned = weather.get('weather_desc') if weather else (clima_miraf.get('clima') if clima_miraf else None)

        row = {
            'scrape_timestamp': ts.isoformat(),
            'station_id': s.get('id'),
            'station_name': s.get('name'),
            'lat': lat,
            'lon': lon,
            'capacity': s.get('capacity'),
            'free_bikes': free_bikes,
            'empty_slots': empty_slots,
            'day_of_week': ts.strftime("%A"),
            'periodo_dia': periodo_del_dia(ts),
            'weather_main': (weather.get('weather_main') if weather else None),
            'weather_desc': (weather.get('weather_desc') if weather else None),
            'temp_C': temp_assigned,
            'wind_speed': (weather.get('wind_speed') if weather else None),
            'clima_miraflores': (clima_miraf.get('clima') if clima_miraf else None),
            'temp_miraflores': (clima_miraf.get('temp_C') if clima_miraf else None),
            'in_miraflores': in_miraflores
        }
        rows.append(row)
    return rows
