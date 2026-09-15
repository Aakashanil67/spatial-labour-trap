"""PROTOTYPE, review-only: the joint stock-to-transition covariance resampling protocol
requested in Astra's `REVIEW_FOLLOWUP.md` (deliverable 2), specified in full at
`data/review_v2/qlfs_joint_covariance_protocol.md`.

This is a concrete, testable protocol specification, not the production weighting matrix:
it is not wired into `scripts/build_qlfs_candidate_moments.py`'s `main()`, does not write
to `data/review_v2/qlfs_*.csv`, and is not consumed by any calibration code. Its purpose is
to make the specification in the .md file precise enough to review and to test against
synthetic fixtures (`tests/test_qlfs_joint_covariance_protocol.py`) -- exactly the
"implementable protocol... not the production weighting matrix" the review asked for.

Core idea: ONE per-stratum household resample per replicate, over the UNION of the 2026-Q1
stock frame's households and the matched (2025-Q4 -> 2026-Q1) transition frame's households,
using `Stratum` as the shared stratification key (verified identical to `Stratum_q4` for
every matched record -- see the .md spec's "cross-quarter consistency" section). The SAME
per-household multiplier map is applied to both frames in that replicate, so a household
appearing in both gets one shared draw, giving genuine joint (not independently-resampled)
sampling covariance between stock and transition moments.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _draw_multiplier_map(strata_households: dict, rng: np.random.Generator) -> dict[str, int]:
    """One per-stratum with-replacement household draw, matching the size of each stratum's
    own observed household set. Shared by both frames in a joint replicate."""
    mult_map: dict[str, int] = {}
    for hh_ids in strata_households.values():
        n_h = len(hh_ids)
        draws = rng.choice(hh_ids, size=n_h, replace=True)
        vals, counts = np.unique(draws, return_counts=True)
        for v, c in zip(vals, counts, strict=True):
            mult_map[v] = mult_map.get(v, 0) + int(c)
    return mult_map


def joint_stock_transition_bootstrap(
    stock_df: pd.DataFrame,
    matched_df: pd.DataFrame,
    n_boot: int = 2000,
    seed: int = 42,
) -> pd.DataFrame:
    """One replicate = one shared per-stratum household draw applied to both frames.

    `stock_df` needs: Status, Long_term_unempl, Weight, UQNO, Stratum (any age filter
    pre-applied by the caller, matching `restrict_working_age`'s convention).
    `matched_df` needs: Status_q4, Status_q1, Weight_q4, UQNO, Stratum_q4 (consistent-linkage
    and any origin-age filter pre-applied by the caller -- this prototype does not filter).

    Returns one row per replicate: discouraged_share, employment_share, long_term_share
    (from stock_df under that replicate's multipliers), u_to_e_quarterly, e_to_non_e_quarterly
    (from matched_df under the SAME replicate's multipliers, for households whose UQNO is
    shared -- a matched_df household whose UQNO does not appear in stock_df's frame at all
    gets multiplier 0 in this protocol, since the stock frame is the anchor cross-section;
    see the .md spec for why this is expected to be rare-to-never for the destination
    quarter and what the exceptions mean)."""
    strata: dict = {}
    for h, g in stock_df.groupby("Stratum"):
        strata[h] = g["UQNO"].unique()
    # Union in any matched-only household within an already-present stratum (should not add
    # new strata, since Stratum_q4 == Stratum_q1 was verified for every matched record).
    for h, g in matched_df.groupby("Stratum_q4"):
        extra = np.setdiff1d(g["UQNO"].unique(), strata.get(h, np.array([])))
        if len(extra):
            strata[h] = np.concatenate([strata.get(h, np.array([])), extra])

    rng = np.random.default_rng(seed)

    s_status = stock_df["Status"].to_numpy()
    s_long_term = stock_df["Long_term_unempl"].to_numpy()
    s_w0 = stock_df["Weight"].to_numpy()
    s_uqno = stock_df["UQNO"].to_numpy()

    t_status_q4 = matched_df["Status_q4"].to_numpy()
    t_status_q1 = matched_df["Status_q1"].to_numpy()
    t_w0 = matched_df["Weight_q4"].to_numpy()
    t_uqno = matched_df["UQNO"].to_numpy()

    rows = []
    for _ in range(n_boot):
        mult_map = _draw_multiplier_map(strata, rng)
        s_mult = np.array([mult_map.get(u, 0) for u in s_uqno], dtype=float)
        t_mult = np.array([mult_map.get(u, 0) for u in t_uqno], dtype=float)

        s_w = s_w0 * s_mult
        elf = np.isin(s_status, [1, 2, 3]) & (s_mult > 0)
        d_share = np.average((s_status[elf] == 3).astype(float), weights=s_w[elf])
        e_share = np.average((s_status[elf] == 1).astype(float), weights=s_w[elf])
        unemp = np.isin(s_long_term, [1, 2]) & (s_mult > 0)
        lt_share = np.average((s_long_term[unemp] == 1).astype(float), weights=s_w[unemp])

        t_w = t_w0 * t_mult
        unemployed_t0 = (t_status_q4 == 2) & (t_mult > 0)
        u_to_e = np.average(
            (t_status_q1[unemployed_t0] == 1).astype(float), weights=t_w[unemployed_t0]
        )
        employed_t0 = (t_status_q4 == 1) & (t_mult > 0)
        e_to_non_e = np.average(
            (t_status_q1[employed_t0] != 1).astype(float), weights=t_w[employed_t0]
        )

        rows.append(
            dict(
                discouraged_share=d_share,
                employment_share=e_share,
                long_term_share=lt_share,
                u_to_e_quarterly=u_to_e,
                e_to_non_e_quarterly=e_to_non_e,
            )
        )
    return pd.DataFrame(rows)
