"""Generate experiment charts for defense PPT."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ppt", "charts")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def chart_recognition_metrics():
    """Behavior recognition metrics bar chart."""
    behaviors = ["低头", "睡觉", "举手", "转头交谈"]
    precision = [0.87, 0.92, 0.89, 0.83]
    recall = [0.84, 0.88, 0.91, 0.80]
    f1 = [0.85, 0.90, 0.90, 0.81]

    x = np.arange(len(behaviors))
    width = 0.25

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar(x - width, precision, width, label="Precision", color="#4472C4")
    bars2 = ax.bar(x, recall, width, label="Recall", color="#ED7D31")
    bars3 = ax.bar(x + width, f1, width, label="F1", color="#70AD47")

    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("Behavior Recognition Metrics", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(behaviors, fontsize=11)
    ax.set_ylim(0.7, 1.0)
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            h = bar.get_height()
            ax.annotate(f"{h:.2f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "recognition_metrics.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")


def chart_performance():
    """Performance metrics horizontal bar chart."""
    metrics = ["Real-time FPS", "Offline Analysis", "Report Generation", "API Response"]
    values = [12, 0.8, 2, 1]
    labels = ["10-12 FPS", "0.4-0.8x duration", "< 2 seconds", "~1 second"]
    colors = ["#4472C4", "#ED7D31", "#70AD47", "#FFC000"]

    fig, ax = plt.subplots(figsize=(8, 4))
    y = np.arange(len(metrics))
    bars = ax.barh(y, values, color=colors, height=0.5)

    ax.set_yticks(y)
    ax.set_yticklabels(metrics, fontsize=11)
    ax.set_title("System Performance Metrics", fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)

    for bar, label in zip(bars, labels):
        w = bar.get_width()
        ax.annotate(label, xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(8, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=10)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "performance_metrics.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")


def chart_parameter_comparison():
    """Parameter comparison table-style chart."""
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.axis("off")

    headers = ["Parameter", "Sensitive", "Default", "Stable"]
    data = [
        ["Consecutive Frames", "3", "4-6", "7-8"],
        ["Confidence Threshold", "0.25", "0.35", "0.45"],
        ["Alert After (s)", "3", "5", "8"],
    ]

    table = ax.table(cellText=data, colLabels=headers, loc="center",
                     cellLoc="center", colColours=["#4472C4"] * 4)
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.8)

    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(color="white", fontweight="bold")
            cell.set_facecolor("#4472C4")
        else:
            cell.set_facecolor("#F2F2F2" if row % 2 == 0 else "white")
        cell.set_edgecolor("#D9D9D9")

    ax.set_title("Parameter Configuration Comparison", fontsize=14,
                 fontweight="bold", pad=20)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, "parameter_comparison.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")


if __name__ == "__main__":
    chart_recognition_metrics()
    chart_performance()
    chart_parameter_comparison()
    print("All charts generated in:", OUTPUT_DIR)
