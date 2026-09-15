"""Standalone ledger verification for the CORRECTED, proportional Design A resource-financing
specification (search_capital_ledger_and_resource_design_2026-09-15.md, second pass, per
`DESIGN_A_REVIEW.md`'s "One bounded next deliverable" item 3).

Not imported by, and does not import, any production code (`src/`, `scripts/`). Reads nothing
from and writes nothing to any config, canonical target, or simulation output. Every check below
is an INDEPENDENT INVARIANT derived from the corrected specification's own algebra (affordability
sign, monotonicity, an accounting identity, a proportionality bound) -- not an expected value
copied from the review's own `verification.json`, except where explicitly reproducing that
document's own worked example as a cross-check (labelled as such below).

Usage: python data/review_v2/verify_design_a_ledger_2026-09-15.py
Writes: search_capital_design_verification_2026-09-15.json (beside this script)
"""

from __future__ import annotations

import json
from pathlib import Path

# Approved/baseline structural parameters (unchanged; from configs/baseline.yaml).
R = 0.035  # reentry_threshold
G = 0.008  # household_inflow

# The three target-compatible fare candidates (approved_specification_2026-09-15.md's own
# corrected midpoints, via validation_manifest_2026-09-15.md's F6.3 label fix).
TARGET_FARES = {
    "double_b": 0.005665,
    "primary_b": 0.007405,
    "b_zero": 0.009145,
}

# Actual per-agent minimum fares at the retained lower search_cost_per_trip bound (a=0.001,
# primary transport_cost_rate), as reported and independently reproduced by DESIGN_A_REVIEW.md
# from the existing 500-agent development configurations -- reused here as the concrete "worst
# case" (smallest fare any real agent in this project's own configs actually faces) for the
# global-domain check, not invented.
ACTUAL_MIN_FARES_AT_A_0001 = {
    "seed_1": 0.001524986,
    "seed_2": 0.001432336,
    "seed_3": 0.001276179,
}


def upper_bound(c: float, r: float = R, g: float = G) -> float:
    """B = max(r, c) + g -- the re-entry capital bound, UNCHANGED by this design (hard-D
    dynamics are not touched)."""
    return max(r, c) + g


def required_phi(c: float, r: float = R, g: float = G, months: int = 13) -> float:
    """The NECESSARY (not sufficient) proportionality threshold: h=phi*c must exceed this for
    there to exist ANY starting balance x < B that can sustain `months` consecutive one-trip
    months. Re-derived from `x >= c*(months - (months-1)*phi)` at x's supremum B:
    phi > (months - B/c) / (months - 1)."""
    b = upper_bound(c, r, g)
    return (months - b / c) / (months - 1)


def ledger_path(
    initial: float,
    fare: float,
    h_fn,
    months: int = 13,
    trips_per_month: int = 1,
) -> list[dict]:
    """One agent's month-by-month search_capital path under TRIP-ACTIVITY eligibility: pay for
    this month's trips first (step 6's existing payment order, unchanged), THEN -- within the
    SAME step-6 event, still strictly before matching runs -- credit h if trips_per_month >= 1.
    A month this step's own credit could never retroactively finance this SAME step's own trip
    payment (the payment is subtracted before the credit is added), so there is no circular
    affordability credit, checked structurally by this function's own order of operations, not
    merely asserted in prose."""
    balance = initial
    rows: list[dict] = []
    for month in range(1, months + 1):
        before = balance
        cost = trips_per_month * fare
        if before < cost:
            rows.append(dict(month=month, before=before, affordable=False))
            return rows
        after_payment = before - cost
        credit = h_fn(fare) if trips_per_month >= 1 else 0.0
        after = after_payment + credit
        rows.append(
            dict(
                month=month,
                before=before,
                cost=cost,
                credit=credit,
                affordable=True,
                after=after,
            )
        )
        balance = after
    return rows


results: dict = {}

# ---------------------------------------------------------------------------------------------
# 1. Reproduce the review's own failing example independently, from the corrected formula's own
#    definition of the ORIGINAL (flat, wrong) transfer -- not copied as a literal number.
# ---------------------------------------------------------------------------------------------
c_primary = TARGET_FARES["primary_b"]
original_flat_h = c_primary - upper_bound(c_primary) / 13  # the prior design doc's own formula
bad_path = ledger_path(0.04, c_primary, lambda fare: original_flat_h)
assert bad_path[-1]["month"] == 11 and not bad_path[-1]["affordable"], (
    "expected the original (flat, timing-uncorrected) transfer to fail at month 11"
)
results["1_reproduced_original_failure"] = dict(original_flat_h=original_flat_h, path=bad_path)

# ---------------------------------------------------------------------------------------------
# 2. Corrected FLAT-h feasible example, cross-checked against the review's own demonstration
#    (h=0.0047 at the primary fare from a re-entry balance of 0.04) -- reproduced independently
#    from the ledger_path() function above, not asserted from the review's JSON directly.
# ---------------------------------------------------------------------------------------------
corrected_flat_h = 0.0047
good_path_flat = ledger_path(0.04, c_primary, lambda fare: corrected_flat_h)
assert len(good_path_flat) == 13 and all(r["affordable"] for r in good_path_flat)
results["2_corrected_flat_h_cross_check"] = dict(h=corrected_flat_h, path=good_path_flat)

# ---------------------------------------------------------------------------------------------
# 3. The corrected PROPORTIONAL design: h_i = phi * c_i, single-trip-per-month path, checked at
#    all three target fares simultaneously with ONE phi.
# ---------------------------------------------------------------------------------------------
required_phis = {name: required_phi(c) for name, c in TARGET_FARES.items()}
PHI = 0.75  # a candidate value, chosen to exceed every target fare's own requirement
assert all(PHI > req for req in required_phis.values()), (
    f"PHI={PHI} must exceed every target fare's required_phi: {required_phis}"
)
results["3_required_phi_per_target_fare"] = required_phis
results["3_chosen_phi"] = PHI

proportional_paths = {}
for name, c in TARGET_FARES.items():
    path = ledger_path(0.04, c, lambda fare: PHI * fare)
    assert len(path) == 13 and all(r["affordable"] for r in path), (
        f"{name} (c={c}) should be feasible for 13 one-trip months at PHI={PHI}"
    )
    proportional_paths[name] = path
results["3_proportional_design_paths_at_x0_0_04"] = proportional_paths

# ---------------------------------------------------------------------------------------------
# 4. Multi-trip invariant: net capital change on an n-trip active month is c*(PHI - n), which is
#    STRICTLY NEGATIVE for every n >= 1 whenever PHI < 1 -- checked for n in 1..3 (this project's
#    max_trips_per_step) at every target fare, not asserted only for n=1.
# ---------------------------------------------------------------------------------------------
multi_trip_check = {}
for n in (1, 2, 3):
    for name, c in TARGET_FARES.items():
        net = PHI * c - n * c
        assert net < 0, f"multi-trip invariant violated for n={n}, fare={name}"
        multi_trip_check[f"{name}_n{n}"] = net
results["4_multi_trip_net_change_c_times_phi_minus_n"] = multi_trip_check

# ---------------------------------------------------------------------------------------------
# 5. Actual-agent-fare domain check: the proportional design's scarcity constraint (h_i < c_i)
#    holds AUTOMATICALLY at the smallest fares any real agent in this project's own development
#    configurations actually faces -- dissolving the prior flat-h design's global-domain
#    conflict (DESIGN_A_REVIEW.md Section 2), verified against the review's own reported minima.
# ---------------------------------------------------------------------------------------------
domain_check = {}
for seed, c_min in ACTUAL_MIN_FARES_AT_A_0001.items():
    h_i = PHI * c_min
    assert h_i < c_min, f"h_i must be strictly below c_min for {seed}"
    domain_check[seed] = dict(c_min=c_min, h_i=h_i, h_less_than_c=h_i < c_min)
results["5_actual_fare_domain_check_a_0_001"] = domain_check

# ---------------------------------------------------------------------------------------------
# 6. Joint-domain feasibility: ONE phi (0.75) simultaneously satisfies the necessary envelope at
#    all three target fares (already asserted in step 3) AND the global scarcity constraint at
#    the smallest actual per-agent fare (already asserted in step 5) -- recorded together as the
#    joint-domain result.
# ---------------------------------------------------------------------------------------------
results["6_joint_domain_feasible"] = dict(
    phi=PHI,
    satisfies_all_target_fare_envelopes=True,
    satisfies_global_scarcity_at_actual_min_fares=True,
)

# ---------------------------------------------------------------------------------------------
# 7a. Transport-subsidy accounting identity: gross fare = out-of-pocket + subsidy payment, for
#     every subsidy rate tau in [0, 1]; h is proportional to OUT-OF-POCKET cost (not the gross
#     fare), so it scales to exactly zero at tau=1 (a fully subsidised trip needs no household
#     top-up), and net capital change on an active month is never positive at any tau.
# ---------------------------------------------------------------------------------------------
policy_identity = {}
for tau in (0.0, 0.25, 0.5, 1.0):
    c = TARGET_FARES["primary_b"]
    oop = c * (1 - tau)
    subsidy_payment = tau * c
    assert abs((oop + subsidy_payment) - c) < 1e-12, "gross fare identity must hold exactly"
    h_i = PHI * oop
    net_change_active_month = h_i - oop
    assert net_change_active_month <= 1e-12, "net change must never be positive at any tau"
    policy_identity[str(tau)] = dict(
        gross_fare=c,
        out_of_pocket=oop,
        subsidy_payment=subsidy_payment,
        h=h_i,
        net_change_active_month=net_change_active_month,
    )
results["7a_transport_subsidy_ledger_identity"] = policy_identity

# ---------------------------------------------------------------------------------------------
# 7b. Same rule, different realised total: a common per-trip h formula produces DIFFERENT total
#     private-transfer spend across policy arms purely because the number of eligible
#     (trip-taking) agent-months differs -- a toy, clearly-labelled illustrative example, not a
#     claim about real simulated arm totals (which this batch does not compute).
# ---------------------------------------------------------------------------------------------
h_flat_at_primary_fare = PHI * c_primary
toy_eligible_u_months = dict(control=1000, transport_subsidy_arm=1400, wage_subsidy_arm=1250)
arm_totals = {arm: h_flat_at_primary_fare * n for arm, n in toy_eligible_u_months.items()}
assert len(set(arm_totals.values())) == len(arm_totals), (
    "identical per-trip rule should still produce different arm totals given different "
    "eligible-agent-month counts"
)
results["7b_illustrative_policy_arm_total_h_payment"] = dict(
    per_trip_h=h_flat_at_primary_fare,
    note="toy eligible-U-month counts, NOT a simulated result",
    eligible_u_months=toy_eligible_u_months,
    totals=arm_totals,
)

out_path = Path(__file__).with_name("search_capital_design_verification_2026-09-15.json")
out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"Wrote {out_path}")
print(json.dumps(results, indent=2))
