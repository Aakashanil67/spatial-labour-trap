"""P2.3: reproducible transport-missingness classification and provisional reconstruction.

Replaces the one-off scratch scripts used during the 2026-09-13/14 Astra review
(never committed -- see EXECUTION_STATUS.md) with a single script that regenerates
data/review_v2/transport_missingness.csv and data/review_v2/transport_provisional_reconstruction.csv
directly from the source NHTS 2020 person file.

Every sentinel code is handled explicitly and per-field: the four listed-mode legs
(Q429b..Q432b) do NOT share one convention (leg 1 uses mode-NA 99 / pay-NA 99 /
cost-NA 8888 / cost-unspecified 9999; legs 2-4 use mode-NA (88,99) / pay-NA 9 /
cost-NA 888 / cost-unspecified 999), and the driver fields Q433bPay/Q434bCost use
their own convention again (cost-NA 8888 / cost-unspecified 9999, confirmed live
against meta.variable_value_labels, NOT the placeholder -998 the first scratch
version of this script used, which silently let 9999 through as a R9999 fare and
inflated the driver per-period means).

Journey-level classification (hitchhike + listed-mode population) distinguishes:
  - zero:                        every administered leg is a reported zero fare
  - fully_costed_positive:       every administered leg resolves to a known value
                                  (zero fare or a numeric cost), at least one positive
  - partially_observed_positive: at least one leg has a numeric positive cost, but at
                                  least one other administered leg is ambiguous/DNK --
                                  the journey involved real payment, but its total is
                                  not fully observed
  - ambiguous:                   no positive leg; at least one leg has an unresolvable
                                  cost (unspecified cost, or a cost/period internal
                                  inconsistency)
  - nonresponse:                 every administered leg's payment period itself is
                                  "do not know"

The disputed Q433bPay codes 5/6 (see transport_definition.md) are carried as both
Scenario A (labels as exported: 5=Per year, 6=Package trips) and Scenario B (instrument
as printed: 5=Do not pay, 6=Do not know) -- neither is picked here.

Usage:
    python -m scripts.build_transport_review_tables

Requires THESIS_DATA_ROOT set (see data/README.md). Writes:
    data/review_v2/transport_missingness.csv
    data/review_v2/transport_provisional_reconstruction.csv
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyreadstat

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "review_v2"

PERIOD_LABELS = {
    1: "per_single_trip",
    2: "per_return_trip",
    3: "per_week",
    4: "per_month",
    5: "per_year",
}

# Per-leg sentinel conventions for the four listed-mode legs, confirmed live against
# meta.variable_value_labels (see journey_audit*.py in the review scratch history).
LEG_SPECS = [
    dict(
        name="leg1",
        mode="Q429bMode1Trv",
        mode_na=(99,),
        pay="Q429b2Pay1",
        pay_zero=7,
        pay_dnk=8,
        pay_na=(99,),
        cost="Q429b3Cost1",
        cost_na=8888,
        cost_unspec=9999,
    ),
    dict(
        name="leg2",
        mode="Q430bMode2Trv",
        mode_na=(88, 99),
        pay="Q430b2Pay2",
        pay_zero=7,
        pay_dnk=None,
        pay_na=(9,),
        cost="Q430b3Cost2",
        cost_na=888,
        cost_unspec=999,
    ),
    dict(
        name="leg3",
        mode="Q431bMode3Trv",
        mode_na=(88, 99),
        pay="Q431b2Pay3",
        pay_zero=7,
        pay_dnk=None,
        pay_na=(9,),
        cost="Q431b3Cost3",
        cost_na=888,
        cost_unspec=999,
    ),
    dict(
        name="leg4",
        mode="Q432bMode4Trv",
        mode_na=(88, 99),
        pay="Q432b2Pay4",
        pay_zero=7,
        pay_dnk=None,
        pay_na=(9,),
        cost="Q432b3Cost4",
        cost_na=888,
        cost_unspec=999,
    ),
]

# Driver fields: confirmed live -- cost-NA 8888, cost-unspecified 9999 (NOT the -998
# placeholder the pre-commit scratch version used, which let the 5 genuine 9999 rows
# through as fare data).
DRIVER_COST_NA = 8888
DRIVER_COST_UNSPEC = 9999


def load_source(data_root: Path) -> pd.DataFrame:
    path = (
        data_root / "nhts2020-v1" / "nhts-2020-v1" / "nhts-2020-v1-stata" / "nhts-2020-person.dta"
    )
    df, _meta = pyreadstat.read_dta(str(path), apply_value_formats=False)
    return df


def mode_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    walk = df["Q416bWalk"] == 1
    cycle = (df["Q416bWalk"] == 2) & (df["Q417bCylce"] == 1)
    not_walk_cycle = (df["Q416bWalk"] == 2) & (df["Q417bCylce"] == 2)
    drive = not_walk_cycle & (df["Q418bDrive"] == 1)
    not_drive = not_walk_cycle & (df["Q418bDrive"] == 2)
    hitch = not_drive & (df["Q419bHitchh"] == 1)
    listed = not_drive & (df["Q419bHitchh"] == 2)
    return dict(walk=walk, cycle=cycle, drive=drive, hitchhike_and_listed_mode=hitch | listed)


def classify_leg(row: pd.Series, spec: dict) -> str:
    mode, pay, cost = row[spec["mode"]], row[spec["pay"]], row[spec["cost"]]
    if pd.isna(mode) or mode in spec["mode_na"]:
        return "not_administered"
    if pd.isna(pay) or pay in spec["pay_na"]:
        return "not_administered"
    if pay == spec["pay_zero"]:
        return "zero_fare_stated"
    if spec["pay_dnk"] is not None and pay == spec["pay_dnk"]:
        return "nonresponse_period_dnk"
    if pd.isna(cost) or cost == spec["cost_unspec"]:
        return "ambiguous_unspecified_cost"
    if cost == spec["cost_na"]:
        return "internal_inconsistency"
    if cost == 0:
        # A named payment period (1-4) with a reported cost of exactly R0. Distinct
        # from "do not pay" (an implied/skip-pattern zero) -- this is an ANSWERED
        # zero -- but the same "known, zero-cost" outcome at the journey level, so it
        # is bucketed with zero_fare_stated for classification purposes below.
        return "zero_fare_numeric"
    return "positive_numeric"


ZERO_CLASSES = ("zero_fare_stated", "zero_fare_numeric")
UNRESOLVED_CLASSES = ("ambiguous_unspecified_cost", "internal_inconsistency")


def journey_class(leg_statuses: list[str]) -> str:
    admin = [c for c in leg_statuses if c != "not_administered"]
    if not admin:
        return "no_legs_administered"
    has_positive = any(c == "positive_numeric" for c in admin)
    # A "do not know" payment period is unresolved, not a free pass: a positive leg
    # elsewhere does not make the journey fully costed if another leg's payment
    # period itself was never established -- that leg could have been paid or free.
    has_unresolved = any(c in UNRESOLVED_CLASSES for c in admin)
    has_dnk = any(c == "nonresponse_period_dnk" for c in admin)
    if has_positive and (has_unresolved or has_dnk):
        return "partially_observed_positive"
    if has_positive:
        return "fully_costed_positive"
    if all(c in ZERO_CLASSES for c in admin):
        return "zero"
    if all(c == "nonresponse_period_dnk" for c in admin):
        return "nonresponse"
    if has_unresolved or has_dnk:
        # No positive leg, but the journey mixes zero-fare and/or DNK and/or
        # unresolvable-cost legs -- the total is not confirmed zero, so it is
        # ambiguous rather than assumed free.
        return "ambiguous"
    return "unclassified"


def build_hitchhike_listed_journeys(sub: pd.DataFrame) -> pd.DataFrame:
    leg_df = pd.DataFrame(index=sub.index)
    for spec in LEG_SPECS:
        leg_df[spec["name"]] = sub.apply(lambda r, s=spec: classify_leg(r, s), axis=1)
    leg_names = [s["name"] for s in LEG_SPECS]
    leg_df["journey"] = leg_df.apply(lambda r: journey_class([r[n] for n in leg_names]), axis=1)
    return leg_df


def summarise_hitchhike_listed(sub: pd.DataFrame, leg_df: pd.DataFrame) -> dict:
    n = len(sub)
    counts = leg_df["journey"].value_counts()
    zero = int(counts.get("zero", 0))
    fully_costed = int(counts.get("fully_costed_positive", 0))
    partial = int(counts.get("partially_observed_positive", 0))
    usable_numeric = fully_costed + partial
    ambiguous = int(counts.get("ambiguous", 0))
    nonresponse = int(counts.get("nonresponse", 0))

    leg_names = [c for c in leg_df.columns if c != "journey"]
    zero_journeys = leg_df.index[leg_df["journey"] == "zero"]
    stated_only = leg_df.loc[zero_journeys, leg_names].apply(
        lambda r: all(v in ("zero_fare_stated", "not_administered") for v in r), axis=1
    )
    numeric_zero_involved = int((~stated_only).sum())

    old_leg1_zero = sub["Q429b2Pay1"] == 7
    positive_classes = ["fully_costed_positive", "partially_observed_positive"]
    reclassified = old_leg1_zero & leg_df["journey"].isin(positive_classes)

    leg1_numeric = sub["Q429b3Cost1"].notna() & ~sub["Q429b3Cost1"].isin([8888, 9999])

    detail = (
        f"Journey-level classification across all four reported travel legs (Q429b-Q432b "
        f"block), CORRECTED 2026-09-14 for numeric-zero handling and DNK-as-unresolved. "
        f"{zero} journeys are legitimate zero fares -- every administered leg is either "
        f"'do not pay' (a stated zero) or a named payment period with a reported cost of "
        f"exactly R0 (a numeric zero, answered rather than skip-implied); {numeric_zero_involved} "
        f"of the {zero} involve at least one numeric-zero leg rather than being 'do not pay' "
        f"on every leg. {fully_costed} journeys are fully costed positive (every administered "
        f"leg resolves to a known value -- zero or a positive number -- with at least one "
        f"positive). {partial} journeys are partially observed positive: at least one leg "
        f"carries a positive cost but at least one other administered leg is unresolved "
        f"(unspecified cost, an internal inconsistency, or the payment period itself recorded "
        f"as 'do not know' -- a DNK leg is NOT treated as a free pass to 'fully costed' merely "
        f"because another leg paid), so the journey is known to involve real payment but its "
        f"total is not fully observed. Of the {usable_numeric} usable-numeric journeys, "
        f"{int(leg1_numeric.sum())} have a numeric FIRST-leg cost alone (this count is not "
        f"itself zero/positive-split -- see transport_provisional_reconstruction.csv for the "
        f"positive-only per-period figures); {int(reclassified.sum())} were reported free on "
        f"leg 1 but paid on a later leg and were wrongly zeroed out by a leg-1-only reading. "
        f"{ambiguous} journeys have no positive leg but at least one unresolvable leg (mixing "
        f"zero-fare legs with an ambiguous-cost, internal-inconsistency, or DNK leg, so the "
        f"total is not confirmed zero). {nonresponse} report 'do not know' as the payment "
        f"period on every administered leg."
    )
    return dict(
        group="hitchhike_and_listed_mode",
        n=n,
        legitimate_zero=zero,
        usable_numeric_cost=usable_numeric,
        ambiguous_cost_unspecified=ambiguous,
        nonresponse_period_dnk=nonresponse,
        disputed_q433_codes_5_6=0,
        detail=detail,
        fully_costed_positive=fully_costed,
        partially_observed_positive=partial,
    )


def summarise_driver(sub: pd.DataFrame) -> dict:
    n = len(sub)
    pay, cost = sub["Q433bPay"], sub["Q434bCost"]
    resolved = cost.notna() & ~cost.isin([DRIVER_COST_NA, DRIVER_COST_UNSPEC])
    numeric_zero = resolved & (cost == 0)
    numeric_positive = resolved & (cost != 0)
    codes_1_4 = pay.isin([1, 2, 3, 4])
    unambiguous_positive = int((numeric_positive & codes_1_4).sum())
    unambiguous_zero = int((numeric_zero & codes_1_4).sum())
    unambiguous_total = int(codes_1_4.sum())
    ambiguous_cost = int((codes_1_4 & ~resolved).sum())
    disputed = int(pay.isin([5, 6]).sum())
    disputed_5 = int((pay == 5).sum())
    disputed_6 = int((pay == 6).sum())

    detail = (
        f"Unambiguous (codes 1-4, n={unambiguous_total}): {unambiguous_positive} have a "
        f"positive numeric Q434bCost, and {unambiguous_zero} have a named payment period with "
        f"Q434bCost reported as exactly R0 (a numeric zero fare, CORRECTED 2026-09-14 -- "
        f"previously folded into the usable-numeric-cost/positive count) -- sentinel codes "
        f"{DRIVER_COST_NA}/{DRIVER_COST_UNSPEC} excluded field-specifically, confirmed live "
        f"against meta.variable_value_labels; {ambiguous_cost} have a real payment period but "
        f"Q434bCost itself is Unspecified (ambiguous). "
        f"DISPUTED (n={disputed}, codes 5-6): the fielded instrument's own printed category "
        f"list for Q433bPay (page 38 of the CAPI export) shows only 6 options -- per "
        f"single/return/week/month, then code 5=DO NOT PAY, code 6=DO NOT KNOW -- and "
        f"Q434bCost's enabling condition (page 39) is explicitly gated on Q433bPay in "
        f"(1,2,3,4). The .dta's attached value-label dictionary decodes Q433bPay codes 5/6 as "
        f"'Per year'/'Package trips, buying points' instead. NOT resolved: see "
        f"transport_definition.md for both scenarios. Scenario A (labels as exported): "
        f"{disputed_5} 'per year' + {disputed_6} 'package trips' = {disputed} genuine "
        f"nonresponse. Scenario B (labels mismatched, instrument as printed governs): "
        f"{disputed_5} reclassify as legitimate zero fares (do not pay), {disputed_6} "
        f"reclassify as nonresponse (payment period itself unknown)."
    )
    return dict(
        group="drive",
        n=n,
        legitimate_zero=unambiguous_zero,
        usable_numeric_cost=unambiguous_positive,
        ambiguous_cost_unspecified=ambiguous_cost,
        nonresponse_period_dnk=0,
        disputed_q433_codes_5_6=disputed,
        detail=detail,
        fully_costed_positive=unambiguous_positive,
        partially_observed_positive=0,
    )


def build_missingness_table(df: pd.DataFrame) -> pd.DataFrame:
    masks = mode_masks(df)
    rows = []
    for group in ("walk", "cycle"):
        sub = df[masks[group]]
        n = len(sub)
        rows.append(
            dict(
                group=group,
                n=n,
                legitimate_zero=n,
                usable_numeric_cost=0,
                ambiguous_cost_unspecified=0,
                nonresponse_period_dnk=0,
                disputed_q433_codes_5_6=0,
                detail=(
                    "not applicable -- true zero fare by construction; single-leg, no "
                    "Q428bModeofTrv block administered"
                ),
                fully_costed_positive=0,
                partially_observed_positive=0,
            )
        )

    sub_drive = df[masks["drive"]]
    rows.append(summarise_driver(sub_drive))

    sub_hl = df[masks["hitchhike_and_listed_mode"]]
    leg_df = build_hitchhike_listed_journeys(sub_hl)
    rows.append(summarise_hitchhike_listed(sub_hl, leg_df))

    table = pd.DataFrame(rows)
    total = dict(
        group="total",
        n=int(table["n"].sum()),
        legitimate_zero=int(table["legitimate_zero"].sum()),
        usable_numeric_cost=int(table["usable_numeric_cost"].sum()),
        ambiguous_cost_unspecified=int(table["ambiguous_cost_unspecified"].sum()),
        nonresponse_period_dnk=int(table["nonresponse_period_dnk"].sum()),
        disputed_q433_codes_5_6=int(table["disputed_q433_codes_5_6"].sum()),
        fully_costed_positive=int(table["fully_costed_positive"].sum()),
        partially_observed_positive=int(table["partially_observed_positive"].sum()),
    )
    n_total = total["n"]
    scen_a_nonresponse = total["nonresponse_period_dnk"] + total["disputed_q433_codes_5_6"]
    total["detail"] = (
        f"Base case (Scenario A for the disputed driver codes): {total['legitimate_zero']} of "
        f"{n_total} ({total['legitimate_zero'] / n_total:.1%}) legitimate zero fares; "
        f"{total['usable_numeric_cost']} of {n_total} "
        f"({total['usable_numeric_cost'] / n_total:.1%}) have at least one leg with a usable "
        f"numeric cost, of which {total['fully_costed_positive']} are fully costed and "
        f"{total['partially_observed_positive']} are partially observed (real payment on at "
        f"least one leg, total not fully known); {total['ambiguous_cost_unspecified']} of "
        f"{n_total} ({total['ambiguous_cost_unspecified'] / n_total:.1%}) are ambiguous; "
        f"{scen_a_nonresponse} of {n_total} ({scen_a_nonresponse / n_total:.1%}) are confirmed "
        f"nonresponse under Scenario A. Under Scenario B for the disputed driver codes, some "
        f"of the 80 disputed driver rows move from nonresponse to legitimate zero fare "
        f"(Q433bPay==5 rows) or stay nonresponse for a different reason (Q433bPay==6, payment "
        f"period unknown). See transport_definition.md for the exact split and both "
        f"scenarios' totals. The payment-period CONVERSION to a common basis, and the choice "
        f"between Scenario A and B, remain open. No corrected transport_budget_share value is "
        f"reported."
    )
    table = pd.concat([table, pd.DataFrame([total])], ignore_index=True)
    return table


def leg1_note(code: int) -> str:
    if code == 1:
        return (
            "No conversion applied. Requires no adjustment ONLY once the excursion is "
            "defined as one-direction -- if the excursion is instead defined as a return "
            "journey, this per-single-trip figure understates it by roughly half absent a "
            "stated (not yet made) doubling assumption. The earlier claim that this figure "
            "needs no adjustment 'under any excursion definition' was wrong and is withdrawn."
        )
    if code == 2:
        return (
            "No conversion applied. Halving to approximate a one-direction cost assumes a "
            "symmetric fare and is NOT applied here -- that is an excursion-definition "
            "choice, not yet made."
        )
    return (
        "No conversion applied. Converting to a common basis requires a stated "
        "trip-frequency assumption -- not yet made. Small n."
    )


def build_provisional_reconstruction(df: pd.DataFrame) -> pd.DataFrame:
    masks = mode_masks(df)
    sub_hl = df[masks["hitchhike_and_listed_mode"]]

    rows = []
    pay1, cost1 = sub_hl["Q429b2Pay1"], sub_hl["Q429b3Cost1"]
    # Positive cost only: numeric zero (cost==0 with a named period) is a legitimate
    # zero fare, not a positive figure to average into these per-period tables --
    # it is counted in transport_missingness.csv's legitimate_zero instead.
    numeric1 = cost1.notna() & ~cost1.isin([8888, 9999, 0])
    for code, label in PERIOD_LABELS.items():
        m = (pay1 == code) & numeric1
        vals = cost1[m]
        rows.append(
            dict(
                population="hitchhike_and_listed_mode_leg1",
                payment_period=label,
                n=int(m.sum()),
                mean_cost_rand=round(vals.mean(), 2) if m.sum() else None,
                median_cost_rand=vals.median() if m.sum() else None,
                min_rand=vals.min() if m.sum() else None,
                max_rand=vals.max() if m.sum() else None,
                note=leg1_note(code),
            )
        )

    # Later-leg paid despite free first leg (positive cost only, same numeric-zero
    # exclusion as above)
    old_zero = pay1 == 7
    later_paid = []
    for spec in LEG_SPECS[1:]:
        c = sub_hl[spec["cost"]]
        m = old_zero & c.notna() & ~c.isin([spec["cost_na"], spec["cost_unspec"], 0])
        later_paid.extend(c[m].tolist())
    if later_paid:
        s = pd.Series(later_paid)
        rows.append(
            dict(
                population="hitchhike_and_listed_mode_later_leg_paid_despite_free_first_leg",
                payment_period="mixed",
                n=len(s),
                mean_cost_rand=None,
                median_cost_rand=None,
                min_rand=s.min(),
                max_rand=s.max(),
                note=(
                    f"{len(s)} paid-leg observations among people whose FIRST leg was reported "
                    f"free (do not pay) but who paid on a later leg of the same journey. Wrongly "
                    f"zeroed out by a leg-1-only reading; reclassified as fully_costed_positive "
                    f"or partially_observed_positive under the journey-level rebuild. Not summed "
                    f"into a single journey total here -- that requires the same "
                    f"excursion-definition and frequency-conversion decisions as the leg-1 "
                    f"figures above."
                ),
            )
        )

    # Driver side, Scenario A/B disclosed, corrected sentinel AND numeric-zero handling.
    # Positive-only and zero-inclusive means are reported as SEPARATE, distinctly
    # labelled populations (CORRECTED 2026-09-14) -- they answer different questions
    # (typical PAID cost vs. typical cost across everyone who reported a period) and
    # must not be presented as a single unlabelled "driver mean".
    payd = df.loc[masks["drive"], "Q433bPay"]
    costd = df.loc[masks["drive"], "Q434bCost"]
    resolved_d = costd.notna() & ~costd.isin([DRIVER_COST_NA, DRIVER_COST_UNSPEC])
    positive_d = resolved_d & (costd != 0)
    driver_periods = {1: "per_single_trip", 2: "per_return_trip", 3: "per_week", 4: "per_month"}
    for code, label in driver_periods.items():
        for population, mask, extra_note in (
            (
                "drive_unambiguous_codes_1_4_positive_only",
                positive_d,
                "Positive cost only -- numeric zero (cost==0) excluded, CORRECTED "
                "2026-09-14, and counted as a legitimate zero fare in "
                "transport_missingness.csv instead. Answers 'what does a driver who "
                "pays something typically pay'.",
            ),
            (
                "drive_unambiguous_codes_1_4_incl_numeric_zero",
                resolved_d,
                "Includes numeric-zero (cost==0) observations alongside positive costs "
                "-- labelled SEPARATELY from the positive-only rows above, "
                "CORRECTED 2026-09-14 (previously the two were not distinguished at "
                "all). Answers 'what does the average driver reporting this period "
                "pay, including those who paid nothing'.",
            ),
        ):
            m = (payd == code) & mask
            vals = costd[m]
            n = int(m.sum())
            note = (
                "Codes 1-4 only (unambiguous under both scenarios; see "
                "transport_definition.md for the Q433bPay code 5/6 ambiguity, which "
                "is NOT included here). Cost sentinels 8888 (not applicable) and 9999 "
                "(unspecified) excluded field-specifically for Q434bCost, confirmed "
                f"live against meta.variable_value_labels. {extra_note}"
            )
            if n <= 3:
                note += f" n={n}, not usable as a reliable point estimate."
            rows.append(
                dict(
                    population=population,
                    payment_period=label,
                    n=n,
                    mean_cost_rand=round(vals.mean(), 2) if n else None,
                    median_cost_rand=vals.median() if n else None,
                    min_rand=vals.min() if n else None,
                    max_rand=vals.max() if n else None,
                    note=note,
                )
            )

    return pd.DataFrame(rows)


def main() -> None:
    data_root = Path(os.environ["THESIS_DATA_ROOT"])
    df = load_source(data_root)

    missingness = build_missingness_table(df)
    missingness_out = missingness[
        [
            "group",
            "n",
            "legitimate_zero",
            "usable_numeric_cost",
            "ambiguous_cost_unspecified",
            "nonresponse_period_dnk",
            "disputed_q433_codes_5_6",
            "detail",
        ]
    ]
    missingness_out.to_csv(OUT_DIR / "transport_missingness.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_missingness.csv'} ({len(missingness_out)} rows)")

    recon = build_provisional_reconstruction(df)
    recon.to_csv(OUT_DIR / "transport_provisional_reconstruction.csv", index=False)
    print(f"Wrote {OUT_DIR / 'transport_provisional_reconstruction.csv'} ({len(recon)} rows)")

    print()
    summary_cols = [
        "group",
        "n",
        "legitimate_zero",
        "fully_costed_positive",
        "partially_observed_positive",
        "ambiguous_cost_unspecified",
        "nonresponse_period_dnk",
        "disputed_q433_codes_5_6",
    ]
    print(missingness[summary_cols].to_string(index=False))


if __name__ == "__main__":
    main()
