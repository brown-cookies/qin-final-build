// The only place route colors are defined; label is the legend text.
const COLORS = {
  yellow: { hex: "#FACC15", label: "Yellow" },
  blue: { hex: "#0052B4", label: "Blue" },
  purple: { hex: "#6A1B9A", label: "Purple" },
  grey: { hex: "#757575", label: "Grey" },
  red: { hex: "#D32F2F", label: "Red" },
  darkyellow: { hex: "#B8860B", label: "Dark yellow" },
};

const FAILED_MESSAGE =
  "We couldn't load the jeepney routes. Check your connection and refresh the page.";
const EMPTY_MESSAGE = "No route data is available.";

const map = L.map("map").setView([15.145, 120.595], 13);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '<a href="https://www.openstreetmap.org/copyright">(c) OpenStreetMap contributors</a>',
}).addTo(map);

function showBanner(text) {
  const banner = document.getElementById("banner");
  banner.textContent = text;
  banner.hidden = false;
}

function renderLegend() {
  const legend = document.getElementById("legend");
  for (const { hex, label } of Object.values(COLORS)) {
    const row = document.createElement("div");
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = hex;
    row.appendChild(swatch);
    row.appendChild(document.createTextNode(label));
    legend.appendChild(row);
  }
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(url + " returned " + res.status);
  return res.json();
}

// GeoJSON is [lng, lat]; Leaflet wants [lat, lng].
function toLatLng(coord) {
  return [coord[1], coord[0]];
}

function drawRoute(color, collection, lines) {
  const hex = COLORS[color].hex;
  const seen = new Set();
  for (const feature of collection.features) {
    if (feature.geometry.type === "LineString") {
      const line = L.polyline(feature.geometry.coordinates.map(toLatLng), {
        color: hex,
        weight: 5,
        opacity: 0.85,
      }).addTo(map);
      lines.push(line);
    } else if (feature.geometry.type === "Point") {
      // Circular routes list a shared stop twice; draw it once per route.
      const name = feature.properties.name;
      if (seen.has(name)) continue;
      seen.add(name);
      L.circleMarker(toLatLng(feature.geometry.coordinates), {
        radius: 5,
        color: "#222",
        weight: 1,
        fillColor: hex,
        fillOpacity: 1,
      })
        .bindPopup(name)
        .addTo(map);
    }
  }
}

async function load() {
  let routes;
  let details;
  try {
    routes = await getJson("/api/routes");
    if (routes.length === 0) {
      showBanner(EMPTY_MESSAGE);
      return;
    }
    details = await Promise.all(
      routes.map((r) => getJson("/api/routes/" + encodeURIComponent(r.route_id)))
    );
  } catch (err) {
    console.error(err);
    showBanner(FAILED_MESSAGE);
    return;
  }

  // Draw only after every request succeeded, so a failure never leaves a partial map.
  const lines = [];
  routes.forEach((r, i) => drawRoute(r.color, details[i], lines));
  map.fitBounds(L.featureGroup(lines).getBounds());
}

renderLegend();
load();
