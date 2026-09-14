"""P2.5: reproducible QLFS panel-linkage audit and provisional quarterly transitions.

Extends the 2025-Q4 -> 2026-Q1 UQNO+PERSONNO linkage feasibility check (see
EXECUTION_STATUS.md) into a full, reproducible script that:

  - reproduces Astra's three demographic-consistency flag counts among matched records
    (age-change, gender-code-change, population-group-change) instead of discarding or
    accepting them on faith
  - reports the matched sample's Status coverage under TWO explicit age universes --
    age 15+ (the universe `Status` is actually derived for, no upper bound) and the
    15-64 convention used elsewhere in this project for discouraged_share/long_term_share
    -- rather than mislabelling the unbounded 15+ population as "working-age" (a term
    that implies the 15-64 convention)
  - decomposes the unmatched share into whole-dwelling non-continuity (the UQNO itself is
    not seen again, consistent with -- but not proof of -- scheduled rotation) and
    person-level non-match within a continuing dwelling (a different, more clearly
    attrition-like pattern), since no rotation/wave/visit design variable exists in
    either extract to identify scheduled rotation directly (confirmed by a full column
    name+label search, not just a keyword subset) -- a mechanical rotation-share
    subtraction is deliberately NOT applied
  - computes provisional survey-side quarterly Status transitions (official StatsSA
    categories) for the full matched panel, the panel with flagged records excluded, and
    the flagged records alone, and reports the ABSOLUTE (percentage-point) and RELATIVE
    (%) difference between the full and excl-flagged panels for every origin/destination
    cell, not just the diagonal

This is an empirical review output only, and all counts are UNWEIGHTED sample
diagnostics -- no QLFS design weight is applied anywhere in this script. It does NOT
decide the model-observation mapping (Part 2 of the execution plan / "Question 6" in
DECISIONS_PENDING.md), which still gates whether or how these transitions become a
calibration target.

The age-change flag definition matters and is stated explicitly: a raw age difference
between one-quarter-apart interviews of the same UQNO+PERSONNO slot is normal (0 if the
birthday hasn't passed, +1 if it has). The flag fires only when the difference is
anything OTHER than 0 or +1 -- i.e. an implausible change for a single real respondent,
which is the definition that reproduces Astra's reported count of 516 exactly.

Usage:
    python -m scripts.build_qlfs_linkage_review

Requires THESIS_DATA_ROOT set (see data/README.md). Writes:
    data/review_v2/qlfs_linkage_flags.csv
    data/review_v2/qlfs_provisional_transitions.csv
    data/review_v2/qlfs_transition_sensitivity.csv
    data/review_v2/qlfs_age_universe_comparison.csv
    data/review_v2/qlfs_attrition_decomposition.csv
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyreadstat

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "review_v2"

STATUS_LABELS = {1: "Employed", 2: "Unemployed", 3: "Discouraged", 4: "Other_NEA"}
LINK_COLS = ["UQNO", "PERSONNO", "Q13GENDER", "Q14AGE", "Q15POPULATION", "Status"]

# No rotation/wave/visit/panel/PSU/cluster variable exists in either extract beyond
# Stratum -- confirmed live against the full column-name AND label list for both files,
# not just a keyword subset (see qlfs_rotation_search in the review scratch history).
# A scheduled-rotation share is therefore not directly identifiable and is never
# subtracted mechanically anywhere in this script.
_AGE_15_PLUS_LABEL = "age 15+ (no upper bound; the universe Status is actually derived for)"
_AGE_15_64_LABEL = "age 15-64 (discouraged_share/long_term_share convention)"
AGE_UNIVERSES = {
    "15_plus": (_AGE_15_PLUS_LABEL, lambda a: a >= 15),
    "15_to_64": (_AGE_15_64_LABEL, lambda a: (a >= 15) & (a <= 64)),
}


def load_quarter(path: Path, encoding: str | None = None) -> pd.DataFrame:
    df, _meta = pyreadstat.read_dta(
        str(path),
        usecols=LINK_COLS,
        apply_value_formats=False,
        encoding=encoding,
    )
    df["UQNO"] = df["UQNO"].astype(str).str.strip()
    return df


def transition_rows(frame: pd.DataFrame, population: str) -> list[dict]:
    f = frame.copy()
    f["s4"] = f["Status_q4"].map(STATUS_LABELS)
    f["s1"] = f["Status_q1"].map(STATUS_LABELS)
    f = f.dropna(subset=["s4", "s1"])
    counts = pd.crosstab(f["s4"], f["s1"])
    shares = pd.crosstab(f["s4"], f["s1"], normalize="index")
    rows = []
    for origin in STATUS_LABELS.values():
        if origin not in counts.index:
            continue
        origin_n = int(counts.loc[origin].sum())
        for dest in STATUS_LABELS.values():
            rows.append(
                dict(
                    population=population,
                    origin_status=origin,
                    destination_status=dest,
                    origin_n=origin_n,
                    transition_n=int(counts.loc[origin].get(dest, 0)),
                    transition_share=round(float(shares.loc[origin].get(dest, 0.0)), 4),
                )
            )
    return rows


def build_linkage_flags(m: pd.DataFrame, q4: pd.DataFrame, q1: pd.DataFrame) -> pd.DataFrame:
    age_diff = m["Q14AGE_q1"] - m["Q14AGE_q4"]
    age_flag = ~age_diff.isin([0, 1])
    gender_flag = m["Q13GENDER_q4"] != m["Q13GENDER_q1"]
    pop_flag = m["Q15POPULATION_q4"] != m["Q15POPULATION_q1"]
    any_flag = age_flag | gender_flag | pop_flag
    flags = pd.DataFrame(
        [
            dict(flag="age_change_diff_not_0_or_1", n=int(age_flag.sum())),
            dict(flag="gender_code_change", n=int(gender_flag.sum())),
            dict(flag="population_group_change", n=int(pop_flag.sum())),
            dict(flag="any_flag_distinct_records", n=int(any_flag.sum())),
            dict(flag="matched_records_total", n=int(len(m))),
            dict(flag="q4_total_respondents", n=int(len(q4))),
            dict(flag="q1_total_respondents", n=int(len(q1))),
        ]
    )
    return flags, any_flag


def build_age_universe_comparison(q4: pd.DataFrame, q1: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, (label, agefilter) in AGE_UNIVERSES.items():
        q4e = q4[q4["Status"].isin([1, 2, 3, 4]) & agefilter(q4["Q14AGE"])]
        q1e = q1[q1["Status"].isin([1, 2, 3, 4]) & agefilter(q1["Q14AGE"])]
        me = q4e.merge(q1e, on=["UQNO", "PERSONNO"], suffixes=("_q4", "_q1"), how="inner")
        rows.append(
            dict(
                age_universe=key,
                description=label,
                q4_eligible_n=len(q4e),
                q1_eligible_n=len(q1e),
                matched_n=len(me),
                unmatched_share_vs_q4=round(1 - len(me) / len(q4e), 4),
                unmatched_share_vs_q1=round(1 - len(me) / len(q1e), 4),
            )
        )
    return pd.DataFrame(rows)


def build_attrition_decomposition(q4_elig: pd.DataFrame, q1_elig: pd.DataFrame) -> pd.DataFrame:
    """Splits the unmatched share by what is actually observable: whether the
    RESPONDENT'S DWELLING (UQNO) reappears at all in the next wave, versus whether
    this specific person is matched within a dwelling that does reappear. The first
    is consistent with (but not confirmed as) scheduled rotation out of the panel;
    the second is a within-household pattern -- the household kept being surveyed,
    but this person specifically was not matched -- that looks more like ordinary
    attrition (moved, temporarily absent, etc.) than a scheduled panel exit. This is
    the finest split the available fields support; it is NOT a rotation-group
    variable and is not treated as one.
    """
    q4_dwellings = set(q4_elig["UQNO"])
    q1_dwellings = set(q1_elig["UQNO"])
    continuing = q4_dwellings & q1_dwellings

    q4_in_cont = q4_elig[q4_elig["UQNO"].isin(continuing)]
    q1_in_cont = q1_elig[q1_elig["UQNO"].isin(continuing)]
    person_matched = q4_in_cont.merge(q1_in_cont, on=["UQNO", "PERSONNO"], how="inner")

    total = len(q4_elig)
    dwelling_dropout_n = total - len(q4_in_cont)
    person_dropout_n = len(q4_in_cont) - len(person_matched)
    matched_n = len(person_matched)

    return pd.DataFrame(
        [
            dict(
                component="whole_dwelling_not_seen_in_q1",
                n=dwelling_dropout_n,
                share_of_q4_eligible=round(dwelling_dropout_n / total, 4),
                note=(
                    "UQNO not observed at all in 2026-Q1. Consistent with scheduled rotation out "
                    "of the panel, but not confirmed as such -- no rotation/wave variable exists "
                    "in either extract to verify it."
                ),
            ),
            dict(
                component="person_not_matched_within_continuing_dwelling",
                n=person_dropout_n,
                share_of_q4_eligible=round(person_dropout_n / total, 4),
                note=(
                    "UQNO IS observed again in 2026-Q1 (the dwelling continued in the panel), but "
                    "this PERSONNO was not. Looks more like ordinary within-household attrition "
                    "(moved out, temporarily absent, etc.) than a scheduled panel exit, since the "
                    "dwelling itself was not scheduled to leave."
                ),
            ),
            dict(
                component="matched",
                n=matched_n,
                share_of_q4_eligible=round(matched_n / total, 4),
                note="UQNO+PERSONNO matched with valid Status in both waves.",
            ),
        ]
    )


def build_transition_sensitivity(transitions: pd.DataFrame) -> pd.DataFrame:
    full = transitions[transitions.population == "matched_panel_all"].set_index(
        ["origin_status", "destination_status"]
    )
    clean = transitions[transitions.population == "matched_panel_excl_flagged"].set_index(
        ["origin_status", "destination_status"]
    )
    rows = []
    for key in full.index:
        f_share = full.loc[key, "transition_share"]
        c_share = clean.loc[key, "transition_share"] if key in clean.index else float("nan")
        abs_diff = round(c_share - f_share, 4)
        rel_diff = round((c_share - f_share) / f_share, 4) if f_share else None
        rows.append(
            dict(
                origin_status=key[0],
                destination_status=key[1],
                share_full_panel=f_share,
                share_excl_flagged=c_share,
                absolute_difference_pp=abs_diff,
                relative_difference=rel_diff,
            )
        )
    return pd.DataFrame(rows)


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    q4_path = data_root / "qlfs-2025-04" / "qlfs-2025-q4-v1.dta"
    q1_path = data_root / "qlfs-2026-q1-v1" / "qlfs-2026-q1-v1.dta"

    q4 = load_quarter(q4_path)
    # 2026-Q1 .dta fails plain utf-8 decode on byte 0x92
    q1 = load_quarter(q1_path, encoding="latin1")

    m = q4.merge(q1, on=["UQNO", "PERSONNO"], suffixes=("_q4", "_q1"), how="inner")

    flags, any_flag = build_linkage_flags(m, q4, q1)
    flags.to_csv(OUT_DIR / "qlfs_linkage_flags.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_linkage_flags.csv'}")
    print(flags.to_string(index=False))
    print()

    age_cmp = build_age_universe_comparison(q4, q1)
    age_cmp.to_csv(OUT_DIR / "qlfs_age_universe_comparison.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_age_universe_comparison.csv'}")
    print(age_cmp.to_string(index=False))
    print()

    q4_elig = q4[q4["Status"].isin([1, 2, 3, 4])]
    q1_elig = q1[q1["Status"].isin([1, 2, 3, 4])]
    attrition = build_attrition_decomposition(q4_elig, q1_elig)
    attrition.to_csv(OUT_DIR / "qlfs_attrition_decomposition.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_attrition_decomposition.csv'}")
    print(attrition.to_string(index=False))
    print()

    all_rows = transition_rows(m, "matched_panel_all")
    clean = m[~any_flag]
    all_rows += transition_rows(clean, "matched_panel_excl_flagged")
    flagged = m[any_flag]
    all_rows += transition_rows(flagged, "matched_panel_flagged_only")
    transitions = pd.DataFrame(all_rows)
    transitions.to_csv(OUT_DIR / "qlfs_provisional_transitions.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_provisional_transitions.csv'}")

    sensitivity = build_transition_sensitivity(transitions)
    sensitivity.to_csv(OUT_DIR / "qlfs_transition_sensitivity.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_transition_sensitivity.csv'}")
    print()
    print("=== Full panel vs excl-flagged: absolute (pp) and relative differences ===")
    print(sensitivity.to_string(index=False))
    print()
    print("All counts above are UNWEIGHTED sample diagnostics -- no QLFS design weight applied.")


if __name__ == "__main__":
    main()
