from __future__ import annotations

import pandas as pd

from config import FIGURES_DIR, TABLES_DIR, ensure_directories
from utils import require_file, safe_write_csv


ACCESSIBILITY_INPUTS = {
    "full": TABLES_DIR / "origin_accessibility_classified_full.csv",
    "clean100": TABLES_DIR / "origin_accessibility_classified_clean100.csv",
    "clean250": TABLES_DIR / "origin_accessibility_classified_clean250.csv",
}

DISTRICT_INPUTS = {
    "full": TABLES_DIR / "district_accessibility_summary_full_corrected.csv",
    "clean100": TABLES_DIR / "district_accessibility_summary_clean100.csv",
    "clean250": TABLES_DIR / "district_accessibility_summary_clean250.csv",
}


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load_accessibility(origin_set: str) -> pd.DataFrame:
    df = pd.read_csv(require_file(ACCESSIBILITY_INPUTS[origin_set]))
    df["origin_set"] = origin_set
    df["official_access_15"] = df["official_access_15"].apply(to_bool)
    df["osm_access_15"] = df["osm_access_15"].apply(to_bool)
    df["disagrees"] = df["disagrees"].apply(to_bool)
    df["difference_minutes"] = pd.to_numeric(df["difference_minutes"], errors="coerce")
    return df


def robustness_summary() -> pd.DataFrame:
    rows = []
    for origin_set in ["full", "clean100", "clean250"]:
        df = load_accessibility(origin_set)
        for amenity_type, group in df.groupby("amenity_type"):
            official_share = group["official_access_15"].mean()
            osm_share = group["osm_access_15"].mean()
            rows.append(
                {
                    "origin_set": origin_set,
                    "amenity_type": amenity_type,
                    "n_origins": int(group["origin_id"].nunique()),
                    "official_share_accessible_15": official_share,
                    "osm_share_accessible_15": osm_share,
                    "difference_share_percentage_points": (osm_share - official_share) * 100.0,
                    "total_disagreement_share": group["disagrees"].mean(),
                    "osm_false_access_share": (group["distortion_class"] == "osm_false_access").mean(),
                    "osm_hidden_access_share": (group["distortion_class"] == "osm_hidden_access").mean(),
                    "median_difference_minutes": group["difference_minutes"].median(),
                    "mean_difference_minutes": group["difference_minutes"].mean(),
                }
            )
    return pd.DataFrame(rows)


def district_change_table() -> pd.DataFrame:
    full = pd.read_csv(require_file(DISTRICT_INPUTS["full"]))[
        ["district", "amenity_type", "difference_share_percentage_points"]
    ].rename(columns={"difference_share_percentage_points": "original_difference_share_percentage_points"})
    clean100 = pd.read_csv(require_file(DISTRICT_INPUTS["clean100"]))[
        ["district", "amenity_type", "difference_share_percentage_points"]
    ].rename(columns={"difference_share_percentage_points": "clean100_difference_share_percentage_points"})
    clean250 = pd.read_csv(require_file(DISTRICT_INPUTS["clean250"]))[
        ["district", "amenity_type", "difference_share_percentage_points"]
    ].rename(columns={"difference_share_percentage_points": "clean250_difference_share_percentage_points"})

    out = full.merge(clean100, on=["district", "amenity_type"], how="outer").merge(
        clean250,
        on=["district", "amenity_type"],
        how="outer",
    )
    out["change_after_cleaning"] = (
        out["clean100_difference_share_percentage_points"]
        - out["original_difference_share_percentage_points"]
    )
    out["clean250_change_after_cleaning"] = (
        out["clean250_difference_share_percentage_points"]
        - out["original_difference_share_percentage_points"]
    )
    return out.sort_values(["district", "amenity_type"]).reset_index(drop=True)


def save_barplot(summary: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order = ["library", "playground", "sports_facility"]
    sets = ["full", "clean100", "clean250"]
    pivot = summary.pivot(index="amenity_type", columns="origin_set", values="difference_share_percentage_points")
    pivot = pivot.reindex(order)

    x = range(len(pivot.index))
    width = 0.24
    fig, ax = plt.subplots(figsize=(8, 5))
    offsets = {"full": -width, "clean100": 0.0, "clean250": width}
    colors = {"full": "#4c78a8", "clean100": "#f58518", "clean250": "#54a24b"}
    for origin_set in sets:
        values = pivot[origin_set].to_numpy()
        ax.bar([idx + offsets[origin_set] for idx in x], values, width=width, label=origin_set, color=colors[origin_set])
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(pivot.index)
    ax.set_ylabel("OSM minus official accessible share (percentage points)")
    ax.set_title("Robustness of OSM-official accessibility difference")
    ax.legend()
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "robustness_accessibility_difference_barplot.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def same_direction(a: float, b: float) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    if abs(a) < 1 and abs(b) < 1:
        return True
    return (a >= 0 and b >= 0) or (a <= 0 and b <= 0)


def write_interpretation(summary: pd.DataFrame, district_changes: pd.DataFrame) -> None:
    full = summary[summary["origin_set"] == "full"].set_index("amenity_type")
    clean = summary[summary["origin_set"] == "clean100"].set_index("amenity_type")
    rows = []
    affected = []
    for amenity_type in full.index:
        original = full.loc[amenity_type, "difference_share_percentage_points"]
        cleaned = clean.loc[amenity_type, "difference_share_percentage_points"]
        change = cleaned - original
        stable = same_direction(original, cleaned) and abs(change) <= 5.0
        rows.append((amenity_type, original, cleaned, change, stable))
        if not stable:
            affected.append(amenity_type)

    lines = ["# Robustness interpretation", ""]
    if not affected:
        lines.append(
            "The direction and approximate size of the main findings remain stable after "
            "clean100 origin-quality filtering, so the results are robust to origin-quality filtering."
        )
    else:
        lines.append(
            "The cleaned results change substantially for "
            + ", ".join(affected)
            + ". This indicates that some original disagreement was driven by edge cells, "
            "harbour/water-adjacent cells, or poorly snapped origins."
        )
    lines.append("")
    lines.append("A change larger than 5 percentage points or a direction change is treated as substantial.")
    lines.append("")
    lines.append("| Amenity type | Full pp difference | Clean100 pp difference | Change pp | Stable |")
    lines.append("|---|---:|---:|---:|---|")
    for amenity_type, original, cleaned, change, stable in rows:
        lines.append(f"| {amenity_type} | {original:.2f} | {cleaned:.2f} | {change:.2f} | {stable} |")

    district_changes = district_changes.copy()
    district_changes["abs_change_after_cleaning"] = district_changes["change_after_cleaning"].abs()
    top = district_changes.sort_values("abs_change_after_cleaning", ascending=False).head(10)
    lines.extend(["", "## Districts most affected by clean100 filtering", ""])
    lines.append("| District | Amenity type | Change pp |")
    lines.append("|---|---|---:|")
    for row in top.itertuples(index=False):
        lines.append(f"| {row.district} | {row.amenity_type} | {row.change_after_cleaning:.2f} |")

    output = TABLES_DIR / "robustness_interpretation.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ensure_directories()
    summary = robustness_summary()
    district_changes = district_change_table()
    safe_write_csv(summary, TABLES_DIR / "robustness_summary_by_origin_set.csv")
    safe_write_csv(district_changes, TABLES_DIR / "district_robustness_comparison.csv")
    save_barplot(summary)
    write_interpretation(summary, district_changes)
    print("Saved robustness summaries, comparison table, barplot, and interpretation notes.")


if __name__ == "__main__":
    main()
