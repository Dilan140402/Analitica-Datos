// 🌍 Variable global del mapa
let map;
let stationData = [];
let activeRoutes = [];

// 🚀 Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', () => {
  console.log("🚀 Inicializando mapa...") ;
  map = L.map('map').setView([-12.0464, -77.0428], 13); // Centro en Limac
  console.log("✅ Mapa creado.");

  setTimeout(() => {
    map.invalidateSize();
    console.log("✅ Tamaño del mapa invalidado.");
  }, 300);
  // Inicializa el mapa


  // Capa base de OpenStreetMap
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);
  console.log("✅ Capa base añadida.");
  // Cargar estaciones y listas
  loadStations();
  checkRedistribution();

  // Recargar cada 5 minutos
  setInterval(loadStations, 5 * 60 * 1000);
});

// 🎨 Obtener color por nivel de ocupación
function getColor(occ) {
  if (occ === null || isNaN(occ)) return '#999';
  if (occ < 0.3) return '#2ecc71';
  if (occ < 0.6) return '#f1c40f';
  if (occ < 0.8) return '#e67e22';
  return '#e74c3c';
}

// 📡 Cargar estaciones desde el backend
async function loadStations() {
  try {

    map.eachLayer(layer => {
      if (layer instanceof L.CircleMarker || layer instanceof L.Polyline) {
        map.removeLayer(layer);
      }
    });

    const res = await fetch('/api/stations');
    const data = await res.json();
    stationData = data;

    if (!data || data.length === 0) {
      console.warn("⚠️ No hay estaciones disponibles.");
      return;
    }

    console.log(`✅ ${data.length} estaciones cargadas.`);

    // Limpiar marcadores previos
    map.eachLayer(layer => {
      if (layer instanceof L.CircleMarker || layer instanceof L.Polyline) {
        map.removeLayer(layer);
      }
    });

    // Capa base otra vez (por si la borramos sin querer)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    // Dibujar estaciones en el mapa
    data.forEach(station => {
      const occ = station.avg_occupancy;
      const color = getColor(occ);

      const marker = L.circleMarker([station.lat, station.lon], {
        radius: 8,
        color: color,
        fillColor: color,
        fillOpacity: 0.8,
        weight: 1
      }).addTo(map);

      marker.bindPopup(`
        <div style="font-size:14px">
          <b>${station.station_name}</b><br>
          🚲 Bicicletas libres: ${station.free_bikes ?? 'N/D'}<br>
          🅿️ Espacios vacíos: ${station.empty_slots ?? 'N/D'}<br>
          📦 Capacidad: ${station.capacity ?? 'N/D'}<br>
          🔵 Ocupación promedio: ${(occ * 100).toFixed(1)}%
        </div>
      `);
    });

    // Actualizar cuadros inferiores y laterales
    renderLowStations();
    renderStationList();

  } catch (err) {
    console.error("❌ Error al cargar estaciones:", err);
  }
}

// 📋 Lista de estaciones con pocas bicis
function renderLowStations() {
  const lowList = document.getElementById('low-list');
  lowList.innerHTML = '';

  const lowStations = stationData.filter(s => s.free_bikes <= 5);
  const donors = stationData.filter(s => s.free_bikes >= 10);

  if (lowStations.length === 0) {
    lowList.innerHTML = '<li>✅ Todas las estaciones tienen suficientes bicicletas.</li>';
    return;
  }

  lowStations.forEach(low => {
    const near = donors
      .map(d => ({ ...d, dist: getDistance(low.lat, low.lon, d.lat, d.lon) }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 3);

    const li = document.createElement('li');
    li.innerHTML = `
      <b>${low.station_name}</b> tiene ${low.free_bikes} bicicletas.<br>
      Posibles donantes: ${near.map(d => d.station_name).join(', ')}
    `;
    lowList.appendChild(li);
  });
}

// 📊 Lista inferior completa de estaciones
function renderStationList() {
  const list = document.getElementById('station-list');
  list.innerHTML = '';

  if (!stationData || stationData.length === 0) {
    list.innerHTML = '<li>No hay estaciones disponibles.</li>';
    return;
  }

  stationData.forEach(st => {
    const occ = (st.avg_occupancy * 100).toFixed(1);

    // 🧭 Buscar los 3 donantes más cercanos con >=10 bicicletas
    const donors = stationData
      .filter(d => d.free_bikes >= 10 && d.station_name !== st.station_name)
      .map(d => ({
        ...d,
        dist: getDistance(st.lat, st.lon, d.lat, d.lon)
      }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 3);

    const donorsText = donors.length > 0
      ? donors.map(d => `🚲 ${d.station_name} (${d.dist.toFixed(1)} km)`).join('<br>')
      : '—';

    // 🧱 Contenedor principal del ítem
    const li = document.createElement('li');
    li.style.display = 'flex';
    li.style.justifyContent = 'space-between';
    li.style.alignItems = 'center';

    // 📋 Info estación
    const infoDiv = document.createElement('div');
    infoDiv.style.flex = '1';
    infoDiv.style.minWidth = '220px';
    infoDiv.innerHTML = `
      <strong>${st.station_name}</strong><br>
      🚲 ${st.free_bikes ?? 'N/D'} libres | 🅿️ ${st.empty_slots ?? 'N/D'} vacíos<br>
      📦 Capacidad: ${st.capacity ?? 'N/D'} | 🔵 ${occ}% ocupación<br>
      <small><b>Donantes cercanos:</b><br>${donorsText}</small>
    `;

    // 📌 Contenedor para los botones (derecha)
    const btnContainer = document.createElement('div');
    btnContainer.style.display = 'flex';
    btnContainer.style.flexDirection = 'column';
    btnContainer.style.gap = '4px';
    btnContainer.style.marginLeft = '10px';

    // 🚴 Botón Reabastecer (solo si tiene 5 o menos bicis)
    if (st.free_bikes <= 5) {
      const btnReab = document.createElement('button');
      btnReab.textContent = 'Reab.';
      btnReab.style.fontSize = '11px';
      btnReab.style.padding = '2px 4px';
      btnReab.style.width = '70px';
      btnReab.onclick = () => startReabastecimiento(st.station_name);
      btnContainer.appendChild(btnReab);
    }

    // 🧭 Botón Ver rutas (toggle)
    const btnRutas = document.createElement('button');
    btnRutas.textContent = 'Ver rutas';
    btnRutas.style.fontSize = '11px';
    btnRutas.style.padding = '2px 4px';
    btnRutas.style.width = '70px';

    let rutasMostradas = false;
    let drawnRoutes = [];

    btnRutas.onclick = async() => {
      if (!rutasMostradas) {
        // Dibujar rutas desde donantes a esta estación
        for (const donor of donors) {
          try{
            const res=await fetch('/api/estimate_route', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({src: donor, dst: st})
            });
            const data = await res.json();
            if (data && data.geometry && data.geometry.coordinates) {
              const coords = data.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
              const routeLine = L.polyline(coords, {color: '#0077cc', weight: 3, opacity: 0.7}).addTo(map);
              drawnRoutes.push(routeLine);
            }
          }catch(err){
            console.error("❌ Error al obtener ruta:",err);
          }
        }


        rutasMostradas = true;
        btnRutas.textContent = 'Ocultar';
      } else {
        // Eliminar las rutas
        drawnRoutes.forEach(r => map.removeLayer(r));
        drawnRoutes = [];
        rutasMostradas = false;
        btnRutas.textContent = 'Ver rutas';
      }
    };

    btnContainer.appendChild(btnRutas);

    // 🧩 Unir info + botones
    li.appendChild(infoDiv);
    li.appendChild(btnContainer);
    list.appendChild(li);
  });
}


// 🧭 Calcular distancia entre estaciones
function getDistance(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) *
            Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ♻️ Redistribución simulada
async function redistributeBikes() {
  clearRoutes();
  const lowStations = stationData.filter(s => s.free_bikes <= 5);
  const donors = stationData.filter(s => s.free_bikes >= 10);

  for (const low of lowStations) {
    const closest = donors
      .map(d => ({ ...d, dist: getDistance(low.lat, low.lon, d.lat, d.lon) }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 1);

    for (const donor of closest) {
      const route = await getRoute(donor, low);
      drawRoute(route);
      animateBike(route);
    }
  }
}

// 🚴 Reabastecimiento manual
function startReabastecimiento(stationName) {
  const target = stationData.find(s => s.station_name === stationName);
  if (!target) return alert('Estación no encontrada.');
  alert(`🚴 Iniciando reabastecimiento para ${target.station_name}...`);
  redistributeSingleStation(target);
}

// ♻️ Redistribución para UNA sola estación
async function redistributeSingleStation(target) {
  clearRoutes();

  // Buscar estaciones donantes
  const donors = stationData
    .filter(s => s.free_bikes >= 10)
    .map(d => ({
      ...d,
      dist: getDistance(target.lat, target.lon, d.lat, d.lon)
    }))
    .sort((a, b) => a.dist - b.dist)
    .slice(0, 1);  // el donante más cercano

  for (const donor of donors) {
    const route = await getRoute(donor, target);
    drawRoute(route);
    animateBike(route);
  }
}



// 🧭 Obtener ruta entre estaciones (del backend)
async function getRoute(src, dst) {
  const res = await fetch('/api/estimate_route', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({src, dst})
  });
  const data = await res.json();
  return data.geometry.coordinates.map(([lon, lat]) => [lat, lon]);
}

// 🧼 Limpiar rutas previas
function clearRoutes() {
  activeRoutes.forEach(r => map.removeLayer(r));
  activeRoutes = [];
}

// ✏️ Dibujar ruta en mapa
function drawRoute(coords) {
  const line = L.polyline(coords, { color: '#3498db', weight: 4, opacity: 0.8 }).addTo(map);
  activeRoutes.push(line);
}

// 🚲 Animar bicicleta sobre la ruta
function animateBike(coords) {
  let i = 0;
  const marker = L.circleMarker(coords[0], { radius: 5, color: 'red', fillColor: 'red' }).addTo(map);

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

// 🔄 Verificación periódica de redistribución
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

      const li = document.createElement('li');
      li.innerHTML = `
        <strong>${target.station_name}</strong> (${target.free_bikes} bicicletas)<br>
        Donantes:<ul>
        ${donors.map(d => `<li>🚲 ${d.donor_name} → ${d.distance_km} km (${d.duration_min} min)</li>`).join('')}
        </ul>
      `;
      list.appendChild(li);
    });
  } catch (err) {
    console.error("❌ Error en redistribución:", err);
  }
}

function logout() {
  localStorage.removeItem('loggedIn'); // ❌ elimina la sesión
  window.location.href = '/login';     // 🔁 redirige al login
}
