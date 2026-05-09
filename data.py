import os
import requests
import numpy as np
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from global_land_mask import globe
import geopandas as gpd
from shapely.geometry import Point

# ─────────────────────────────────────────────
# COUNTRY FALLBACKS
# ─────────────────────────────────────────────

COUNTRY_FALLBACKS = {
    "pakistan":       {"lat_min": 23.5, "lat_max": 37.0, "lon_min": 60.5, "lon_max": 77.5},
    "india":          {"lat_min":  8.0, "lat_max": 37.0, "lon_min": 68.0, "lon_max": 97.5},
    "saudi arabia":   {"lat_min": 16.0, "lat_max": 32.5, "lon_min": 34.5, "lon_max": 56.0},
    "australia":      {"lat_min":-43.5, "lat_max":-10.5, "lon_min":113.0, "lon_max":154.0},
    "usa":            {"lat_min": 24.5, "lat_max": 49.5, "lon_min":-125.0, "lon_max":-66.0},
    "united states":  {"lat_min": 24.5, "lat_max": 49.5, "lon_min":-125.0, "lon_max":-66.0},
    "china":          {"lat_min": 18.0, "lat_max": 53.5, "lon_min": 73.5, "lon_max":135.0},
    "egypt":          {"lat_min": 22.0, "lat_max": 31.5, "lon_min": 25.0, "lon_max": 37.0},
    "nigeria":        {"lat_min":  4.0, "lat_max": 14.0, "lon_min":  2.5, "lon_max": 15.0},
    "brazil":         {"lat_min":-33.5, "lat_max":  5.5, "lon_min":-74.0, "lon_max":-34.5},
    "germany":        {"lat_min": 47.0, "lat_max": 55.5, "lon_min":  5.5, "lon_max": 15.5},
    "uk":             {"lat_min": 49.5, "lat_max": 61.0, "lon_min": -8.5, "lon_max":  2.0},
    "united kingdom": {"lat_min": 49.5, "lat_max": 61.0, "lon_min": -8.5, "lon_max":  2.0},
    "iran":           {"lat_min": 25.0, "lat_max": 39.5, "lon_min": 44.0, "lon_max": 63.5},
    "turkey":         {"lat_min": 36.0, "lat_max": 42.5, "lon_min": 26.0, "lon_max": 45.0},
}

MIN_BBOX_SIZE = 1.0  # country bbox must be at least 1 degree wide


# ─────────────────────────────────────────────
# STEP 1: Get bounding box for a country
# ─────────────────────────────────────────────

def get_country_bbox(country_name):
    """
    Get bounding box for a country from Nominatim.
    Filters to country-level results only.
    Falls back to hardcoded values if needed.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": country_name,
            "format": "json",
            "limit": 10,
            "addressdetails": 1,
            "featuretype": "country",
        }
        headers = {"User-Agent": "solar-panel-optimizer/1.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        results = r.json()

        for res in results:
            if "boundingbox" not in res:
                continue

            res_type = res.get("type", "")
            res_class = res.get("class", "")

            # Only accept country level results
            if res_type != "country" and res_class != "boundary":
                continue

            bb = res["boundingbox"]
            lat_size = abs(float(bb[1]) - float(bb[0]))
            lon_size = abs(float(bb[3]) - float(bb[2]))

            if lat_size < MIN_BBOX_SIZE or lon_size < MIN_BBOX_SIZE:
                continue

            bounds = {
                "lat_min": float(bb[0]), "lat_max": float(bb[1]),
                "lon_min": float(bb[2]), "lon_max": float(bb[3]),
            }
            print(f"  Got country bounding box from Nominatim")
            return bounds

        print(f"  Nominatim couldn't find country level result, using fallback...")

    except Exception as e:
        print(f"  Nominatim unavailable, using fallback...")

    # Fallback
    key = country_name.lower().strip()
    for fallback_key, bounds in COUNTRY_FALLBACKS.items():
        if fallback_key in key or key in fallback_key:
            print(f"  Using fallback bounding box for '{fallback_key}'")
            return bounds

    raise ValueError(
        f"Could not find bounding box for '{country_name}'.\n"
        f"Add it to COUNTRY_FALLBACKS in the script."
    )


# ─────────────────────────────────────────────
# STEP 2: Fetch solar score per location
# ─────────────────────────────────────────────

def fetch_pvgis(lat, lon):
    """PVGIS — high resolution solar irradiation."""
    url = "https://re.jrc.ec.europa.eu/api/v5_2/MRadiation"
    params = {"lat": round(lat, 4), "lon": round(lon, 4), "outputformat": "json", "browser": 0}
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        raise Exception(f"PVGIS {r.status_code}")
    data = r.json()
    monthly = data["outputs"]["monthly"]["fixed"]
    return round(sum(m["H(h)_m"] for m in monthly) / len(monthly), 4)


def fetch_open_meteo(lat, lon):
    """Open-Meteo fallback — free, no API key, global coverage."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "daily": "shortwave_radiation_sum",
        "timezone": "auto",
    }
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        raise Exception(f"Open-Meteo {r.status_code}")
    data = r.json()
    values = [v for v in data["daily"]["shortwave_radiation_sum"] if v is not None]
    return round(sum(values) / len(values) / 3.6, 4)


def fetch_solar_score(lat, lon):
    """Try PVGIS first, fall back to Open-Meteo."""
    try:
        return fetch_pvgis(lat, lon), "pvgis"
    except Exception:
        pass
    try:
        return fetch_open_meteo(lat, lon), "open-meteo"
    except Exception:
        return None, "failed"


def fetch_all_scores(candidates):
    """Fetch real solar score for every candidate location."""
    total = len(candidates)
    print(f"  Fetching solar data for {total} locations...")
    print(f"  Progress: ", end="", flush=True)

    updated = [None] * total
    sources = {"pvgis": 0, "open-meteo": 0, "failed": 0}

    def task(idx, loc):
        score, source = fetch_solar_score(loc["lat"], loc["lon"])
        return idx, loc, score, source

    max_workers = 25
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(task, i, loc) for i, loc in enumerate(candidates)]
        for future in as_completed(futures):
            idx, loc, score, source = future.result()
            sources[source] += 1
            updated[idx] = {"lat": loc["lat"], "lon": loc["lon"], "solar_score": score}
            completed += 1
            if completed % 25 == 0:
                print(f"{completed}/{total}", end=" ", flush=True)

    print()
    print(f"  PVGIS: {sources['pvgis']} | Open-Meteo: {sources['open-meteo']} | Failed: {sources['failed']}")

    # Fill failed with mean
    good = [c["solar_score"] for c in updated if c["solar_score"] is not None]
    mean_score = round(float(np.mean(good)), 4) if good else 5.5
    for loc in updated:
        if loc["solar_score"] is None:
            loc["solar_score"] = mean_score

    return updated


# ─────────────────────────────────────────────
# STEP 3: Generate candidate grid
# ─────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NE_SHAPEFILE = os.path.join(
    BASE_DIR, "data", "natural_earth", "ne_110m_admin_0_countries.shp"
)
_WORLD_CACHE = None
COUNTRY_ALIASES = {
    "uk": "united kingdom",
    "england": "united kingdom",
    "scotland": "united kingdom",
    "wales": "united kingdom",
    "northern ireland": "united kingdom",
    "usa": "united states of america",
    "us": "united states of america",
    "united states": "united states of america",
    "uae": "united arab emirates",
    "south korea": "korea, republic of",
    "north korea": "korea, dem. rep.",
    "ivory coast": "cote d'ivoire",
}


def _load_world():
    global _WORLD_CACHE
    if _WORLD_CACHE is not None:
        return _WORLD_CACHE
    if not os.path.exists(NE_SHAPEFILE):
        print(f"  Warning: Natural Earth shapefile not found at {NE_SHAPEFILE}")
        return None
    try:
        _WORLD_CACHE = gpd.read_file(NE_SHAPEFILE)
    except Exception as e:
        print(f"  Warning: could not load country polygons ({e})")
        return None
    return _WORLD_CACHE


def get_country_polygon(country_name):
    world = _load_world()
    if world is None:
        return None

    name = " ".join(country_name.lower().split())
    name = COUNTRY_ALIASES.get(name, name)
    for col in ["NAME", "ADMIN", "SOVEREIGNT", "NAME_EN", "BRK_NAME"]:
        if col not in world.columns:
            continue
        series = world[col].astype(str).str.lower()
        match = world[series == name]
        if match.empty:
            match = world[series.str.contains(name)]
        if not match.empty:
            return match.geometry.values[0]

    print(f"  Warning: no polygon match found for '{country_name}'")
    return None


def generate_grid(bounds, country_name, n_candidates=100):
    country_polygon = get_country_polygon(country_name)
    n_grid = 10

    while True:
        candidates = []
        lats = np.linspace(bounds["lat_min"], bounds["lat_max"], n_grid)
        lons = np.linspace(bounds["lon_min"], bounds["lon_max"], n_grid)

        for lat in lats:
            for lon in lons:
                if not globe.is_land(lat, lon):
                    continue
                if country_polygon is not None:
                    if not country_polygon.contains(Point(lon, lat)):
                        continue
                candidates.append({
                    "lat": round(float(lat), 4),
                    "lon": round(float(lon), 4),
                    "solar_score": None,
                })

        if len(candidates) >= n_candidates:
            step = len(candidates) / n_candidates
            candidates = [candidates[int(i * step)] for i in range(n_candidates)]
            print(f"  Grid {n_grid}x{n_grid} → exactly {len(candidates)} valid candidates")
            return candidates

        print(f"  Grid {n_grid}x{n_grid} gave only {len(candidates)} valid points, increasing...")
        n_grid += 2


# ─────────────────────────────────────────────
# STEP 4: Save / Load
# ─────────────────────────────────────────────

def save_candidates(candidates, country_name, path="candidates.json"):
    with open(path, "w") as f:
        json.dump({
            "country": country_name,
            "total": len(candidates),
            "locations": candidates
        }, f, indent=2)
    print(f"  Saved {len(candidates)} candidates to candidates.json")


def load_candidates(path="candidates.json"):
    with open(path) as f:
        data = json.load(f)
    return data["locations"], data.get("country", "unknown")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 data.py <country>")
        print("Example: python3 data.py Pakistan")
        sys.exit(1)
    
    country = " ".join(sys.argv[1:])

    print("=" * 50)
    print(f"DAY 1 — DATA PIPELINE: {country.upper()}")
    print("=" * 50)

    print("\n[1] Getting country bounding box...")
    bounds = get_country_bbox(country)
    lat_size = bounds["lat_max"] - bounds["lat_min"]
    lon_size = bounds["lon_max"] - bounds["lon_min"]
    print(f"    Lat: {bounds['lat_min']} → {bounds['lat_max']}")
    print(f"    Lon: {bounds['lon_min']} → {bounds['lon_max']}")
    print(f"    Size: ~{lat_size*111:.0f}km × {lon_size*111:.0f}km")

    print("\n[2] Generating 10×10 candidate grid...")
    candidates = generate_grid(bounds, country, n_candidates=100)
    cell_km = (lat_size * 111) / 10
    print(f"    {len(candidates)} candidate regions (~{cell_km:.0f}km per cell)")

    print("\n[3] Fetching real solar irradiance per region...")
    candidates = fetch_all_scores(candidates)

    scores = [c["solar_score"] for c in candidates]
    print(f"    Score range : {min(scores):.3f} – {max(scores):.3f} kWh/m2/day")
    print(f"    Std dev     : {np.std(scores):.4f}")

    print("\n[4] Saving...")
    save_candidates(candidates, country)

    scores = [c["solar_score"] for c in candidates]
    print(f"\n{'='*50}")
    print(f"COMPLETE — {country}")
    print(f"{'='*50}")
    print(f"  Total regions : {len(candidates)}")
    print(f"  Solar mean    : {np.mean(scores):.3f} kWh/m2/day")
    print(f"  Solar range   : {min(scores):.3f} – {max(scores):.3f}")
    top5 = sorted(candidates, key=lambda x: x["solar_score"], reverse=True)[:5]
    print(f"  Top 5 regions:")
    for loc in top5:
        print(f"    ({loc['lat']:.2f}°N, {loc['lon']:.2f}°E) → {loc['solar_score']} kWh/m2/day")