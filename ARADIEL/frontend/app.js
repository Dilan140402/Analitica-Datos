// app.js
const map = L.map('map').setView([-12.121, -77.03], 14);

// Capa base (mapa)
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors'
}).addTo(map);

// Función para obtener color según ocupación promedio
function getColor(occ) {
  if (occ === null || isNaN(occ)) return '#999';  // gris si no hay dato
  if (occ < 0.3) return '#2ecc71';                // verde = baja ocupación
  if (occ < 0.6) return '#f1c40f';                // amarillo = media
  if (occ < 0.8) return '#e67e22';                // naranja = alta
  return '#e74c3c';                               // rojo = muy alta
}

// Cargar estaciones desde la API
async function loadStations() {
  try {
    const res = await fetch('/api/stations');
    const data = await res.json();
    stationData = data; // Guardar para uso posterior

    if (!data || data.length === 0) {
      alert("⚠️ No hay estaciones disponibles en el dataset.");
      return;
    }

    console.log(`✅ ${data.length} estaciones cargadas.`);

    data.forEach(station => {
      const occ = station.avg_occupancy;
      const color = getColor(occ);

      // Marcador circular con color según ocupación
      const marker = L.circleMarker([station.lat, station.lon], {
        radius: 8,
        color: color,
        fillColor: color,
        fillOpacity: 0.8,
        weight: 1
      }).addTo(map);

      // Popup con detalles
      const popup = `
        <div style="font-size:14px">
          <b>${station.station_name}</b><br>
          🚲 Bicicletas libres: ${station.free_bikes ?? 'N/D'}<br>
          🅿️ Espacios vacíos: ${station.empty_slots ?? 'N/D'}<br>
          📦 Capacidad: ${station.capacity ?? 'N/D'}<br>
          🔵 Ocupación promedio: ${(occ * 100).toFixed(1)}%<br>
        </div>
      `;

      marker.bindPopup(popup);
    });

    renderLowStations();

  } catch (err) {
    console.error("❌ Error al cargar estaciones:", err);
    alert("Error al obtener datos de estaciones.");
  }
}
/*Logica para redistribuir*/
let stationData = [];
let activeRoutes = [];


function renderLowStations() {
  const lowList = document.getElementById('low-list');
  lowList.innerHTML = '';
  const lowStations = stationData.filter(s => s.free_bikes <= 5);
  const donorStations = stationData.filter(s => s.free_bikes >= 10);

  if (lowStations.length === 0) {
    lowList.innerHTML = '<li>✅ Todas las estaciones tienen suficientes bicicletas.</li>';
    return;
  }

  lowStations.forEach(low => {
    const donors = donorStations
      .map(d => ({
        ...d,
        dist: getDistance(low.lat, low.lon, d.lat, d.lon)
      }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 3);

    const li = document.createElement('li');
    li.innerHTML = `<b>${low.station_name}</b> tiene ${low.free_bikes} bicicletas.<br>
      Posibles donantes: ${donors.map(d => d.station_name).join(', ')}`;
    lowList.appendChild(li);
  });
}

function getDistance(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI/180;
  const dLon = (lon2 - lon1) * Math.PI/180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Botón de redistribución
/*document.getElementById('redistribute-btn').addEventListener('click', redistributeBikes);*/
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('redistribute-btn');
  if (btn) {
    btn.addEventListener('click', redistributeBikes);
  }
});


async function redistributeBikes() {
  clearRoutes();
  const lowStations = stationData.filter(s => s.free_bikes <= 5);
  const donors = stationData.filter(s => s.free_bikes >= 10);

  for (const low of lowStations) {
    const closest = donors
      .map(d => ({ ...d, dist: getDistance(low.lat, low.lon, d.lat, d.lon) }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 1); // el más cercano

    for (const donor of closest) {
      const route = await getRoute(donor, low);
      drawRoute(route);
      animateBike(route);
    }
  }
}

async function getRoute(src, dst) {
  const res = await fetch('/api/estimate_route', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({src, dst})
  });
  const data = await res.json();
  return data.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
}

function drawRoute(coords) {
  const routeLine = L.polyline(coords, {color: '#3498db', weight: 4, opacity: 0.8}).addTo(map);
  activeRoutes.push(routeLine);
}

function clearRoutes() {
  activeRoutes.forEach(r => map.removeLayer(r));
  activeRoutes = [];
}

// Simulación de bicicleta moviéndose
function animateBike(coords) {
  let i = 0;
  const marker = L.circleMarker(coords[0], {radius: 5, color: 'red', fillColor: 'red'}).addTo(map);

  const interval = setInterval(() => {
    i++;
    if (i >= coords.length) {
      clearInterval(interval);
      map.removeLayer(marker);
      return;
    }
    marker.setLatLng(coords[i]);
  }, 150);
}


// Verificar estaciones con baja ocupación y sugerir redistribución
async function checkRedistribution() {
  try {
    const res = await fetch('/api/redistribution');
    const data = await res.json();
    const list = document.getElementById('low-list');
    list.innerHTML = '';

    if (!data || data.length === 0) {
      list.innerHTML = '<li>Todas las estaciones están equilibradas ✅</li>';
      return;
    }

    data.forEach(item => {
      const target = item.target_station;
      const donors = item.suggested_donors;

      let donorsText = donors.map(d =>
        `<li>🚲 ${d.donor_name} → ${d.distance_km} km (${d.duration_min} min)</li>`
      ).join('');

      const li = document.createElement('li');
      li.innerHTML = `
        <strong>${target.station_name}</strong> tiene ${target.free_bikes} bicicletas.<br>
        Posibles donantes:<ul>${donorsText}</ul>
        <button onclick='highlightRoutes(${JSON.stringify(JSON.stringify(item))})'>
          Ver rutas
        </button>`;
      list.appendChild(li);
    });
  } catch (err) {
    console.error("❌ Error en redistribución:", err);
  }
}

// Dibuja las rutas en el mapa
function highlightRoutes(itemJson) {
  const item = JSON.parse(itemJson);
  item.suggested_donors.forEach(d => {
    const route = L.geoJSON(d.geometry, {
      style: { color: '#0077cc', weight: 3, opacity: 0.7 }
    }).addTo(map);
    route.bindPopup(`${d.donor_name} → ${item.target_station.station_name}<br>${d.distance_km} km, ${d.duration_min} min`);
  });
}




// Recargar estaciones cada 5 minutos
setInterval(loadStations, 5 * 60 * 1000);
checkRedistribution();
// Inicializar
loadStations();
