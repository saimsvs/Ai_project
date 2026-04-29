import random
import json

# ── Hyperparameters ──────────────────────────
N_PARTICLES   = 60      # swarm size
N_GENERATIONS = 300     # iterations
N_SELECT      = 50      # sites to pick per solution
N_CANDIDATES  = 225     # total grid points
V_MAX         = 0.4     # max velocity (clamps exploration)
W_START       = 0.9     # inertia at generation 0  (high → explore)
W_END         = 0.4     # inertia at last generation (low → exploit)
C1            = 1.5     # cognitive acceleration
C2            = 1.5     # social acceleration
# ─────────────────────────────────────────────


# ── Load candidates ──────────────────────────
with open("candidates.json") as f:
    data = json.load(f)
candidates = data["locations"]   # list of {lat, lon, solar_score}


# ── Helper: score a selection (list of indices) ──
def score_selection(selected_indices):
    return sum(candidates[i]["solar_score"] for i in selected_indices)


# ── Helper: top-50 indices from a probability vector ──
def top50(position):
    # argsort descending → pick first 50
    ranked = sorted(range(N_CANDIDATES), key=lambda i: position[i], reverse=True)
    return ranked[:N_SELECT]


# ── Initialise swarm ─────────────────────────
print("=" * 50)
print("PSO — SOLAR PANEL PLACEMENT OPTIMIZER")
print("=" * 50)
print(f"\nSwarm size : {N_PARTICLES} particles")
print(f"Iterations : {N_GENERATIONS} generations")
print(f"Sites/sol  : {N_SELECT} out of {N_CANDIDATES}\n")

swarm = []
for _ in range(N_PARTICLES):
    pos = [random.random() for _ in range(N_CANDIDATES)]   # random probabilities
    vel = [random.uniform(-V_MAX, V_MAX) for _ in range(N_CANDIDATES)]
    sel = top50(pos)
    sc  = score_selection(sel)
    particle = {
        "pos":   pos,
        "vel":   vel,
        "pbest_pos":   list(pos),   # personal best position
        "pbest_score": sc,
        "pbest_sel":   sel,
    }
    swarm.append(particle)

# Global best — initialise from best particle
gbest_particle = max(swarm, key=lambda p: p["pbest_score"])
gbest_pos   = list(gbest_particle["pbest_pos"])
gbest_score = gbest_particle["pbest_score"]
gbest_sel   = list(gbest_particle["pbest_sel"])


# ── Main PSO loop ────────────────────────────
history = []   # track gbest score per generation

for gen in range(N_GENERATIONS):

    # Linearly decay inertia weight (exploration → exploitation)
    w = W_START - (W_START - W_END) * (gen / N_GENERATIONS)

    for particle in swarm:
        pos = particle["pos"]
        vel = particle["vel"]
        pb  = particle["pbest_pos"]

        # Velocity & position update
        new_vel = []
        new_pos = []
        for i in range(N_CANDIDATES):
            r1 = random.random()
            r2 = random.random()
            v_new = (w * vel[i]
                     + C1 * r1 * (pb[i]       - pos[i])
                     + C2 * r2 * (gbest_pos[i] - pos[i]))
            # Clamp velocity
            v_new = max(-V_MAX, min(V_MAX, v_new))
            p_new = max(0.0, min(1.0, pos[i] + v_new))
            new_vel.append(v_new)
            new_pos.append(p_new)

        particle["vel"] = new_vel
        particle["pos"] = new_pos

        # Evaluate new position
        sel = top50(new_pos)
        sc  = score_selection(sel)

        # Update personal best
        if sc > particle["pbest_score"]:
            particle["pbest_pos"]   = list(new_pos)
            particle["pbest_score"] = sc
            particle["pbest_sel"]   = sel

        # Update global best
        if sc > gbest_score:
            gbest_pos   = list(new_pos)
            gbest_score = sc
            gbest_sel   = list(sel)

    history.append(gbest_score)

    if gen % 50 == 0:
        print(f"Generation {gen:>3} — best score: {gbest_score:.4f}  (w={w:.3f})")

print(f"\nGeneration {N_GENERATIONS} — best score: {gbest_score:.4f}")
print(f"\nFinal best score : {gbest_score:.4f}")
print(f"Best locations   : {gbest_sel}")


# ── Save result ──────────────────────────────
result = {
    "algorithm":      "PSO",
    "hyperparameters": {
        "n_particles":   N_PARTICLES,
        "n_generations": N_GENERATIONS,
        "n_select":      N_SELECT,
        "w_start":       W_START,
        "w_end":         W_END,
        "c1":            C1,
        "c2":            C2,
        "v_max":         V_MAX,
    },
    "best_score":     gbest_score,
    "score_history":  history,
    "best_locations": [candidates[i] for i in gbest_sel],
}

with open("pso_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("\nSaved to pso_result.json")
print("\nRun next: python3 sa.py")