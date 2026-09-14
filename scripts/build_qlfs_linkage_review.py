"""P2.5: reproducible QLFS panel-linkage audit and provisional quarterly transitions.

Extends the 2025-Q4 -> 2026-Q1 UQNO+PERSONNO linkage feasibility check (see
EXECUTION_STATUS.md) into a full, reproducible script that:

  - reproduces Astra's three demographic-consistency flag counts among matched records
    (age-change, gender-code-change, population-group-change) instead of discarding or
    accepting them on faith
  - reports the matched sample's Status coverage and the working-age attrition rate,
    since the raw UQNO+PERSONNO match rate mixes in the under-15 population for whom
    Status is not derived at all
  - computes provisional survey-side quarterly Status transitions (official StatsSA
    categories: Employed / Unemployed / Discouraged job seeker / Other not economically
    active) for the full matched panel, the panel with flagged records excluded, and the
    flagged records alone, so the sensitivity of the transition rates to the disputed
    records is visible rather than asserted

This is an empirical review output only. It does NOT decide the model-observation
mapping (Part 2 of the execution plan / "Question 6" in DECISIONS_PENDING.md), which
still gates whether or how these transitions become a calibration target.

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


def load_quarter(path: Path, encoding: str | None = None) -> pd.DataFrame:
    df, _meta = pyreadstat.read_dta(
        str(path),
        usecols=LINK_COLS,
        apply_value_formats=False,
        encoding=encoding,
    )
    df["UQNO"] = df["UQNO"].astype(str).str.strip()
    return df


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    q4_path = data_root / "qlfs-2025-04" / "qlfs-2025-q4-v1.dta"
    q1_path = data_root / "qlfs-2026-q1-v1" / "qlfs-2026-q1-v1.dta"

    q4 = load_quarter(q4_path)
    # 2026-Q1 .dta fails plain utf-8 decode on byte 0x92
    q1 = load_quarter(q1_path, encoding="latin1")

    m = q4.merge(q1, on=["UQNO", "PERSONNO"], suffixes=("_q4", "_q1"), how="inner")

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
    flags.to_csv(OUT_DIR / "qlfs_linkage_flags.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_linkage_flags.csv'}")
    print(flags.to_string(index=False))
    print()

    # Status coverage / working-age attrition, computed on the FULL quarter files (not
    # just the matched panel), since match rate against the raw quarter total conflates
    # the under-15 population (Status is not derived below age 15) with genuine attrition.
    q4_elig = q4[q4["Status"].isin([1, 2, 3, 4])]
    q1_elig = q1[q1["Status"].isin([1, 2, 3, 4])]
    elig_matched = q4_elig.merge(
        q1_elig,
        on=["UQNO", "PERSONNO"],
        suffixes=("_q4", "_q1"),
        how="inner",
    )

    coverage_rows = [
        dict(metric="q4_total", value=len(q4)),
        dict(metric="q4_status_eligible_age_15plus", value=len(q4_elig)),
        dict(metric="q1_total", value=len(q1)),
        dict(metric="q1_status_eligible_age_15plus", value=len(q1_elig)),
        dict(metric="matched_uqno_personno_raw", value=len(m)),
        dict(metric="matched_status_eligible_both_waves", value=len(elig_matched)),
        dict(metric="match_rate_raw_vs_q4_total", value=round(len(m) / len(q4), 4)),
        dict(
            metric="attrition_rate_status_eligible_vs_q4",
            value=round(1 - len(elig_matched) / len(q4_elig), 4),
        ),
        dict(
            metric="attrition_rate_status_eligible_vs_q1",
            value=round(1 - len(elig_matched) / len(q1_elig), 4),
        ),
    ]

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

    all_rows = transition_rows(m, "matched_panel_all")
    clean = m[~any_flag]
    all_rows += transition_rows(clean, "matched_panel_excl_flagged")
    flagged = m[any_flag]
    all_rows += transition_rows(flagged, "matched_panel_flagged_only")

    transitions = pd.DataFrame(all_rows)
    transitions.to_csv(OUT_DIR / "qlfs_provisional_transitions.csv", index=False)
    print(f"Wrote {OUT_DIR / 'qlfs_provisional_transitions.csv'}")
    print()
    print("=== Coverage / attrition ===")
    print(pd.DataFrame(coverage_rows).to_string(index=False))
    print()
    print("=== Employed->Employed and Unemployed->Unemployed, by population ===")
    for pop in ["matched_panel_all", "matched_panel_excl_flagged", "matched_panel_flagged_only"]:
        is_diag = transitions.origin_status == transitions.destination_status
        sub = transitions[(transitions.population == pop) & is_diag]
        print(pop)
        cols = ["origin_status", "origin_n", "transition_n", "transition_share"]
        print(sub[cols].to_string(index=False))


if __name__ == "__main__":
    main()
