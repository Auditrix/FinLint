"""FinLint Week 1 dashboard.

Compares Benford's law, Isolation Forest, the autoencoder, and two
supervised models on the VynFi journal entries, all on the same frozen
train and test split. Reads only saved results, never retrains a model on
page load, so the numbers shown are always exactly what the notebooks and
scripts already produced.
"""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "generated"

REQUIRED_FILES = [
    "model_comparison.csv",
    "benford_digit_table.csv",
    "benford_threshold_sweep.csv",
    "supervised_recall_by_fraud_type.csv",
]

# White background, orange as the primary accent, green reserved for one
# meaning only: this is the winning result. Not used decoratively elsewhere.
ORANGE = "#F97316"
RUST = "#C2410C"
PEACH = "#FDBA74"
CREAM = "#FFF3E8"
CHARCOAL = "#1F2937"
GREEN = "#16A34A"
ORANGE_FAMILY = [RUST, "#EA580C", ORANGE, "#FB923C", PEACH]


def _load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / name)


def _horizontal_grouped_bar(
    data: pd.DataFrame,
    category_field: str,
    value_field: str,
    color_field: str,
    category_sort=None,
    height: int = 320,
    color_domain: list[str] | None = None,
    color_range: list[str] | None = None,
) -> alt.Chart:
    """A horizontal grouped bar chart.

    Horizontal reads better than vertical here, since category names like
    "Benford (MAD by gl_account)" are too long to fit under a vertical bar.
    color_domain fixes which color goes with which series, since Altair
    otherwise sorts the legend alphabetically and silently reassigns colors.
    """
    color = alt.Color(f"{color_field}:N", title=None)
    if color_range is not None:
        color = alt.Color(f"{color_field}:N", title=None, scale=alt.Scale(domain=color_domain, range=color_range))
    return (
        alt.Chart(data)
        .mark_bar()
        .encode(
            y=alt.Y(f"{category_field}:N", sort=category_sort, title=None, axis=alt.Axis(labelLimit=280)),
            x=alt.X(f"{value_field}:Q"),
            color=color,
            yOffset=f"{color_field}:N",
            tooltip=[category_field, color_field, value_field],
        )
        .properties(height=height)
    )


st.set_page_config(page_title="FinLint Week 1", layout="wide", page_icon="🟠")

missing = [name for name in REQUIRED_FILES if not (DATA_DIR / name).exists()]
if missing:
    st.error(
        "Missing result files: "
        + ", ".join(missing)
        + ". Run the four anomaly modules (or notebooks/week1_comparison.ipynb) first."
    )
    st.stop()

st.markdown(
    f"""
    <style>
    div[data-testid="stMetric"] {{
        background-color: {CREAM};
        border: 1px solid {PEACH};
        border-radius: 8px;
        padding: 12px 14px 8px 14px;
    }}
    div[data-testid="stMetricValue"] {{
        color: {RUST};
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

comparison = _load_csv("model_comparison.csv")
best_row = comparison.sort_values("f1", ascending=False).iloc[0]

st.title("FinLint: Week 1 anomaly detection comparison")
st.caption(
    "Five methods, one frozen document level train and test split, "
    "VynFi journal entries, 667,584 rows, 6.2 percent real fraud."
)

metric_cols = st.columns(len(comparison))
for col, (_, row) in zip(metric_cols, comparison.iterrows()):
    with col:
        if row["method"] == best_row["method"]:
            st.markdown(
                f"<div style='color:{GREEN}; font-weight:700; font-size:0.8rem;'>&#9733; BEST OF FIVE</div>",
                unsafe_allow_html=True,
            )
        st.metric(row["method"], f"F1 {row['f1']:.3f}")
        st.caption(f"precision {row['precision']:.3f}, recall {row['recall']:.3f}, {int(row['n_flagged']):,} flagged")

st.divider()

overview_tab, tradeoff_tab, benford_tab, iforest_tab, supervised_tab = st.tabs(
    [
        "Overview",
        "Precision vs recall",
        "Benford deep dive",
        "Isolation Forest",
        "Supervised deep dive",
    ]
)

with overview_tab:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Full comparison")
        st.dataframe(
            comparison[["method", "precision", "recall", "f1", "n_flagged", "notes"]],
            hide_index=True,
            width="stretch",
            column_config={
                "precision": st.column_config.ProgressColumn("precision", min_value=0, max_value=1, format="%.3f"),
                "recall": st.column_config.ProgressColumn("recall", min_value=0, max_value=1, format="%.3f"),
                "f1": st.column_config.ProgressColumn("f1", min_value=0, max_value=1, format="%.3f"),
            },
        )
        st.caption(
            f"Best method: **{best_row['method']}**, F1 {best_row['f1']:.3f}. "
            "Unsupervised methods never see the fraud label during training, "
            "supervised methods do, which is the expected reason they lead."
        )

    with right:
        st.subheader("Precision, recall, and F1 by method")
        score_columns = comparison.melt(
            id_vars="method",
            value_vars=["precision", "recall", "f1"],
            var_name="metric",
            value_name="score",
        )
        st.altair_chart(
            _horizontal_grouped_bar(
                score_columns,
                "method",
                "score",
                "metric",
                category_sort=list(comparison["method"]),
                color_domain=["precision", "recall", "f1"],
                color_range=[ORANGE, GREEN, RUST],
            ),
            width="stretch",
        )

with tradeoff_tab:
    st.subheader("Precision versus recall, all five methods at once")
    st.caption(
        "Bubble size is how many rows each method flagged. Top right is where you want to be, "
        "high precision and high recall together. Click a method in the legend to highlight it."
    )
    # The legend can use any colors to tell the five methods apart, that part
    # is free. The one rule kept is that the winning method is always green,
    # matching the "best of five" badge above, everywhere it appears.
    method_order = list(comparison["method"])
    non_winner_oranges = iter(ORANGE_FAMILY)
    scatter_colors = [GREEN if m == best_row["method"] else next(non_winner_oranges) for m in method_order]

    highlight = alt.selection_point(fields=["method"], bind="legend")
    scatter = (
        alt.Chart(comparison)
        .mark_circle()
        .encode(
            x=alt.X("recall:Q", scale=alt.Scale(domain=[0, 1]), title="Recall"),
            y=alt.Y("precision:Q", scale=alt.Scale(domain=[0, 1]), title="Precision"),
            size=alt.Size("n_flagged:Q", legend=None, scale=alt.Scale(range=[200, 2200])),
            color=alt.Color("method:N", title=None, scale=alt.Scale(domain=method_order, range=scatter_colors)),
            opacity=alt.condition(highlight, alt.value(0.9), alt.value(0.25)),
            tooltip=["method", "precision", "recall", "f1", "n_flagged"],
        )
        .add_params(highlight)
        .properties(height=460)
    )
    text = (
        alt.Chart(comparison)
        .mark_text(dy=-16, fontSize=12, color=CHARCOAL)
        .encode(x="recall:Q", y="precision:Q", text="method:N")
    )
    st.altair_chart((scatter + text), width="stretch")
    st.caption(
        "Random guessing would sit at precision 0.062, the true fraud rate, "
        "no matter what recall it happened to reach. Every method here clears that line by a wide margin."
    )

with benford_tab:
    st.subheader("Why Benford's law scored weakly")
    benford_col1, benford_col2 = st.columns([1, 1])
    with benford_col1:
        st.caption("First digit distribution: observed vs expected")
        digit_table = _load_csv("benford_digit_table.csv")
        digit_columns = digit_table.melt(
            id_vars="digit",
            value_vars=["expected", "observed"],
            var_name="series",
            value_name="share",
        )
        st.altair_chart(
            _horizontal_grouped_bar(
                digit_columns,
                "digit",
                "share",
                "series",
                category_sort=list(range(1, 10)),
                color_domain=["expected", "observed"],
                color_range=[GREEN, ORANGE],
            ),
            width="stretch",
        )
        st.caption("The observed pattern already matches Benford closely, real transaction amounts are not faked.")

    with benford_col2:
        st.caption("Threshold sweep: lift over the random baseline stays near 1.0 everywhere")
        sweep = _load_csv("benford_threshold_sweep.csv")
        top_sweep = sweep.sort_values("lift_over_base_rate", ascending=False).head(10)
        st.dataframe(
            top_sweep[["group_column", "min_rows", "threshold", "lift_over_base_rate", "recall"]],
            hide_index=True,
            width="stretch",
            column_config={
                "lift_over_base_rate": st.column_config.ProgressColumn(
                    "lift over base rate", min_value=0, max_value=1.5, format="%.3f"
                ),
            },
        )
        st.caption(
            "Fifteen grouping and threshold combinations tried. None cleared meaningful "
            "lift over random guessing, this fraud does not look like an unusual dollar amount."
        )

with iforest_tab:
    st.subheader("Isolation Forest: precision vs recall at every threshold")
    pr_curve_path = DATA_DIR / "isolation_forest_pr_curve.png"
    if pr_curve_path.exists():
        st.image(str(pr_curve_path), width=650)
        st.caption(
            "Isolation Forest never sees the fraud label during training, contamination is set from the "
            "real training fraud rate, a fair use of the label as a setting, not as something learned."
        )
    else:
        st.info("Run src/finlint/anomaly/isolation_forest.py to generate the precision-recall curve.")

with supervised_tab:
    st.subheader("Which fraud types get caught, supervised models")
    recall_by_type = _load_csv("supervised_recall_by_fraud_type.csv")
    method_choice = st.radio(
        "Model",
        recall_by_type["method"].unique(),
        horizontal=True,
    )
    subset = recall_by_type[recall_by_type["method"] == method_choice].sort_values("recall", ascending=False)
    st.altair_chart(
        alt.Chart(subset)
        .mark_bar(color=ORANGE)
        .encode(
            y=alt.Y("fraud_type:N", sort=list(subset["fraud_type"]), title=None, axis=alt.Axis(labelLimit=200)),
            x=alt.X("recall:Q"),
            tooltip=["fraud_type", "fraud_rows", "caught", "recall"],
        )
        .properties(height=25 * len(subset) + 40),
        width="stretch",
    )
    st.dataframe(
        subset,
        hide_index=True,
        width="stretch",
        column_config={"recall": st.column_config.ProgressColumn("recall", min_value=0, max_value=1, format="%.3f")},
    )

st.divider()
st.caption(
    "All five methods run through the same frozen document level split, saved at "
    "splits/test_document_ids.csv, so no method sees an easier or harder test set than another."
)
