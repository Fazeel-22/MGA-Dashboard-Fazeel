import pandas as pd
import numpy as np
import json
from itertools import permutations, product
from gurobipy import Model, GRB, quicksum

# --- Load feasible points ---
df = pd.read_excel("A_matrix_feasible_region.xlsx")
energy_sources = df.columns.tolist()
num_points = len(df)
A_matrix = {src: df[src].values for src in energy_sources}

ϵ = 0.02
UB = {src: max(A_matrix[src]) for src in energy_sources}
LB = {src: min(A_matrix[src]) for src in energy_sources}
R  = {src: UB[src] - LB[src] for src in energy_sources}

# Starting point: centroid of feasible region
P0 = {src: float(np.mean(A_matrix[src])) for src in energy_sources}


def solve_lp(direction_constraints, obj_source):
    """Solve λ-simplex LP, minimizing obj_source, subject to any direction_constraints."""
    try:
        m = Model()
        m.setParam("OutputFlag", 0)
        lambdas = m.addVars(num_points, lb=0, ub=1, name="λ")
        # always minimize the first priority objective
        m.setObjective(quicksum(A_matrix[obj_source][j] * lambdas[j] for j in range(num_points)), GRB.MINIMIZE)
        m.addConstr(quicksum(lambdas[j] for j in range(num_points)) == 1)

        # apply any direction constraints (lb, ub) on each source
        for src, (lb, ub) in direction_constraints.items():
            expr = quicksum(A_matrix[src][j] * lambdas[j] for j in range(num_points))
            if lb is not None:
                m.addConstr(expr >= lb)
            if ub is not None:
                m.addConstr(expr <= ub)

        m.optimize()
        if m.status == GRB.OPTIMAL:
            return np.array([lambdas[j].X for j in range(num_points)])
        else:
            return None
    except Exception as e:
        print(f"LP solve error for {obj_source}: {e}")
        return None


def generate_direction_constraint(prev_point, src, direction, step):
    """
    For step == 0, ignore ε and jump to absolute extreme:
      ↑ => enforce src >= UB[src]
      ↓ => enforce src <= LB[src]
      ⏸️ => no constraint
    For step > 0, use ε-tolerance around prev_point[src].
    """
    if step == 0:
        if direction == "↑":
            return {src: (UB[src], None)}
        elif direction == "↓":
            return {src: (None, LB[src])}
        else:  # pause at start: no constraint
            return {}
    else:
        if direction == "↑":
            lb = min(prev_point[src] + ϵ * R[src], UB[src])
            return {src: (lb, None)}
        elif direction == "↓":
            ub = max(prev_point[src] - ϵ * R[src], LB[src])
            return {src: (None, ub)}
        else:  # ⏸️
            lb = max(prev_point[src] - ϵ * R[src], LB[src])
            ub = min(prev_point[src] + ϵ * R[src], UB[src])
            return {src: (lb, ub)}


# --- Store partial paths ---
path_dict = {}
total_cases = 0
successful_cases = 0

priority_orders = list(permutations(energy_sources))          # 120 orders
direction_sets  = list(product(["↑", "⏸️", "↓"], repeat=len(energy_sources)))  # 3^5 combinations

for priority in priority_orders:
    for directions in direction_sets:
        steps      = []
        constraints = {}
        point_k    = P0.copy()
        λ_k        = np.full(num_points, 1 / num_points)
        success    = True

        for k, src_k in enumerate(priority):
            dir_k = directions[k]
            # build (or override) the single-source constraint
            new_c = generate_direction_constraint(point_k, src_k, dir_k, k)
            constraints.update(new_c)

            # always optimize the first priority source
            λ_new = solve_lp(constraints, priority[0])
            if λ_new is None:
                success = False
                break

            point_new = {src: float(np.dot(λ_new, A_matrix[src])) for src in energy_sources}
            steps.append({
                "step": k + 1,
                "λ":      λ_new.tolist(),
                "point":  point_new
            })
            point_k = point_new
            λ_k      = λ_new

            # record the path so far
            key = (tuple(priority[: k + 1 ]), tuple(directions[: k + 1 ]))
            path_dict[str(key)] = steps.copy()

        total_cases += 1
        if success:
            successful_cases += 1

        if total_cases % 500 == 0:
            print(f"{total_cases} tested, {successful_cases} successful full paths")

# --- Save as JSON ---
with open("precomputed_mga_nested.json", "w") as f:
    json.dump(path_dict, f, indent=2)

print(f"\n✅ Done. Saved {len(path_dict)} partial MGA paths to 'precomputed_mga_nested.json'")
