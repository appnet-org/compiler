import gurobipy as gp
from gurobipy import GRB

def optimize(dreqi, drespi, si, ri, Bj, Ereqi, Erespi, Sstrong, Srelaxed, Pij, Oij):
    elements = list(dreqi.keys())
    locations = list(Bj.keys())
    orders = list(range(len(elements)))

    m = gp.Model("AppNet_Optimization")

    # Decision variables
    x = m.addVars(elements, locations, vtype=GRB.BINARY, name="x")
    y = m.addVars(elements, orders, vtype=GRB.BINARY, name="y")
    max_strong_sync = m.addVars(locations, vtype=GRB.CONTINUOUS, name="max_strong_sync")
    max_relaxed_sync = m.addVars(locations, vtype=GRB.CONTINUOUS, name="max_relaxed_sync")
    location_active = m.addVars(locations, vtype=GRB.BINARY, name="location_active")

    # Objective function
    m.setObjective(
        gp.quicksum(
            gp.quicksum(
                (Ereqi[i] * (1 - dreqi[i]) + Erespi[i] * (1 - drespi[i])) * x[i, j]
                for i in elements
            )
            + max_strong_sync[j]
            + max_relaxed_sync[j]
            + Bj[j] * location_active[j]
            for j in locations
        ),
        GRB.MINIMIZE
    )

    # Element Placement Constraint
    m.addConstrs((gp.quicksum(x[i, j] for j in locations) == 1 for i in elements), name="placement")

    # Execution Order Constraint
    m.addConstrs((gp.quicksum(y[i, k] for k in orders) == 1 for i in elements), name="order")

    # Unique Position Constraint
    m.addConstrs((gp.quicksum(y[i, k] for i in elements) <= 1 for k in orders), name="unique_position")

    # Allowed Location Constraint
    m.addConstrs((x[i, j] <= Pij[i, j] for i in elements for j in locations), name="allowed_location")

    # Allowed Ordering Constraint
    m.addConstrs((y[i, k] <= y[j, k + 1] for i in elements for j in elements for k in range(len(orders) - 1) if i != j and Oij.get((i, j), 0) == 1), name="allowed_ordering")

    # Strong synchronization constraints
    m.addConstrs((max_strong_sync[j] >= si[i] * x[i, j] * Sstrong[i, j] for i in elements for j in locations), name="strong_sync")

    # Relaxed synchronization constraints
    m.addConstrs((max_relaxed_sync[j] >= ri[i] * x[i, j] * Srelaxed[i, j] for i in elements for j in locations), name="relaxed_sync")

    # Location active constraint
    m.addConstrs((location_active[j] >= x[i, j] for i in elements for j in locations), name="location_active")

    # Optimize model
    m.optimize()

    if m.status == GRB.OPTIMAL:
        placement = m.getAttr('x', x)
        order = m.getAttr('x', y)
        optimal_placement = {i: j for i in elements for j in locations if placement[i, j] > 0.5}
        optimal_order = {i: k for i in elements for k in orders if order[i, k] > 0.5}
        return optimal_placement, optimal_order
    else:
        print("No optimal solution found.")
        return None, None

# Test cases
dreqi = {'A': 0, 'B': 0}
drespi = {'A': 0, 'B': 0}
si = {'A': 0, 'B': 0}
ri = {'A': 0, 'B': 0}
Bj = {'L1': 5, 'L2': 5}
Ereqi = {'A': 1, 'B': 1}
Erespi = {'A': 1, 'B': 1}
Sstrong = {('A', 'L1'): 1, ('A', 'L2'): 1, ('B', 'L1'): 1, ('B', 'L2'): 1}
Srelaxed = {('A', 'L1'): 1, ('A', 'L2'): 1, ('B', 'L1'): 1, ('B', 'L2'): 1}
Pij = {('A', 'L1'): 1, ('A', 'L2'): 1, ('B', 'L1'): 1, ('B', 'L2'): 1}
Oij = {('A', 'B'): 0, ('B', 'A'): 0}

optimal_placement, optimal_order = optimize(dreqi, drespi, si, ri, Bj, Ereqi, Erespi, Sstrong, Srelaxed, Pij, Oij)

print("Optimal Placement:")
for elem, loc in optimal_placement.items():
    print(f"Element {elem} is placed at location {loc}")

print("\nOptimal Order:")
for elem, ord in optimal_order.items():
    print(f"Element {elem} is executed in order {ord}")
# import random
# import time

# def generate_test_case(num_elements, num_locations):
#     # Generate random test data
#     elements = [f"E{i}" for i in range(num_elements)]
#     locations = [f"L{j}" for j in range(num_locations)]
    
#     dreqi = {elem: random.uniform(0, 0.3) for elem in elements}
#     drespi = {elem: random.uniform(0, 0.2) for elem in elements}
#     si = {elem: random.choice([0, 1]) for elem in elements}
#     ri = {elem: random.choice([0, 1]) for elem in elements}
#     Bj = {loc: random.uniform(1, 10) for loc in locations}
#     Ereqi = {elem: random.uniform(1, 5) for elem in elements}
#     Erespi = {elem: random.uniform(1, 5) for elem in elements}
#     Sstrong = {(elem, loc): random.uniform(1, 3) for elem in elements for loc in locations}
#     Srelaxed = {(elem, loc): random.uniform(1, 3) for elem in elements for loc in locations}
#     Pij = {(elem, loc): random.choice([0, 1]) for elem in elements for loc in locations}
    
#     # Ensure at least one valid placement
#     for elem in elements:
#         if all(Pij[(elem, loc)] == 0 for loc in locations):
#             Pij[(elem, random.choice(locations))] = 1
    
#     Oij = {(elem1, elem2): random.choice([0, 1]) for elem1 in elements for elem2 in elements if elem1 != elem2}
    
#     return dreqi, drespi, si, ri, Bj, Ereqi, Erespi, Sstrong, Srelaxed, Pij, Oij

# def test_scalability():
#     sizes = [(5, 5), (10, 5), (20, 5), (30, 5), (40, 5), (100, 5)]
#     results = []
    
#     for num_elements, num_locations in sizes:
#         dreqi, drespi, si, ri, Bj, Ereqi, Erespi, Sstrong, Srelaxed, Pij, Oij = generate_test_case(num_elements, num_locations)
        
#         start_time = time.time()
#         optimal_placement, optimal_order = optimize(dreqi, drespi, si, ri, Bj, Ereqi, Erespi, Sstrong, Srelaxed, Pij, Oij)
#         end_time = time.time()
        
#         results.append({
#             "num_elements": num_elements,
#             "num_locations": num_locations,
#             "execution_time": end_time - start_time,
#             "optimal_placement": optimal_placement,
#             "optimal_order": optimal_order
#         })
        
#         print(f"Test case with {num_elements} elements and {num_locations} locations executed in {end_time - start_time:.2f} seconds.")
    
#     return results

# # Run the scalability test
# scalability_results = test_scalability()

# # Print results
# for result in scalability_results:
#     print(f"Elements: {result['num_elements']}, Locations: {result['num_locations']}, Execution Time: {result['execution_time']:.2f} seconds")

# # Optional: You can save the results to a file for further analysis
# import json
# with open('scalability_results.json', 'w') as f:
#     json.dump(scalability_results, f, indent=4)
