const logEl = document.getElementById("log");
const statusEl = document.getElementById("status");
const winnerNameEl = document.getElementById("winnerName");
const winnerScoreEl = document.getElementById("winnerScore");
const winnerCountEl = document.getElementById("winnerCount");

const map = L.map("map", { zoomControl: true }).setView([20, 0], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const markerGroup = L.layerGroup().addTo(map);

const solarIcon = L.divIcon({
  className: "solar-marker",
  html: "<div class=\"panel\"></div>",
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

function log(message) {
  logEl.textContent += `${message}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

function clearLog() {
  logEl.textContent = "";
}

function setStatus(message) {
  statusEl.textContent = message;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  return response.json();
}

function updateWinner(comparison) {
  winnerNameEl.textContent = comparison.winner || "--";
  winnerScoreEl.textContent = comparison.winner_score
    ? comparison.winner_score.toFixed(4)
    : "--";
  winnerCountEl.textContent = comparison.winner_locations
    ? comparison.winner_locations.length
    : 0;
}

function plotWinnerLocations(locations) {
  markerGroup.clearLayers();
  if (!locations || !locations.length) {
    return;
  }

  const bounds = [];
  locations.forEach((loc) => {
    const marker = L.marker([loc.lat, loc.lon], { icon: solarIcon });
    marker.bindPopup(
      `Lat: ${loc.lat}<br>Lon: ${loc.lon}<br>Score: ${loc.solar_score}`
    );
    marker.addTo(markerGroup);
    bounds.push([loc.lat, loc.lon]);
  });

  map.fitBounds(bounds, { padding: [30, 30] });
}

async function handleRun(url, label, payload) {
  setStatus(`Running ${label}...`);
  log(`\n== ${label} ==`);
  try {
    const data = await postJson(url, payload);
    if (!data.ok) {
      log(`Error: ${data.error || "Unknown error"}`);
      if (data.stderr) {
        log(data.stderr);
      }
      setStatus(`Failed: ${label}`);
      return;
    }
    if (data.stdout) {
      log(data.stdout);
    }
    if (data.stderr) {
      log(data.stderr);
    }
    if (data.elapsed) {
      log(`Finished in ${data.elapsed}s`);
    }
    setStatus(`Done: ${label}`);
  } catch (err) {
    log(`Error: ${err}`);
    setStatus(`Failed: ${label}`);
  }
}

const runAllBtn = document.getElementById("runAllBtn");
const countryInput = document.getElementById("countryInput");

async function runAll() {
  const country = document.getElementById("countryInput").value.trim();
  if (!country) {
    setStatus("Country required");
    log("\nError: Please enter a country.");
    return;
  }

  runAllBtn.disabled = true;
  setStatus(`Running: ${country} (this can take a few minutes)`);
  clearLog();
  markerGroup.clearLayers();
  updateWinner({});
  log("\n== Full Pipeline ==");
  const data = await postJson("/run/all", { country });
  if (!data.ok) {
    log(`Error: ${data.error || "Unknown error"}`);
    if (data.stderr) {
      log(data.stderr);
    }
    setStatus("Run failed");
    runAllBtn.disabled = false;
    return;
  }

  const steps = data.steps || {};
  const ordered = ["data", "ga", "pso", "sa"];
  ordered.forEach((key) => {
    const step = steps[key];
    if (!step) {
      return;
    }
    log(`\n== ${key.toUpperCase()} ==`);
    if (step.stdout) {
      log(step.stdout);
    }
    if (step.stderr) {
      log(step.stderr);
    }
    if (step.elapsed) {
      log(`Finished in ${step.elapsed}s`);
    }
  });

  updateWinner(data.comparison);
  plotWinnerLocations(data.comparison.winner_locations);
  setStatus(`Done: ${data.country}`);
  runAllBtn.disabled = false;
}

runAllBtn.addEventListener("click", runAll);
countryInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    runAll();
  }
});
