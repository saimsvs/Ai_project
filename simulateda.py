import random
import math
import json


# ── Hyperparameters ──────────────────────────
N_SELECT  = 50        # sites to pick per solution
T_START   = 5.0       # initial temperature  (high → explore freely)
T_END     = 0.001     # final temperature    (low  → near-greedy)
N_STEPS   = 50_000    # total annealing steps
LOG_EVERY = 5_000     # print progress every N steps
# ─────────────────────────────────────────────


# ── Load candidates ──────────────────────────
with open("candidates.json") as f:
    data = json.load(f)
candidates = data["locations"]   # list of {lat, lon, solar_score}
N_CANDIDATES = len(candidates)   # 225


# ── Helper: score a selection (set of indices) ──
def score_selection(selected_set):
    return sum(candidates[i]["solar_score"] for i in selected_set)


# ── Initialise solution ──────────────────────
print("=" * 50)
print("SA — SOLAR PANEL PLACEMENT OPTIMIZER")
print("=" * 50)
print(f"\nSteps      : {N_STEPS:,}")
print(f"T_start    : {T_START}")
print(f"T_end      : {T_END}")
print(f"Sites/sol  : {N_SELECT} out of {N_CANDIDATES}\n")

# Random starting selection (set for O(1) membership checks)
current_sel   = set(random.sample(range(N_CANDIDATES), N_SELECT))
current_score = score_selection(current_sel)

best_sel   = set(current_sel)
best_score = current_score

# Pre-compute cooling factor α
alpha = (T_END / T_START) ** (1.0 / N_STEPS)
T     = T_START

history        = []   # (step, temperature, best_score) logged every LOG_EVERY steps
n_accepted     = 0    # moves accepted (including worse ones)
n_improvements = 0    # moves that improved the score

# ── Main SA loop ─────────────────────────────
for step in range(N_STEPS):

    # ── Build neighbour via swap ──
    # 1. Remove one random site from current selection
    remove_idx = random.choice(list(current_sel))

    # 2. Add one random site NOT in current selection
    all_indices    = set(range(N_CANDIDATES))
    not_selected   = list(all_indices - current_sel)
    add_idx        = random.choice(not_selected)

    # 3. Construct neighbour
    neighbour_sel  = (current_sel - {remove_idx}) | {add_idx}
    neighbour_score = current_score - candidates[remove_idx]["solar_score"] \
                                    + candidates[add_idx]["solar_score"]

    # ── Acceptance decision ──
    delta = neighbour_score - current_score

    if delta > 0:
        # Better move — always accept
        current_sel   = neighbour_sel
        current_score = neighbour_score
        n_accepted    += 1
        n_improvements += 1
    else:
        # Worse move — accept with Boltzmann probability
        prob = math.exp(delta / T)
        if random.random() < prob:
            current_sel   = neighbour_sel
            current_score = neighbour_score
            n_accepted    += 1

    # ── Track global best ──
    if current_score > best_score:
        best_sel   = set(current_sel)
        best_score = current_score

    # ── Cool down ──
    T *= alpha

    # ── Logging ──
    if (step + 1) % LOG_EVERY == 0:
        history.append({
            "step":       step + 1,
            "temperature": round(T, 6),
            "best_score": round(best_score, 4),
        })
        accept_rate = n_accepted / (step + 1)
        print(f"Step {step+1:>6,} | T={T:.5f} | best={best_score:.4f} | "
              f"accept_rate={accept_rate:.3f}")


print(f"\nFinal best score : {best_score:.4f}")
print(f"Improvements     : {n_improvements:,} out of {N_STEPS:,} steps")
print(f"Best locations   : {sorted(best_sel)}")


# ── Save result ──────────────────────────────
result = {
    "algorithm": "SA",
    "hyperparameters": {
        "n_select":  N_SELECT,
        "t_start":   T_START,
        "t_end":     T_END,
        "n_steps":   N_STEPS,
        "alpha":     round(alpha, 8),
    },
    "best_score":     best_score,
    "n_improvements": n_improvements,
    "score_history":  history,
    "best_locations": [candidates[i] for i in sorted(best_sel)],
}

with open("sa_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("\nSaved to sa_result.json")
print("\nAll three algorithms complete!")
print("  GA  → ga_result.json")
print("  PSO → pso_result.json")
print("  SA  → sa_result.json")