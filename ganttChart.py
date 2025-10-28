import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

def plot_gantt_with_due_dates(problem, jobs_due_date, result):
    """
    Δημιουργεί Gantt chart χρησιμοποιώντας:
    - problem: dict {job: [ptime_m0, ptime_m1, ...]}
    - jobs_due_date: dict {job: Dj}
    - result: dict που περιέχει "start_times" και "objective"
    """

    # Βρες το μέγιστο index εργοστασίου και μηχανής
    FACTORIES = sorted(set(f for (_, f, _) in result["start_times"].keys()))
    MACHINES = sorted(set(m for (_, _, m) in result["start_times"].keys()))
    JOBS = sorted(problem.keys())

    colors = plt.cm.get_cmap("tab10", len(JOBS))
    fig, ax = plt.subplots(figsize=(12, 6))

    yticks = []
    ylabels = []
    bar_height = 0.35

    # Σχεδίαση bars ανά εργοστάσιο και μηχανή
    for f in FACTORIES:
        for m in MACHINES:
            y = f * (len(MACHINES) + 0.5) + m
            yticks.append(y)
            ylabels.append(f"F{f}-M{m}")

            for (j, ff, mm), start in result["start_times"].items():
                if f == ff and m == mm:
                    dur = problem[j][m]  # παίρνουμε processing time από το dict
                    ax.barh(
                        y, dur, left=start, height=bar_height,
                        color=colors(j), edgecolor="black"
                    )
                    ax.text(
                        start + dur / 2, y, f"J{j}",
                        va="center", ha="center", fontsize=8, color="black"
                    )

    # Προσθήκη due dates
    for j in JOBS:
        Dj = jobs_due_date[j]
        ax.axvline(Dj, color=colors(j), linestyle="--", linewidth=1)
        ax.text(Dj, max(yticks) + 0.5, f"D{j}={Dj}", rotation=90,
                va="bottom", ha="center", fontsize=8, color=colors(j))

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("Time")
    ax.set_title(f"Gantt Chart (Total Tardiness = {result['objective']:.0f})")
    ax.grid(True, axis="x", linestyle=":", alpha=0.5)

    # Legend για jobs
    patches = [mpatches.Patch(color=colors(j), label=f"Job {j}") for j in JOBS]
    ax.legend(handles=patches, loc="upper right", fontsize=8, ncol=2)

    plt.tight_layout()
    plt.show()