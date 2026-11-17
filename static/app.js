"use strict";

const TOKEN_KEY = "obratrack_token";

const state = {
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  devices: [],
  selectedId: null,
  alertsState: "open",
  formDeviceId: null,
  map: null,
  markerLayer: null,
  geofenceLayer: null,
  trailLayer: null,
  pollId: null,
  busy: false,
};

const $ = (selector) => document.querySelector(selector);

/* ------------------------------- Utilidades ------------------------------- */

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function timeAgo(iso) {
  if (!iso) return "sin datos";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `hace ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  return `hace ${Math.floor(hours / 24)} d`;
}

function formatDateTime(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(iso));
}

let toastTimer = null;
function toast(message, type = "") {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast ${type}`.trim();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.add("hidden"), 4000);
}

async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && state.token) {
    logout();
    throw new Error("Tu sesión expiró, inicia sesión de nuevo");
  }

  let data = null;
  if (response.status !== 204) {
    data = await response.json().catch(() => null);
  }

  if (!response.ok) {
    let message = `Error ${response.status}`;
    if (data && typeof data.detail === "string") {
      message = data.detail;
    } else if (data && Array.isArray(data.detail)) {
      message = data.detail.map((item) => item.msg).join(". ");
    }
    throw new Error(message);
  }
  return data;
}

/* --------------------------------- Acceso --------------------------------- */

let authMode = "login";

function setAuthMode(mode) {
  authMode = mode;
  const registering = mode === "register";
  $("#auth-title").textContent = registering ? "Crear cuenta" : "Iniciar sesión";
  $("#auth-submit").textContent = registering ? "Crear cuenta" : "Entrar";
  $("#name-field").classList.toggle("hidden", !registering);
  $("#auth-name").required = registering;
  $("#auth-password").minLength = registering ? 8 : 1;
  $("#auth-switch-text").textContent = registering ? "¿Ya tienes cuenta?" : "¿No tienes cuenta?";
  $("#auth-toggle").textContent = registering ? "Inicia sesión" : "Crear una";
}

async function handleAuth(event) {
  event.preventDefault();
  const submit = $("#auth-submit");
  const email = $("#auth-email").value.trim();
  const password = $("#auth-password").value;
  const name = $("#auth-name").value.trim();

  submit.disabled = true;
  try {
    if (authMode === "register") {
      await api("/api/auth/register", { method: "POST", body: { email, password, name } });
      toast("Cuenta creada, iniciando sesión…", "ok");
    }
    const data = await api("/api/auth/login", { method: "POST", body: { email, password } });
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem(TOKEN_KEY, state.token);
    await enterApp();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    submit.disabled = false;
  }
}

function logout() {
  state.token = null;
  state.user = null;
  state.devices = [];
  state.selectedId = null;
  state.formDeviceId = null;
  clearInterval(state.pollId);
  state.pollId = null;
  localStorage.removeItem(TOKEN_KEY);

  clearSelectedLayers();
  if (state.markerLayer) state.markerLayer.clearLayers();
  $("#app-view").classList.add("hidden");
  $("#auth-view").classList.remove("hidden");
  $("#auth-password").value = "";
}

async function enterApp() {
  if (!state.user) state.user = await api("/api/auth/me");
  $("#user-name").textContent = state.user.name;
  $("#auth-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");

  initMap();
  await refreshAll();
  if (state.token) startPolling();
}

/* ---------------------------------- Mapa ---------------------------------- */

function initMap() {
  if (state.map) {
    setTimeout(() => state.map.invalidateSize(), 60);
    return;
  }
  if (!window.L) {
    $("#map").innerHTML =
      '<p style="padding:1rem;color:#8da2bd">No se pudo cargar Leaflet. Revisa la conexión a internet.</p>';
    return;
  }

  state.map = L.map("map").setView([4.60971, -74.08175], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(state.map);

  state.markerLayer = L.layerGroup().addTo(state.map);

  // Clic en el mapa: mueve el centro de la geocerca del dispositivo elegido.
  state.map.on("click", (event) => {
    if (!state.selectedId) return;
    $("#geo-lat").value = event.latlng.lat.toFixed(6);
    $("#geo-lon").value = event.latlng.lng.toFixed(6);
    toast("Centro actualizado en el formulario. Guarda para aplicarlo.");
  });

  setTimeout(() => state.map.invalidateSize(), 80);
}

function clearSelectedLayers() {
  if (!state.map) return;
  if (state.geofenceLayer) state.map.removeLayer(state.geofenceLayer);
  if (state.trailLayer) state.map.removeLayer(state.trailLayer);
  state.geofenceLayer = null;
  state.trailLayer = null;
}

function renderMarkers() {
  if (!state.map || !state.markerLayer) return;
  state.markerLayer.clearLayers();

  for (const device of state.devices) {
    if (device.last_lat == null || device.last_lon == null) continue;

    const outside = device.geofence_state === "outside";
    const color = !device.active ? "#64748b" : outside ? "#ef4444" : "#f5a524";

    const marker = L.circleMarker([device.last_lat, device.last_lon], {
      radius: device.id === state.selectedId ? 11 : 8,
      color: "#0f172a",
      weight: 2,
      fillColor: color,
      fillOpacity: 0.95,
    })
      .bindPopup(
        `<strong>${escapeHtml(device.name)}</strong><br>` +
          `${device.last_seen_at ? "Visto " + timeAgo(device.last_seen_at) : "Sin datos"}`
      )
      .on("click", () => selectDevice(device.id));

    marker.addTo(state.markerLayer);
  }
}

/* ----------------------------- Estado del panel ---------------------------- */

function statePill(device) {
  const pill = document.createElement("span");
  if (!device.geofence) {
    pill.className = "pill";
    pill.textContent = "Sin geocerca";
  } else if (device.geofence_state === "outside") {
    pill.className = "pill out";
    pill.textContent = "Fuera";
  } else if (device.geofence_state === "inside") {
    pill.className = "pill ok";
    pill.textContent = "Dentro";
  } else {
    pill.className = "pill warn";
    pill.textContent = device.geofence.enabled ? "Sin fix" : "Inactiva";
  }
  return pill;
}

function renderStats(overview) {
  $("#stat-devices").textContent = overview.devices_total;
  $("#stat-outside").textContent = overview.devices_outside;
  $("#stat-alerts").textContent = overview.alerts_open;
}

function renderDevices() {
  const list = $("#device-list");
  list.replaceChildren();
  $("#device-count").textContent = state.devices.length;

  if (!state.devices.length) {
    const empty = document.createElement("li");
    empty.className = "device-empty";
    empty.textContent = "Registra tu primera herramienta.";
    list.append(empty);
    return;
  }

  for (const device of state.devices) {
    const item = document.createElement("li");
    item.className = "device-item";
    if (device.id === state.selectedId) item.classList.add("selected");

    const left = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = device.name;
    const sub = document.createElement("small");
    sub.textContent = device.last_seen_at
      ? `Visto ${timeAgo(device.last_seen_at)}`
      : "Sin posiciones";
    left.append(name, sub);

    item.append(left, statePill(device));
    item.addEventListener("click", () => selectDevice(device.id));
    list.append(item);
  }
}

function renderAlerts(alerts) {
  const list = $("#alert-list");
  list.replaceChildren();

  if (!alerts.length) {
    const empty = document.createElement("li");
    empty.className = "alert-empty";
    empty.textContent =
      state.alertsState === "open" ? "Sin alertas abiertas." : "Todavía no hay alertas.";
    list.append(empty);
    return;
  }

  for (const alert of alerts) {
    const item = document.createElement("li");
    item.className = "alert-item";
    if (alert.resolved_at) item.classList.add("resolved");

    const message = document.createElement("p");
    message.textContent = alert.message;

    const meta = document.createElement("div");
    meta.className = "alert-meta";

    const info = document.createElement("small");
    const status = alert.resolved_at ? "Resuelta" : alert.acknowledged_at ? "Vista" : "Nueva";
    info.textContent = `${alert.device ? alert.device.name : "Equipo"} · ${status} · ${timeAgo(
      alert.created_at
    )}`;

    meta.append(info);

    if (!alert.acknowledged_at) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-ghost";
      button.textContent = "Marcar vista";
      button.addEventListener("click", () => acknowledgeAlert(alert.id));
      meta.append(button);
    }

    item.append(message, meta);
    list.append(item);
  }
}

async function acknowledgeAlert(alertId) {
  try {
    await api(`/api/alerts/${alertId}/acknowledge`, { method: "POST" });
    await refreshAll();
  } catch (error) {
    toast(error.message, "error");
  }
}

/* ------------------------------- Dispositivo ------------------------------ */

async function selectDevice(deviceId) {
  state.selectedId = deviceId;
  state.formDeviceId = null;
  $("#device-detail").classList.remove("hidden");
  renderDevices();
  renderMarkers();
  try {
    await refreshSelected(true);
  } catch (error) {
    toast(error.message, "error");
  }
}

function renderDetail(device) {
  $("#detail-name").textContent = device.name;

  const pill = $("#detail-status");
  if (device.inside_geofence === true) {
    pill.className = "pill ok";
    pill.textContent = "Dentro";
  } else if (device.inside_geofence === false) {
    pill.className = "pill out";
    pill.textContent = "Fuera";
  } else if (device.geofence) {
    pill.className = "pill warn";
    pill.textContent = device.geofence.enabled ? "Sin fix" : "Inactiva";
  } else {
    pill.className = "pill";
    pill.textContent = "Sin geocerca";
  }

  const details = [];
  if (device.last_fix_at) {
    details.push(`Fix: ${formatDateTime(device.last_fix_at)} (${timeAgo(device.last_fix_at)})`);
  }
  if (device.distance_to_center_m != null) {
    details.push(`${Math.round(device.distance_to_center_m)} m del centro`);
  }
  if (device.last_satellites != null) details.push(`${device.last_satellites} satélites`);
  if (device.last_battery_pct != null) details.push(`batería ${device.last_battery_pct}%`);
  if (device.open_alerts) details.push(`${device.open_alerts} alerta(s) abierta(s)`);
  $("#detail-meta").textContent = details.join(" · ") || "Aún no hay posiciones reportadas.";

  $("#device-token").textContent = device.token;
}

function renderGeofenceForm(device, geofence, reset) {
  if (!reset && state.formDeviceId === device.id) return;

  if (geofence) {
    $("#geo-name").value = geofence.name;
    $("#geo-radius").value = Math.round(geofence.radius_m);
    $("#geo-lat").value = geofence.center_lat;
    $("#geo-lon").value = geofence.center_lon;
    $("#geo-enabled").checked = geofence.enabled;
  } else {
    $("#geo-name").value = "Geocerca";
    $("#geo-radius").value = 150;
    const center =
      device.last_lat != null
        ? { lat: device.last_lat, lng: device.last_lon }
        : state.map
        ? state.map.getCenter()
        : { lat: 4.60971, lng: -74.08175 };
    $("#geo-lat").value = Number(center.lat).toFixed(6);
    $("#geo-lon").value = Number(center.lng).toFixed(6);
    $("#geo-enabled").checked = true;
  }

  $("#geo-delete").disabled = !geofence;
  state.formDeviceId = device.id;
}

function drawSelected(device, positions, focus) {
  if (!state.map) return;
  clearSelectedLayers();

  if (device.geofence) {
    state.geofenceLayer = L.circle(
      [device.geofence.center_lat, device.geofence.center_lon],
      {
        radius: device.geofence.radius_m,
        color: device.geofence.enabled ? "#38bdf8" : "#64748b",
        weight: 2,
        fillColor: "#38bdf8",
        fillOpacity: device.geofence.enabled ? 0.08 : 0.03,
        dashArray: "6 8",
      }
    ).addTo(state.map);
  }

  if (positions.length) {
    const points = positions
      .slice()
      .reverse()
      .filter((position) => position.lat != null && position.lon != null)
      .map((position) => [position.lat, position.lon]);

    if (points.length > 1) {
      state.trailLayer = L.polyline(points, {
        color: "#f5a524",
        weight: 3,
        opacity: 0.7,
      }).addTo(state.map);
    }

    if (focus) {
      state.map.setView(points[points.length - 1], Math.max(state.map.getZoom(), 16));
    }
  }
}

async function refreshSelected(focus) {
  const deviceId = state.selectedId;
  if (!deviceId) return;

  const [status, geofence, positions] = await Promise.all([
    api(`/api/devices/${deviceId}/status`),
    api(`/api/devices/${deviceId}/geofence`).catch(() => null),
    api(`/api/devices/${deviceId}/positions?limit=300`),
  ]);

  if (state.selectedId !== deviceId) return;

  renderDetail(status);
  renderGeofenceForm(status, geofence, focus);
  drawSelected(status, positions, focus);
}

/* --------------------------------- Acciones -------------------------------- */

async function handleDeviceCreate(event) {
  event.preventDefault();
  const input = $("#new-device-name");
  const name = input.value.trim();
  if (!name) return;

  const button = event.target.querySelector("button");
  button.disabled = true;
  try {
    const device = await api("/api/devices", { method: "POST", body: { name } });
    input.value = "";
    toast("Herramienta creada. Copia el token para configurar la ESP32.", "ok");
    await refreshAll();
    await selectDevice(device.id);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function handleGeofenceSave(event) {
  event.preventDefault();
  if (!state.selectedId) return;

  const body = {
    name: $("#geo-name").value.trim() || "Geocerca",
    center_lat: Number($("#geo-lat").value),
    center_lon: Number($("#geo-lon").value),
    radius_m: Number($("#geo-radius").value),
    enabled: $("#geo-enabled").checked,
  };

  if (
    !Number.isFinite(body.center_lat) ||
    !Number.isFinite(body.center_lon) ||
    !Number.isFinite(body.radius_m) ||
    body.radius_m <= 0
  ) {
    toast("Completa latitud, longitud y un radio mayor que cero", "error");
    return;
  }

  const button = $("#geo-save");
  button.disabled = true;
  try {
    await api(`/api/devices/${state.selectedId}/geofence`, {
      method: "PUT",
      body,
    });
    state.formDeviceId = null;
    toast("Geocerca guardada", "ok");
    await refreshAll();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function handleGeofenceDelete() {
  if (!state.selectedId) return;
  if (!confirm("¿Eliminar la geocerca de esta herramienta?")) return;

  const button = $("#geo-delete");
  button.disabled = true;
  try {
    await api(`/api/devices/${state.selectedId}/geofence`, { method: "DELETE" });
    state.formDeviceId = null;
    toast("Geocerca eliminada", "ok");
    await refreshAll();
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
  }
}

function useDevicePosition() {
  const device = state.devices.find((item) => item.id === state.selectedId);
  if (!device || device.last_lat == null) {
    toast("La herramienta todavía no tiene una posición", "error");
    return;
  }
  $("#geo-lat").value = Number(device.last_lat).toFixed(6);
  $("#geo-lon").value = Number(device.last_lon).toFixed(6);
  toast("Centro tomado de la última posición.");
}

function useMapCenter() {
  if (!state.map) return;
  const center = state.map.getCenter();
  $("#geo-lat").value = center.lat.toFixed(6);
  $("#geo-lon").value = center.lng.toFixed(6);
  toast("Centro tomado del mapa.");
}

async function copyToken() {
  const token = $("#device-token").textContent.trim();
  if (!token) return;
  try {
    await navigator.clipboard.writeText(token);
    toast("Token copiado al portapapeles", "ok");
  } catch {
    toast("No se pudo copiar automáticamente; selecciona el token manualmente", "error");
  }
}

/* ----------------------------------- Poll ---------------------------------- */

async function refreshAll() {
  if (!state.token || state.busy) return;
  state.busy = true;

  try {
    const [devices, overview, alerts] = await Promise.all([
      api("/api/devices"),
      api("/api/overview"),
      api(`/api/alerts?state=${state.alertsState}&limit=50`),
    ]);

    state.devices = devices;
    renderStats(overview);
    renderDevices();
    renderAlerts(alerts);
    renderMarkers();

    if (state.selectedId && !devices.some((device) => device.id === state.selectedId)) {
      state.selectedId = null;
      state.formDeviceId = null;
      $("#device-detail").classList.add("hidden");
      clearSelectedLayers();
    }

    if (state.selectedId) await refreshSelected(false);
  } catch (error) {
    if (state.token) toast(error.message, "error");
  } finally {
    state.busy = false;
  }
}

function startPolling() {
  clearInterval(state.pollId);
  state.pollId = setInterval(() => {
    if (!document.hidden) refreshAll();
  }, 5000);
}

/* --------------------------------- Arranque -------------------------------- */

function wireEvents() {
  $("#auth-form").addEventListener("submit", handleAuth);
  $("#auth-toggle").addEventListener("click", (event) => {
    event.preventDefault();
    setAuthMode(authMode === "login" ? "register" : "login");
  });
  $("#logout-btn").addEventListener("click", logout);
  $("#device-form").addEventListener("submit", handleDeviceCreate);
  $("#geofence-form").addEventListener("submit", handleGeofenceSave);
  $("#geo-delete").addEventListener("click", handleGeofenceDelete);
  $("#geo-from-device").addEventListener("click", useDevicePosition);
  $("#geo-from-map").addEventListener("click", useMapCenter);
  $("#copy-token").addEventListener("click", copyToken);

  document.querySelectorAll(".segmented-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.alertsState = button.dataset.state;
      document
        .querySelectorAll(".segmented-btn")
        .forEach((item) => item.classList.toggle("active", item === button));
      refreshAll();
    });
  });

  window.addEventListener("resize", () => {
    if (state.map) state.map.invalidateSize();
  });
}

async function boot() {
  setAuthMode("login");
  wireEvents();
  if (!state.token) return;

  try {
    state.user = await api("/api/auth/me");
    await enterApp();
  } catch (error) {
    logout();
    if (!/sesión expiró|inválido|Debes iniciar sesión/i.test(error.message)) {
      toast(error.message, "error");
    }
  }
}

boot();
