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

const NOTICE_MS = 5000;
const INCOMPLETE_MESSAGE = "Incomplete origin and destination selection.";
const NO_MATCH_MESSAGE = "No match found";
const PENDING_MESSAGE = "Finding route…";
const INTERNAL_MESSAGE = "Something went wrong. Please try again.";
const NETWORK_MESSAGE = "Network failure. Refresh the page and try again.";
const PLAN_ERRORS = {
  invalid_location: "That location is outside the service area.",
  no_stop_nearby: "No stops nearby.",
  no_route: "No route found.",
  validation_error: "The request wasn't valid. Please try again.",
  route_data_unavailable: "No available routes.",
  route_not_found: "Route doesn't exist.",
  internal_error: INTERNAL_MESSAGE,
};

const map = L.map("map").setView([15.145, 120.595], 13);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '<a href="https://www.openstreetmap.org/copyright">(c) OpenStreetMap contributors</a>',
}).addTo(map);

let bannerTimer = null;

function showBanner(text) {
  const banner = document.getElementById("banner");
  banner.textContent = text;
  banner.hidden = false;
}

// Only these banners expire; the map-load messages stay until refresh.
function showTimedBanner(text) {
  showBanner(text);
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(clearTimedBanner, NOTICE_MS);
}

function clearTimedBanner() {
  if (bannerTimer === null) return;
  clearTimeout(bannerTimer);
  bannerTimer = null;
  document.getElementById("banner").hidden = true;
}

let messageTimer = null;

function showPanelMessage(text, expires) {
  const el = document.getElementById("panel-message");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(messageTimer);
  if (expires) messageTimer = setTimeout(clearPanelMessage, NOTICE_MS);
}

function clearPanelMessage() {
  clearTimeout(messageTimer);
  document.getElementById("panel-message").hidden = true;
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

// Served from the vendored web/images/, not auto-detected from the CSS.
L.Icon.Default.prototype.options.imagePath = "/images/";

const points = [];
const pointMarkers = [];
const routeRecords = [];
const highlightLayers = [];
// Taps are ignored while a request is pending and after any result, until Reset.
let locked = false;

const findButton = document.getElementById("find-route");
const resetButton = document.getElementById("reset");

function updatePrompt() {
  const prompt = document.getElementById("prompt");
  prompt.hidden = locked || points.length >= 2;
  prompt.textContent =
    points.length === 0
      ? "Tap the map to set your origin"
      : "Tap the map to set your destination";
}

// Origin first, then destination.
function setPoint(latlng) {
  if (locked || points.length >= 2) return;
  points.push(latlng);
  pointMarkers.push(L.marker(latlng).addTo(map));
  updatePrompt();
}

function resetPoints() {
  pointMarkers.forEach((m) => m.remove());
  pointMarkers.length = 0;
  points.length = 0;
  locked = false;
  updatePrompt();
}

map.on("click", (e) => setPoint(e.latlng));

function project(latlng) {
  return map.options.crs.project(L.latLng(latlng));
}

// Distances are measured in projected space, which is zoom independent.
function nearestOnLine(record, latlng, preferLast) {
  const p = project(latlng);
  let best = null;
  for (let i = 0; i < record.proj.length - 1; i++) {
    const c = L.LineUtil.closestPointOnSegment(p, record.proj[i], record.proj[i + 1]);
    const dist = p.distanceTo(c);
    // A circular route's repeated end stop must land at the end of the line.
    const better = preferLast
      ? !best || dist <= best.dist + 1e-3
      : !best || dist < best.dist;
    if (better) {
      best = { dist, seg: i, point: c, len: record.cum[i] + record.proj[i].distanceTo(c) };
    }
  }
  return best;
}

function buildRecord(route, collection) {
  const lineFeature = collection.features.find((f) => f.geometry.type === "LineString");
  const line = lineFeature.geometry.coordinates.map(toLatLng);
  const proj = line.map(project);
  const cum = [0];
  for (let i = 1; i < proj.length; i++) cum.push(cum[i - 1] + proj[i - 1].distanceTo(proj[i]));
  const record = {
    route_id: route.route_id,
    color: route.color,
    direction: route.direction,
    line,
    proj,
    cum,
    stops: [],
    lines: [],
    dots: new Map(),
  };
  const pointFeatures = collection.features
    .filter((f) => f.geometry.type === "Point")
    .sort((a, b) => a.properties.seq - b.properties.seq);
  const names = new Set();
  for (const f of pointFeatures) {
    const name = f.properties.name;
    const latlng = toLatLng(f.geometry.coordinates);
    record.stops.push({ name, latlng, pos: nearestOnLine(record, latlng, names.has(name)) });
    names.add(name);
  }
  return record;
}

function drawLine(hex, feature, record, lines) {
  const line = L.polyline(feature.geometry.coordinates.map(toLatLng), {
    color: hex,
    weight: 5,
    opacity: 0.85,
  }).addTo(map);
  lines.push(line);
  record.lines.push(line);
}

function drawStopDot(hex, feature, record) {
  // Circular routes list a shared stop twice; draw it once per route.
  const name = feature.properties.name;
  if (record.dots.has(name)) return;
  const latlng = toLatLng(feature.geometry.coordinates);
  const dot = L.circleMarker(latlng, {
    radius: 5,
    color: "#222",
    weight: 1,
    fillColor: hex,
    fillOpacity: 1,
  })
    .bindPopup(name, { closeButton: false })
    .addTo(map);
  dot.on("mouseover", () => dot.openPopup());
  dot.on("mouseout", () => dot.closePopup());
  dot.on("click", (e) => {
    // Stop here so the map click handler does not count the tap twice.
    L.DomEvent.stopPropagation(e);
    setPoint(L.latLng(latlng));
  });
  record.dots.set(name, dot);
}

function drawRoute(route, collection, lines) {
  const hex = COLORS[route.color].hex;
  const record = buildRecord(route, collection);
  for (const feature of collection.features) {
    if (feature.geometry.type === "LineString") drawLine(hex, feature, record, lines);
    else if (feature.geometry.type === "Point") drawStopDot(hex, feature, record);
  }
  routeRecords.push(record);
}

function setRoutesVisible(visible) {
  for (const record of routeRecords) {
    const layers = [...record.lines, ...record.dots.values()];
    layers.forEach((layer) => (visible ? layer.addTo(map) : layer.remove()));
  }
}

function clearHighlight() {
  highlightLayers.forEach((layer) => layer.remove());
  highlightLayers.length = 0;
  setRoutesVisible(true);
}

function findStopIndexes(record, name) {
  const found = [];
  record.stops.forEach((s, i) => {
    if (s.name === name) found.push(i);
  });
  return found;
}

// Returns null for an unmatched or wraparound ride.
function matchRide(step) {
  const record = routeRecords.find(
    (r) => r.color === step.color && r.direction === step.direction
  );
  if (!record) return null;
  let best = null;
  for (const i of findStopIndexes(record, step.from)) {
    for (const j of findStopIndexes(record, step.to)) {
      const gap = Math.abs(record.stops[i].pos.len - record.stops[j].pos.len);
      if (!best || gap < best.gap) best = { i, j, gap };
    }
  }
  if (!best || best.j < best.i) return null;
  return { record, from: record.stops[best.i], to: record.stops[best.j] };
}

function segmentLatLngs(record, a, b) {
  const [lo, hi] = a.pos.len <= b.pos.len ? [a.pos, b.pos] : [b.pos, a.pos];
  const inner = record.proj.slice(lo.seg + 1, hi.seg + 1);
  return [lo.point, ...inner, hi.point].map((p) => map.options.crs.unproject(p));
}

// Returns false (and changes nothing) if any ride cannot be matched.
function applyHighlight(plan) {
  const rides = plan.steps.filter((s) => s.type === "ride");
  if (rides.length === 0) return true;
  const matches = rides.map(matchRide);
  if (matches.includes(null)) return false;

  setRoutesVisible(false);
  for (const m of matches) {
    const segment = L.polyline(segmentLatLngs(m.record, m.from, m.to), {
      color: COLORS[m.record.color].hex,
      weight: 8,
      opacity: 1,
    }).addTo(map);
    highlightLayers.push(segment);
  }
  for (const m of matches) {
    m.record.dots.get(m.from.name).addTo(map);
    m.record.dots.get(m.to.name).addTo(map);
  }
  map.fitBounds(L.featureGroup(highlightLayers).getBounds());
  return true;
}

function tint(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return "rgba(" + r + ", " + g + ", " + b + ", 0.5)";
}

function stepText(step) {
  if (step.type === "walk") {
    return "Walk " + Math.round(step.distance_m) + " m to " + step.to;
  }
  if (step.type === "ride") {
    const stops = step.stops_passed === 1 ? "1 stop" : step.stops_passed + " stops";
    const km = Number((step.distance_m / 1000).toFixed(2));
    return (
      "Ride " + COLORS[step.color].label + " from " + step.from + " to " + step.to +
      " (" + stops + ", " + km + " km)"
    );
  }
  const text = "Transfer to " + COLORS[step.to_color].label + " at " + step.from;
  return step.walk_m > 0 ? text + " (walk " + Math.round(step.walk_m) + " m)" : text;
}

function renderPlan(plan) {
  const list = document.getElementById("steps");
  for (const step of plan.steps) {
    const item = document.createElement("li");
    item.textContent = stepText(step);
    if (step.type === "ride") item.style.background = tint(COLORS[step.color].hex);
    list.appendChild(item);
  }
  document.getElementById("summary").textContent = plan.summary;
}

function clearPlanView() {
  document.getElementById("steps").replaceChildren();
  document.getElementById("summary").textContent = "";
}

async function errorText(res) {
  try {
    const body = await res.json();
    return Object.hasOwn(PLAN_ERRORS, body.error) ? PLAN_ERRORS[body.error] : INTERNAL_MESSAGE;
  } catch (err) {
    return INTERNAL_MESSAGE;
  }
}

// Resolves to { plan } or { error }; never rejects.
async function requestPlan() {
  const [from, to] = points;
  const query = new URLSearchParams({
    from_lat: from.lat,
    from_lng: from.lng,
    to_lat: to.lat,
    to_lng: to.lng,
  });
  try {
    const res = await fetch("/api/plan?" + query);
    if (res.ok) return { plan: await res.json() };
    return { error: await errorText(res) };
  } catch (err) {
    console.error(err);
    return { error: NETWORK_MESSAGE };
  }
}

function setPending(pending) {
  findButton.disabled = pending;
  resetButton.disabled = pending;
  if (pending) {
    locked = true;
    updatePrompt();
    showPanelMessage(PENDING_MESSAGE, false);
  } else {
    clearPanelMessage();
  }
}

function clearTrip() {
  clearTimedBanner();
  clearPanelMessage();
  clearPlanView();
  clearHighlight();
}

async function findRoute() {
  clearTrip();
  if (points.length < 2) {
    showTimedBanner(INCOMPLETE_MESSAGE);
    return;
  }
  setPending(true);
  const result = await requestPlan();
  setPending(false);
  if (result.error) {
    showTimedBanner(result.error);
    return;
  }
  renderPlan(result.plan);
  findButton.disabled = true;
  if (!applyHighlight(result.plan)) {
    showPanelMessage(NO_MATCH_MESSAGE, true);
    findButton.disabled = false;
  }
}

function resetAll() {
  clearTrip();
  resetPoints();
  findButton.disabled = false;
}

findButton.addEventListener("click", findRoute);
resetButton.addEventListener("click", resetAll);

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
  routes.forEach((r, i) => drawRoute(r, details[i], lines));
  map.fitBounds(L.featureGroup(lines).getBounds());
}

updatePrompt();
renderLegend();
load();
