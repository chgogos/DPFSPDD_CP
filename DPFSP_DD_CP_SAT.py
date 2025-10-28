import logging
from ortools.sat.python import cp_model
from itertools import combinations
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from collections import defaultdict

def solve_distributed_flowshop(
        problem, 
        jobs_due_date, 
        factory, 
        permutation=True, 
        time_limit=60, 
        use_lexicographic_symmetry=True, 
        use_min_index_symmetry=False, 
        verbose=False,):
    
    J = len(problem)
    M = len(next(iter(problem.values())))
    F = factory
       
    JOBS = range(J)
    MACHINES = range(M)
    FACTORIES = range(F)

    # Large upper bound for times
    UB = sum(problem[j][m] for j in JOBS for m in MACHINES) + 100
    print("LARGER UPPER BOUND:", UB)
    
    # VARIABLES
    x       = defaultdict(cp_model.IntVar)  # interval variables for each job, factory, machine
    b       = defaultdict(cp_model.IntVar)  # boolean variables for each job, factory `b[j, f] = 1` if job j is assigned to factory f
    start   = defaultdict(cp_model.IntVar)  # start time of job j on machine m
    end     = defaultdict(cp_model.IntVar)  # end time of job j on machine m
    t       = defaultdict(cp_model.IntVar)  # integer variables measuring the tardiness of each job
    

    model = cp_model.CpModel()

    # VARIABLES
    # assignment b[j,f] : job j assigned to factory f
    for j in JOBS:
        for f in FACTORIES:
            b[j, f] = model.NewBoolVar(f"b_{j}_{f}")

    # interval variables: for each job j, factory f, machine m:
    # create start_j_f_m (IntVar), end_j_f_m (IntVar) and optional interval x_j_f_m
    for j in JOBS:
        t[j] = model.new_int_var(0, UB, name=f"t_{j}")
        for f in FACTORIES:
            for m in MACHINES:
                # CP-SAT => NewIntVar(lb, ub, name)
                s = model.NewIntVar(0, UB, f"start_{j}_{f}_{m}")
                e = model.NewIntVar(0, UB, f"end_{j}_{f}_{m}")
                p = problem[j][m]

                x[j, f, m] = model.NewOptionalIntervalVar(s, p, e, b[j, f], f"x_{j}_{f}_{m}")
                start[j, f, m] = s
                end[j, f, m] = e
                    
    # order variables o[j1,j2,f]
    o = {}
    if permutation:
        for j1, j2 in combinations(JOBS, 2):
            for f in FACTORIES:
                o[j1, j2, f] = model.NewBoolVar(f"o_{j1}_{j2}_{f}") #oj1,j2,f​=1⇒end(xj1,f,m​)≤start(xj2,f,m​)
                o[j2, j1, f] = model.NewBoolVar(f"o_{j2}_{j1}_{f}") #oj2,j1,f​=1⇒end(xj2,f,m​)≤start(xj1,f,m​)​
    # =======================================================================================================

    # CONSTRAINTS

    # MODEL EQUATION (2) -  Each job assigned to exactly one factory
    for j in JOBS:
        model.Add(sum(b[j, f] for f in FACTORIES) == 1)

    # MODEL EQUATION (3) - No-overlap at first machine for each factory (global no-overlap)
    for f in FACTORIES:
        model.AddNoOverlap([x[j, f, 0] for j in JOBS])

    # MODEL EQUATION (4) order between pairs of jobs if they are in same factory
    if permutation:
        # Use o variables to impose a consistent order across all machines
        for j1, j2 in combinations(JOBS, 2):
            for f in FACTORIES:
                # If both present and o[j1,j2,f]==1 => j1 before j2 on machine 0 (and we will propagate to all machines)
                model.Add(end[j1, f, 0] <= start[j2, f, 0]).OnlyEnforceIf([o[j1, j2, f], b[j1, f], b[j2, f]])
                model.Add(end[j2, f, 0] <= start[j1, f, 0]).OnlyEnforceIf([o[j2, j1, f], b[j1, f], b[j2, f]])
                # If either job not present then ordering variable is irrelevant:
                model.AddBoolOr([o[j1, j2, f], o[j2, j1, f], b[j1, f].Not(), b[j2, f].Not()])
        for f in FACTORIES:
            for m in range(1, M):
                for j1, j2 in combinations(JOBS, 2):
                    model.Add(end[j1, f, m] <= start[j2, f, m]).OnlyEnforceIf([o[j1, j2, f], b[j1, f], b[j2, f]])
                    model.Add(end[j2, f, m] <= start[j1, f, m]).OnlyEnforceIf([o[j2, j1, f], b[j1, f], b[j2, f]])
    else:
        # Ensure no overlap for machines 1..M-1
        for f in FACTORIES:
            for m in range(1, M):
                model.AddNoOverlap([x[j, f, m] for j in JOBS])

    # MODEL EQUATION (5) for each job in each factory, machine m starts after previous end
    for j in JOBS:
        for f in FACTORIES:
            for m in range(1, M):
               model.Add(end[j, f, m - 1] <= start[j, f, m]).OnlyEnforceIf(b[j, f])

    # MODEL EQUATION (6) tardiness definition
    for j in JOBS:
        Dj = jobs_due_date[j]
        for f in FACTORIES:
            model.Add(t[j] >= end[j, f, M - 1] - Dj).OnlyEnforceIf(b[j, f])
  
    # # Symmetry breaking (7): b_0,0 = 1 (first job assigned to first factory)
    # model.Add(b[0, 0] == 1)

    # #Symmetry breaking (8): binary-weight lexicographic ordering of factories
    # if use_lexicographic_symmetry and F > 1:
    #     #For each factory f compute sum(2^j * b[j,f]) and impose ordering
    #     #Note: 2**j may grow, but for moderate J it's fine; if J large, consider alternative (y variables).
    #     powers = [2 ** j for j in JOBS]
    #     for f in range(F - 1):
    #        lhs = sum(powers[j] * b[j, f] for j in JOBS)
    #        rhs = sum(powers[j] * b[j, f + 1] for j in JOBS)
    #        model.Add(lhs <= rhs)

    # # Symmetry breaking (9)-(10): min-index y_f variables
    # if use_min_index_symmetry and y is not None and F > 2:
    #     #y[f] <= j for every job j present at factory f (so y[f] becomes min index)
    #     for f in range(1, F):
    #         for j in JOBS:
    #             # if b[j,f] then y[f] <= j
    #             model.Add(y[f] <= j).OnlyEnforceIf(b[j, f])
    #     # enforce increasing y[f]
    #     for f in range(1, F - 1):
    #         model.Add(y[f] < y[f + 1])


    # OBJECTIVE: minimize total tardiness
    obj = model.NewIntVar(0, UB * J, "obj")
    model.Add(obj == sum(t[j] for j in JOBS))
    model.Minimize(obj)

    if verbose:
        logging.info(model.ModelStats())

    # SOLVE
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 6
    solver.parameters.log_search_progress = False
    
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("No solution found")
 
    # DEL # BUILD result structure (a simple dict-based solution)
    # DEL sol = Solution(a_problem)

    schedule = { (j,f,m): None for j in JOBS for f in FACTORIES for m in MACHINES }
    assignment = { j: None for j in JOBS }
    for j in JOBS:
        for f in FACTORIES:
            if solver.Value(b[j, f]) == 1:
                assignment[j] = f
                for m in MACHINES:
                    schedule[j, f, m] = solver.Value(start[j, f, m])
                    # DEL sol.schedule(j, f, m, solver.value(start[j, f, m]))
    result = {
        "status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
        "objective": solver.ObjectiveValue(),
        "assignment": assignment,
        "start_times": schedule,
        "tardiness": { j: solver.Value(t[j]) for j in JOBS },
        "best_bound": solver.BestObjectiveBound(),
    }
    
    return result

#==========================================================================================================
#*** CREATE GANT CHART ************************************************************************************
def plot_gantt_with_due_dates(problem, jobs_due_date, result):
    # Collect all the keys from result
    FACTORIES = sorted({f for (_, f, _) in result["start_times"].keys()})
    MACHINES = sorted({m for (_, _, m) in result["start_times"].keys()})
    JOBS = sorted(problem.keys())

    # --- Colormap  ---
    colors = plt.colormaps.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(12, 6))

    yticks, ylabels = [], []
    bar_height = 0.35

    for f in FACTORIES:
        for m in MACHINES:
            y = f * (len(MACHINES) + 0.5) + m
            yticks.append(y)
            ylabels.append(f"F{f}-M{m}")

            for (j, ff, mm), start in result["start_times"].items():
                if f == ff and m == mm and start is not None:
                    dur = problem[j][m]
                    # check for right instances
                    if dur is None or isinstance(dur, str):
                        continue
                    ax.barh(
                        y, dur, left=start, height=bar_height,
                        color=colors(j % len(JOBS)), edgecolor="black"
                    )
                    ax.text(
                        start + dur / 2, y, f"J{j}",
                        va="center", ha="center", fontsize=8, color="black"
                    )

    # --- Due Dates ---
    for j in JOBS:
        Dj = jobs_due_date[j]
        ax.axvline(Dj, color=colors(j % len(JOBS)), linestyle="--", linewidth=1)
        ax.text(Dj, max(yticks) + 0.5, f"D{j}={Dj}", rotation=90,
                va="bottom", ha="center", fontsize=8, color=colors(j % len(JOBS)))

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("Time")
    ax.set_title(f"Gantt Chart (Total Tardiness = {result.get('objective', 0):.0f})")

    ax.grid(True, axis="x", linestyle=":", alpha=0.5)

    # --- Legend ---
    patches = [mpatches.Patch(color=colors(j % len(JOBS)), label=f"Job {j}") for j in JOBS]
    ax.legend(handles=patches, loc="upper right", fontsize=8, ncol=2)

    plt.tight_layout()
    plt.show()

#==========================================================================================================
#*** BUILD SEQUENCES **************************************************************************************
def build_factory_sequences(result):
    raw = result.get("start_times", {})
    flat = {}
    if all(isinstance(k, tuple) and len(k) == 3 for k in raw.keys()):
        flat = dict(raw)
    else:
        for j, v1 in raw.items():
            if isinstance(v1, dict):
                for f, v2 in v1.items():
                    if isinstance(v2, dict):
                        for m, st in v2.items():
                            flat[(int(j), int(f), int(m))] = st
                    else:
                        flat[(int(j), int(f), 0)] = v2
            else:
                pass

    factories = sorted({f for (_, f, _) in flat.keys()})
    jobs = sorted({j for (j, _, _) in flat.keys()})
    j_f_start = {}
    for (j, f, m), st in flat.items():
        j_f_start.setdefault((j, f), []).append((m, st))

    j_f_best_start = {}
    for (j, f), lst in j_f_start.items():
        m0_entries = [st for (m, st) in lst if m == 0 and st is not None]
        if m0_entries:
            j_f_best_start[(j, f)] = m0_entries[0]
        else:
            numeric = [st for (m, st) in lst if st is not None]
            j_f_best_start[(j, f)] = min(numeric) if numeric else None

    factory_sequences = {}
    for f in factories:
        entries = []
        for j in jobs:
            start = j_f_best_start.get((j, f), None)
            if start is not None:
                entries.append((j, float(start)))
        entries.sort(key=lambda x: (x[1], x[0]))
        factory_sequences[f] = [j for j, _ in entries]

    return factory_sequences

#==========================================================================================================
#*** CALL MAIN FUNCTION ***********************************************************************************
if __name__ == "__main__":

    # PROBLEM DATA       
    problem = {0: [1, 4], 1: [86, 21], 2: [28, 67], 3: [32, 17]}
    jobs_due_date = {0:5, 1:108, 2:96, 3:50}
    factory = 2

    # problem = {0: [59, 80], 1: [92, 51], 2: [66, 99], 3: [77, 71], 4: [89, 99], 5: [73, 78]}
    # jobs_due_date = {0:144,1:148,2:169,3:149, 4:190, 5:158}
    # factory = 2
    try:
        #CALL THE SOLVER FUNCTION
        results = solve_distributed_flowshop(problem, jobs_due_date , factory, time_limit=30, verbose=True)
              
        summary = {
        "Solver Status": results["status"],
        "Objective (Total Tardiness)": results["objective"],
        "Best Bound": results["best_bound"],
        "Optimality Gap (%)": round(
        100 * (results["objective"] - results["best_bound"]) / results["objective"], 2
        )
        }
       
        jobs_df = pd.DataFrame([
            {
            "Job": j,
            "Assigned Factory": results["assignment"][j],
            "Tardiness": results["tardiness"][j]
            }
        for j in results["assignment"]
        ])

        FACTORIES = sorted({f for (_, f, _) in results["start_times"].keys()})
       
        print(pd.DataFrame([summary]))                              #print SUMMARY
        print(jobs_df)                                              #print jobs Assignments
        print(build_factory_sequences(results))                     #print sequences of jobs on Factories
        plot_gantt_with_due_dates(problem, jobs_due_date, results)  #print Gantt Chart
       
    except Exception as e:
        logging.error(e)