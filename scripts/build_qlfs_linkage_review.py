"""P2.5: reproducible QLFS panel-linkage audit and provisional quarterly transitions.

Extends the 2025-Q4 -> 2026-Q1 UQNO+PERSONNO linkage feasibility check (see
EXECUTION_STATUS.md) into a full, reproducible script that:

  - reproduces Astra's three demographic-consistency flag counts among matched records
    (age-change, gender-code-change, population-group-change) instead of discarding or
    accepting them on faith
  - defines the analysis population by ORIGIN (2025-Q4) age eligibility -- the PRIMARY
    universe is age 15+ (the universe `Status` is actually derived for, no upper
    bound), with the 15-64 convention used elsewhere in this project
    (discouraged_share/long_term_share) reported as an explicit alternative
  - for each origin-eligible person, separates four distinct outcomes rather than
    collapsing everything into one "unmatched" figure: matched with a valid,
    in-universe destination status; matched but the destination status is out of the
    age universe (ONLY possible under the 15-64 alternative -- someone turned 65
    between waves); matched but the destination status is invalid for some other
    reason; and failed linkage (UQNO+PERSONNO simply not found in 2026-Q1 at all).
    Failed linkage is further split into whole-dwelling non-continuity (the UQNO
    itself is not seen again, consistent with -- but not proof of -- scheduled
    rotation) and within-dwelling person-level non-match, since no rotation/wave/
    visit design variable exists in either extract (confirmed by a full column
    name+label search) to identify scheduled rotation directly
  - computes provisional survey-side quarterly Status transitions (official StatsSA
    categories) for the PRIMARY (15+) matched-valid population, the panel with
    demographic-flagged records excluded, and the flagged records alone, and reports
    the ABSOLUTE (percentage-point, on a 0-100 scale) and RELATIVE (%) difference
    between the full and excl-flagged panels for every origin/destination cell

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
    data/review_v2/qlfs_origin_eligibility_outcomes.csv
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
_AGE_15_PLUS_LABEL = (
    "age 15+ (no upper bound; the universe Status is actually derived for) -- PRIMARY"
)
_AGE_15_64_LABEL = "age 15-64 (discouraged_share/long_term_share convention) -- alternative"
AGE_UNIVERSES = {
    "15_plus": (_AGE_15_PLUS_LABEL, lambda a: a >= 15),
    "15_to_64": (_AGE_15_64_LABEL, lambda a: (a >= 15) & (a <= 64)),
}
PRIMARY_AGE_UNIVERSE = "15_plus"


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


def build_linkage_flags(m: pd.DataFrame, q4: pd.DataFrame, q1: pd.DataFrame):
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


def build_origin_eligibility_outcomes(
    q4: pd.DataFrame, q1: pd.DataFrame, universe_key: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Origin (2025-Q4) age-eligibility defines the analysis population; every person
    in it gets exactly one outcome. Returns (outcome_summary, matched_valid_frame) --
    the second is the frame to feed into transition_rows for this universe.
    """
    label, agefilter = AGE_UNIVERSES[universe_key]
    q4e = q4[q4["Status"].isin([1, 2, 3, 4]) & agefilter(q4["Q14AGE"])].reset_index(drop=True)
    q1_uqnos = set(q1["UQNO"])

    m = q4e.merge(q1, on=["UQNO", "PERSONNO"], how="left", suffixes=("_q4", "_q1"), indicator=True)
    linked = m["_merge"] == "both"
    dest_status_valid = m["Status_q1"].isin([1, 2, 3, 4])
    dest_age_ok = agefilter(m["Q14AGE_q1"]).fillna(False)

    matched_valid = linked & dest_status_valid & dest_age_ok
    dest_age_excl = linked & dest_status_valid & ~dest_age_ok
    dest_invalid_other = linked & ~dest_status_valid
    failed_link = ~linked

    dwelling_gone = ~m.loc[failed_link, "UQNO"].isin(q1_uqnos)

    total = len(q4e)
    summary = pd.DataFrame(
        [
            dict(
                age_universe=universe_key,
                description=label,
                component="origin_eligible_total",
                n=total,
                share_of_origin_eligible=1.0,
            ),
            dict(
                age_universe=universe_key,
                description=label,
                component="matched_valid_destination",
                n=int(matched_valid.sum()),
                share_of_origin_eligible=round(matched_valid.sum() / total, 4),
            ),
            dict(
                age_universe=universe_key,
                description=label,
                component="destination_age_exclusion",
                n=int(dest_age_excl.sum()),
                share_of_origin_eligible=round(dest_age_excl.sum() / total, 4),
            ),
            dict(
                age_universe=universe_key,
                description=label,
                component="destination_status_invalid_other",
                n=int(dest_invalid_other.sum()),
                share_of_origin_eligible=round(dest_invalid_other.sum() / total, 4),
            ),
            dict(
                age_universe=universe_key,
                description=label,
                component="failed_linkage_total",
                n=int(failed_link.sum()),
                share_of_origin_eligible=round(failed_link.sum() / total, 4),
            ),
            dict(
                age_universe=universe_key,
                description=label,
                component="failed_linkage_whole_dwelling_not_seen_in_q1",
                n=int(dwelling_gone.sum()),
                share_of_origin_eligible=round(dwelling_gone.sum() / total, 4),
            ),
            dict(
                age_universe=universe_key,
                description=label,
                component="failed_linkage_dwelling_continues_person_not_matched",
                n=int((~dwelling_gone).sum()),
                share_of_origin_eligible=round((~dwelling_gone).sum() / total, 4),
            ),
        ]
    )
    return summary, m.loc[matched_valid]


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
        # Percentage-POINT difference: shares are stored as fractions (0-1), so a
        # percentage-point difference requires multiplying by 100 -- 0.9062 to 0.9104
        # is a +0.42pp move, not +0.0042pp. Relative difference is a plain ratio and
        # needs no such rescaling.
        abs_diff_pp = round((c_share - f_share) * 100, 2)
        rel_diff = round((c_share - f_share) / f_share, 4) if f_share else None
        rows.append(
            dict(
                origin_status=key[0],
                destination_status=key[1],
                share_full_panel=f_share,
                share_excl_flagged=c_share,
                absolute_difference_pp=abs_diff_pp,
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

    outcome_tables = []
    matched_valid_frames = {}
    for key in AGE_UNIVERSES:
        summary, matched_valid = build_origin_eligibility_outcomes(q4, q1, key)
        outcome_tables.append(summary)
        matched_valid_frames[key] = matched_valid
    outcomes = pd.concat(outcome_tables, ignore_index=True)
    outcomes.to_csv(OUT_DIR / "qlfs_origin_eligibility_outcomes.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_origin_eligibility_outcomes.csv'}")
    print(outcomes.to_string(index=False))
    print()

    # Transitions use the PRIMARY (origin age 15+) matched-valid population.
    primary_matched = matched_valid_frames[PRIMARY_AGE_UNIVERSE]
    primary_matched_flagged = primary_matched.merge(
        m[["UQNO", "PERSONNO"]].assign(_flagged=any_flag.to_numpy()),
        on=["UQNO", "PERSONNO"],
        how="left",
    )
    primary_matched_flagged["_flagged"] = primary_matched_flagged["_flagged"].fillna(False)

    all_rows = transition_rows(primary_matched_flagged, "matched_panel_all")
    clean = primary_matched_flagged[~primary_matched_flagged["_flagged"]]
    all_rows += transition_rows(clean, "matched_panel_excl_flagged")
    flagged_only = primary_matched_flagged[primary_matched_flagged["_flagged"]]
    all_rows += transition_rows(flagged_only, "matched_panel_flagged_only")
    transitions = pd.DataFrame(all_rows)
    transitions.to_csv(OUT_DIR / "qlfs_provisional_transitions.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_provisional_transitions.csv'}")

    sensitivity = build_transition_sensitivity(transitions)
    sensitivity.to_csv(OUT_DIR / "qlfs_transition_sensitivity.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_transition_sensitivity.csv'}")
    print()
    print("=== Full panel vs excl-flagged: absolute (pp, 0-100 scale) and relative differences ===")
    print(sensitivity.to_string(index=False))
    print()
    print("All counts above are UNWEIGHTED sample diagnostics -- no QLFS design weight applied.")


if __name__ == "__main__":
    main()
