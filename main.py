import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

from flask import Flask, jsonify, render_template, request

# Prefer the local venv interpreter when available.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_VENV_PY = os.path.join(_BASE_DIR, ".venv", "bin", "python")
if os.path.exists(_VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PY):
    os.execv(_VENV_PY, [_VENV_PY] + sys.argv)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script_capture(script_name, *args):
    script_path = os.path.join(BASE_DIR, script_name)
    start = time.time()
    result = subprocess.run(
        [sys.executable, script_path, *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=BASE_DIR
    )
    elapsed = round(time.time() - start, 2)
    return result.stdout, result.stderr, elapsed

# ─────────────────────────────────────────────
# MAIN — Solar Panel Placement Optimizer
# Runs: data pipeline → GA → PSO → SA
# Compares results and picks the winner
# ─────────────────────────────────────────────

def run_script(script_name, *args):
    """Run a Python script and return time taken."""
    print(f"\n{'='*50}")
    if args:
        display_args = " ".join(args)
        print(f"Running {script_name} {display_args}...")
    else:
        print(f"Running {script_name}...")
    print(f"{'='*50}")
    start = time.time()
    result = subprocess.run([sys.executable, script_name, *args], check=True)
    elapsed = round(time.time() - start, 2)
    print(f"\n✓ {script_name} completed in {elapsed}s")
    return elapsed


def run_script_capture(script_name, *args):
    """Run a Python script and return stdout/stderr plus elapsed time."""
    start = time.time()
    result = subprocess.run(
        [sys.executable, script_name, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    elapsed = round(time.time() - start, 2)
    return result.stdout, result.stderr, elapsed


def load_result(path):
    """Load a result JSON file."""
    with open(path) as f:
        return json.load(f)


def compare_results():
    """Load all three results and print comparison."""
    ga  = load_result("ga_result.json")
    pso = load_result("pso_result.json")
    sa  = load_result("sa_result.json")

    results = [ga, pso, sa]
    winner  = max(results, key=lambda x: x["best_score"])

    print(f"\n{'='*50}")
    print("ALGORITHM COMPARISON")
    print(f"{'='*50}")
    print(f"{'Algorithm':<10} {'Best Score':<15} {'Winner'}")
    print(f"{'-'*35}")
    for r in results:
        tag = " ← WINNER" if r["algorithm"] == winner["algorithm"] else ""
        print(f"{r['algorithm']:<10} {r['best_score']:<15.4f}{tag}")

    print(f"\nWinner: {winner['algorithm']} with score {winner['best_score']:.4f}")
    print(f"\nWhat this means:")
    print(f"  The best 50 solar farm locations found by {winner['algorithm']}")
    print(f"  collectively generate {winner['best_score']:.2f} kWh/m²/day total.")

    # Save comparison
    comparison = {
        "results": [
            {"algorithm": r["algorithm"], "best_score": r["best_score"]}
            for r in results
        ],
        "winner": winner["algorithm"],
        "winner_score": winner["best_score"],
        "winner_locations": winner["best_locations"],
    }
    with open("comparison.json", "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"\nSaved comparison to comparison.json")
    return comparison


def run_cli():
    print("=" * 50)
    print("SOLAR PANEL PLACEMENT OPTIMIZER")
    print("Comparing GA vs PSO vs SA")
    print("=" * 50)

    # Get country from user
    country = input("\nEnter country name (e.g. 'Pakistan'): ").strip()
    if not country:
        country = "Pakistan"

    # Step 1 — Data pipeline
    run_script("data.py", country)

    # Step 2 — Run all three algorithms
    run_script("ga.py")
    run_script("pso.py")
    run_script("simulateda.py")

    # Step 3 — Compare
    compare_results()

    print("\nDone. Run map.py next to visualize results.")


def create_app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, template_folder="templates", static_folder="static")
    lock = threading.Lock()

    state = {
        "country": None,
        "last_step": None,
    }

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    def safe_run(script_name, *args):
        with lock:
            stdout, stderr, elapsed = run_script_capture(script_name, *args)
        return stdout, stderr, elapsed

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    @app.post("/set-country")
    def set_country():
        payload = request.get_json(silent=True) or {}
        country = (payload.get("country") or "").strip()
        if not country:
            return jsonify({"ok": False, "error": "Country is required."}), 400
        state["country"] = country
        state["last_step"] = "country"
        return jsonify({"ok": True, "country": country})

    @app.post("/run/all")
    def run_all():
        payload = request.get_json(silent=True) or {}
        country = (payload.get("country") or state["country"] or "").strip()
        if not country:
            return jsonify({"ok": False, "error": "Country is required."}), 400
        state["country"] = country

        try:
            stdout_data, stderr_data, elapsed_data = safe_run("data.py", country)
            stdout_ga, stderr_ga, elapsed_ga = safe_run("ga.py")
            stdout_pso, stderr_pso, elapsed_pso = safe_run("pso.py")
            stdout_sa, stderr_sa, elapsed_sa = safe_run("simulateda.py")
            comparison = compare_results()
        except subprocess.CalledProcessError as exc:
            return jsonify({"ok": False, "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr}), 500

        state["last_step"] = "compare"
        return jsonify({
            "ok": True,
            "country": country,
            "steps": {
                "data": {"stdout": stdout_data, "stderr": stderr_data, "elapsed": elapsed_data},
                "ga": {"stdout": stdout_ga, "stderr": stderr_ga, "elapsed": elapsed_ga},
                "pso": {"stdout": stdout_pso, "stderr": stderr_pso, "elapsed": elapsed_pso},
                "sa": {"stdout": stdout_sa, "stderr": stderr_sa, "elapsed": elapsed_sa},
            },
            "comparison": comparison,
        })

    @app.post("/run/data")
    def run_data():
        if not state["country"]:
            return jsonify({"ok": False, "error": "Set a country first."}), 400
        try:
            stdout, stderr, elapsed = safe_run("data.py", state["country"])
        except subprocess.CalledProcessError as exc:
            return jsonify({"ok": False, "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr}), 500
        state["last_step"] = "data"
        return jsonify({"ok": True, "stdout": stdout, "stderr": stderr, "elapsed": elapsed})

    @app.post("/run/ga")
    def run_ga():
        try:
            stdout, stderr, elapsed = safe_run("ga.py")
        except subprocess.CalledProcessError as exc:
            return jsonify({"ok": False, "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr}), 500
        state["last_step"] = "ga"
        return jsonify({"ok": True, "stdout": stdout, "stderr": stderr, "elapsed": elapsed})

    @app.post("/run/pso")
    def run_pso():
        try:
            stdout, stderr, elapsed = safe_run("pso.py")
        except subprocess.CalledProcessError as exc:
            return jsonify({"ok": False, "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr}), 500
        state["last_step"] = "pso"
        return jsonify({"ok": True, "stdout": stdout, "stderr": stderr, "elapsed": elapsed})

    @app.post("/run/sa")
    def run_sa():
        try:
            stdout, stderr, elapsed = safe_run("simulateda.py")
        except subprocess.CalledProcessError as exc:
            return jsonify({"ok": False, "error": str(exc), "stdout": exc.stdout, "stderr": exc.stderr}), 500
        state["last_step"] = "sa"
        return jsonify({"ok": True, "stdout": stdout, "stderr": stderr, "elapsed": elapsed})

    @app.post("/run/compare")
    def run_compare():
        try:
            comparison = compare_results()
        except FileNotFoundError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        state["last_step"] = "compare"
        return jsonify({"ok": True, "comparison": comparison})

    @app.get("/comparison")
    def get_comparison():
        path = os.path.join(base_dir, "comparison.json")
        if not os.path.exists(path):
            return jsonify({"ok": False, "error": "comparison.json not found"}), 404
        with open(path) as f:
            data = json.load(f)
        return jsonify({"ok": True, "comparison": data})

    return app


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
app = create_app()

if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
        raise SystemExit(0)

    port = int(os.environ.get("PORT", "5000"))
    if "PORT" not in os.environ:
        url = f"http://127.0.0.1:{port}"
        try:
            webbrowser.open(url)
        except Exception:
            pass
    app.run(host="0.0.0.0", port=port, debug=False)