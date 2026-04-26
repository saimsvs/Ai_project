import random
import json

with open("candidates.json") as f:
    data = json.load(f)
candidates = data["locations"]

# Build population
population = []
for _ in range(100):
    selected = random.sample(range(225), 50)
    score = sum(candidates[idx]["solar_score"] for idx in selected)
    population.append({"selected": selected, "score": score})

def tournament_select(population, k=5):
    tournament = random.sample(population, k)
    return max(tournament, key=lambda x: x["score"])

def crossover(parentA, parentB):
    pool = list(set(parentA["selected"] + parentB["selected"]))
    if len(pool) >= 50:
        child = random.sample(pool, 50)
    else:
        extra = random.sample(range(225), 50 - len(pool))
        child = pool + extra
    return child

def mutate(child, mutation_rate=0.1):
    if random.random() < mutation_rate:
        # pick a random position in child to replace
        remove_idx = random.randint(0, 49)
        # find all locations NOT in child
        all_indices = set(range(225))
        not_selected = list(all_indices - set(child))
        # pick a random one to add
        new_loc = random.choice(not_selected)
        # swap
        child[remove_idx] = new_loc
    return child

# Create parents
best_ever = max(population, key=lambda x: x["score"])

for generation in range(300):
    
    # Step 1 - select parents
    parents = [tournament_select(population) for _ in range(100)]
    
    # Step 2 - make children, mutate, score
    new_population = []
    for i in range(0, 100, 2):
        child1 = mutate(crossover(parents[i], parents[i+1]))
        child2 = mutate(crossover(parents[i+1], parents[i]))
        
        score1 = sum(candidates[idx]["solar_score"] for idx in child1)
        score2 = sum(candidates[idx]["solar_score"] for idx in child2)
        
        new_population.append({"selected": child1, "score": score1})
        new_population.append({"selected": child2, "score": score2})
    
    # Step 3 - replace old population
    population = new_population
    
    # Step 4 - track best
    current_best = max(population, key=lambda x: x["score"])
    if current_best["score"] > best_ever["score"]:
        best_ever = current_best
    
    if generation % 50 == 0:
        print(f"Generation {generation} — best score: {best_ever['score']:.4f}")

print(f"\nFinal best score: {best_ever['score']:.4f}")
print(f"Best locations: {best_ever['selected']}")

result = {
    "algorithm": "GA",
    "best_score": best_ever["score"],
    "best_locations": [candidates[i] for i in best_ever["selected"]]
}

with open("ga_result.json", "w") as f:
    json.dump(result, f, indent=2)

print("Saved to ga_result.json")