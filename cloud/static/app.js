const byId = id => document.getElementById(id);
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed: ${response.status}`);
  return body;
}

function toast(text, error = false) {
  const element = byId("toast");
  element.textContent = text;
  element.className = `toast show${error ? " error" : ""}`;
  setTimeout(() => element.className = "toast", 2800);
}

function setBusy(busy) {
  document.querySelectorAll("[data-image]").forEach(item => item.disabled = busy);
  byId("image-upload").disabled = busy;
  byId("drop-zone").classList.toggle("busy", busy);
}

async function loadImages() {
  const data = await api("/api/images");
  byId("image-list").innerHTML = data.images.map(image => `
    <article class="image-card">
      <img src="${escapeHtml(image.url)}" alt="${escapeHtml(image.title)}">
      <div><h3>${escapeHtml(image.title)}</h3><p>${escapeHtml(image.description)}</p>
      <button data-image="${escapeHtml(image.key)}">Run detection</button></div>
    </article>`).join("");
  document.querySelectorAll("[data-image]").forEach(button => {
    button.addEventListener("click", () => runImage(button));
  });
}

async function runImage(button) {
  setBusy(true);
  try {
    await api("/api/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({image: button.dataset.image})
    });
    toast(`${button.closest(".image-card").querySelector("h3").textContent} sent through MQTT`);
    setTimeout(refreshEvents, 700);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function uploadImage(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    toast("Choose a JPG, PNG, or WebP image", true);
    return;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    toast("Image is too large. Maximum size is 8 MB.", true);
    return;
  }

  const form = new FormData();
  form.append("image", file);
  setBusy(true);
  try {
    const result = await api("/api/upload", {method: "POST", body: form});
    toast(`${result.image_name} uploaded and sent through MQTT`);
    setTimeout(refreshEvents, 700);
  } catch (error) {
    toast(error.message, true);
  } finally {
    setBusy(false);
    byId("image-upload").value = "";
  }
}

function configureDropZone() {
  const zone = byId("drop-zone");
  const input = byId("image-upload");
  input.addEventListener("change", () => uploadImage(input.files[0]));

  ["dragenter", "dragover"].forEach(name => zone.addEventListener(name, event => {
    event.preventDefault();
    if (!input.disabled) zone.classList.add("dragging");
  }));
  ["dragleave", "drop"].forEach(name => zone.addEventListener(name, event => {
    event.preventDefault();
    zone.classList.remove("dragging");
  }));
  zone.addEventListener("drop", event => {
    if (!input.disabled) uploadImage(event.dataTransfer.files[0]);
  });
}

function showLatest(event) {
  byId("latest").classList.remove("hidden");
  byId("input-image").src = event.image_url;
  byId("result-image").src = `data:image/jpeg;base64,${event.annotated_image}`;
  byId("edge-result").textContent = `${event.edge_summary} (${event.edge_detections.length} boxes)`;
  byId("final-result").textContent = `${event.final_summary} (${event.final_detections.length} boxes)`;
  byId("location").textContent = event.execution_location;
  byId("reason").textContent = event.reason;
  byId("result-caption").textContent = `${event.execution_location === "cloud" ? "Cloud YOLO11m" : "Edge YOLO11n"} result`;
  byId("latest-alert").textContent = event.alert ? "SECURITY ALERT" : "NO ALERT";
  byId("latest-alert").className = event.alert ? "alert" : "safe";
}

function renderEvents(events) {
  if (!events.length) {
    byId("events").innerHTML = '<tr><td colspan="7" class="empty">No detections yet.</td></tr>';
    byId("logs").textContent = "Waiting for an RGB image event...";
    byId("latest").classList.add("hidden");
    return;
  }
  showLatest(events[0]);
  byId("events").innerHTML = events.map(event => `
    <tr>
      <td>${new Date(event.received_at).toLocaleTimeString()}</td>
      <td>${escapeHtml(event.zone || "north-gate")}</td>
      <td>${escapeHtml(event.image_name)}</td>
      <td>${escapeHtml(event.edge_summary)}</td>
      <td><span class="result ${event.alert ? "danger" : ""}">${escapeHtml(event.final_summary)}</span></td>
      <td>${escapeHtml(event.execution_location)}</td>
      <td>${(Number(event.edge_latency_ms) + Number(event.cloud_latency_ms)).toFixed(0)} ms</td>
    </tr>`).join("");
  byId("logs").textContent = events.slice().reverse().map(event => {
    const time = new Date(event.received_at).toLocaleTimeString();
    return `[${time}] ${event.zone || "north-gate"} | ${event.image_name} | edge=${event.edge_summary} | ${event.execution_location}=${event.final_summary}${event.alert ? " | ALERT" : ""}`;
  }).join("\n");
  byId("logs").scrollTop = byId("logs").scrollHeight;
}

async function refreshEvents() {
  try {
    renderEvents((await api("/api/events?limit=12")).events);
  } catch (error) {
    console.error(error);
  }
}

function renderVibrationEvents(events) {
  if (!events.length) {
    byId("vibration-events").innerHTML = '<tr><td colspan="7" class="empty">Waiting for vibration windows...</td></tr>';
    return;
  }
  byId("vibration-events").innerHTML = events.map(event => `
    <tr>
      <td>${new Date(event.received_at).toLocaleTimeString()}</td>
      <td>${escapeHtml(event.zone || "north-gate")}</td>
      <td><span class="result ${event.alert ? "danger" : ""}">${escapeHtml(event.classification)}</span></td>
      <td>${(Number(event.confidence) * 100).toFixed(1)}%</td>
      <td>${Number(event.rms_g).toFixed(4)} g</td>
      <td>${Number(event.peak_g).toFixed(4)} g</td>
      <td>${Number(event.latency_ms).toFixed(2)} ms</td>
    </tr>`).join("");
}

async function refreshVibrationEvents() {
  try {
    renderVibrationEvents((await api("/api/vibration-events?limit=12")).events);
  } catch (error) {
    console.error(error);
  }
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    const online = data.mqtt_broker.status === "ok"
      && data.edge.status === "online"
      && data.vibration_edge.status === "online";
    byId("status").textContent = online
      ? `ONLINE | ${data.edge.model} camera | ${data.vibration_edge.model} vibration | ${data.cloud.model} cloud`
      : "WAITING FOR EDGE DEVICES";
    byId("status").className = `status ${online ? "online" : "waiting"}`;
  } catch {
    byId("status").textContent = "APPLICATION OFFLINE";
  }
}

byId("clear").addEventListener("click", async () => {
  await api("/api/reset", {method: "POST"});
  await refreshEvents();
  await refreshVibrationEvents();
});

configureDropZone();
loadImages().catch(error => toast(error.message, true));
refreshStatus();
refreshEvents();
refreshVibrationEvents();
setInterval(refreshStatus, 3000);
setInterval(refreshEvents, 2000);
setInterval(refreshVibrationEvents, 2000);
