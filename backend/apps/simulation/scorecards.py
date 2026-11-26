"""The scorecard workbench in the game (P3.5; Document 09).

Building, combining and deploying scorecards are the Head of Data Analytics's
actions, recorded and replayed (each model's random holdout comes from the world's
seed and the model's number, so a replay builds the same model). The statistics live
in the bureau layer (``apps.bureau.analytics``); this module adds what only the game
knows: the world's truth behind each model (the debrief), the Compliance finding a
restricted attribute brings, and monitoring in later months.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
from django.db.models import Max

from apps.bureau.analytics import scoredata as sd
from apps.bureau.analytics import scoremath as sm
from apps.bureau.analytics.portfolio import latest_reporting_date, reporting_bounds
from apps.world.models import Loan

from . import duties
from .feed import Feed
from .judgement import customer_borrowers
from .models import Game, ScoreModel, Severity

WINDOWS = (3, 6, 12)  # months; 12 is the default definition (D13)
DRIFT_PSI = 0.25  # population stability above this: the population has shifted
SHIFT_PSI = 0.10  # above this, a moderate shift worth watching (the usual 0.1 / 0.25 rule)
PSI_EDGES = [float(f) for _, f, _ in sorted(sm.BANDS, key=lambda b: b[1])][1:]  # band floors


class ScorecardError(Exception):
    """The workbench cannot do this; the message says why."""


def _seed(game: Game, number: int) -> int:
    return int(game.world.seed) * 10_000 + number


def observation_dates(
    game: Game, window: int, bounds: tuple[date | None, date | None] | None = None
) -> list[str]:
    """Month-ends that leave ``window`` months of outcome on file, after one month of history."""
    first, last = bounds or reporting_bounds(game.organization_id)
    if first is None or last is None:
        return []
    days = []
    t = sd.months_back(first, -1)
    while sd.months_back(t, -window) <= last:
        days.append(t.isoformat())
        t = sd.months_back(t, -1)
    return days


def options(game: Game) -> dict[str, Any]:
    bounds = reporting_bounds(game.organization_id)
    return {
        "terms": [
            {"code": sd.SHORT, "label": "Short term: up to 3 months (mostly mobile loans)"},
            {"code": sd.MID, "label": "Mid term: over 3 months, up to a year"},
            {"code": sd.LONG, "label": "Long term: over a year"},
            {"code": sd.ALL, "label": "One scorecard for every loan (to compare)"},
        ],
        "features": [
            {
                "name": n,
                "description": d,
                "recommended_for": list(t),
                "restricted": n in sd.RESTRICTED,
            }
            for n, (d, t) in sd.FEATURES.items()
        ],
        "windows": [
            {"months": w, "observation_dates": observation_dates(game, w, bounds)} for w in WINDOWS
        ],
        "default_window": 12,
    }


def _next_number(game: Game) -> int:
    return (ScoreModel.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0) + 1


def _check_dates(game: Game, observation: date, window: int) -> None:
    if window not in WINDOWS:
        raise ScorecardError(f"The outcome window must be {', '.join(map(str, WINDOWS))} months")
    if observation.isoformat() not in observation_dates(game, window):
        raise ScorecardError(
            f"{observation:%d %B %Y} does not leave {window} months of outcomes on file: "
            "choose an earlier observation date or a shorter window"
        )


def _deciles(scores: np.ndarray) -> dict[str, list[Any]]:
    """Score deciles, their edges fixed: finer than the five bands, so a shift within a band
    shows (P3.12)."""
    edges = sorted({float(e) for e in np.quantile(scores, np.linspace(0.1, 0.9, 9))})
    return {"edges": edges, "counts": _counts(scores, edges)}


def _counts(scores: np.ndarray, edges: list[float]) -> list[int]:
    counts: np.ndarray = np.bincount(
        np.searchsorted(np.array(edges), scores, side="right"), minlength=len(edges) + 1
    )
    return [int(c) for c in counts]


def _histogram(scores: np.ndarray) -> list[int]:
    counts: np.ndarray = np.bincount(
        np.searchsorted(np.array(PSI_EDGES), scores, side="right"), minlength=len(PSI_EDGES) + 1
    )
    return [int(c) for c in counts]


def build(
    game: Game, term: str, observation: date, window: int, features: list[str], tick: int
) -> ScoreModel:
    """Build a term scorecard (or one for every loan) and store it as a draft."""
    if term not in sd.BUILDABLE:
        raise ScorecardError(f"There is no term {term!r}")
    _check_dates(game, observation, window)
    number = _next_number(game)
    data = sd.dataset(game.organization_id, term, observation, window)
    try:
        result = sd.build(data, features, _seed(game, number))
    except ValueError as exc:
        raise ScorecardError(str(exc)) from exc
    scores = result.pop("scores")
    all_scores = np.array(scores["scores"])
    result["truth"] = debrief(game, term, data, all_scores, np.array(scores["holdout"]))
    result["development"] = _histogram(all_scores)
    spec = {k: result.pop(k) for k in ("binnings", "intercept", "coefficients")}
    return ScoreModel.objects.create(
        game=game, number=number, term=term, observation_date=observation, window_months=window,
        features=features, seed=_seed(game, number), spec=spec, results=result, built_tick=tick,
    )  # fmt: skip


def build_composite(game: Game, observation: date, window: int, tick: int) -> ScoreModel:
    """Combine the deployed term scorecards into one score, with weights fitted on the data."""
    _check_dates(game, observation, window)
    parts = list(
        ScoreModel.objects.filter(
            game=game, status=ScoreModel.Status.DEPLOYED, term__in=sd.TERMS
        ).order_by("term")
    )
    if not parts:
        raise ScorecardError(
            "Deploy at least one term scorecard first: the composite combines them"
        )
    number = _next_number(game)
    data = sd.dataset(game.organization_id, sd.ALL, observation, window)
    if len(data.customers) < 100 or data.bad.sum() < 10:
        raise ScorecardError("Too little data at that date for a composite")
    log_odds = {}
    for part in parts:
        p = 1.0 / (1.0 + np.exp(-_logit(part, data)))
        log_odds[part.term] = np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1))
    # Each term's log-odds counts only for customers who hold that term; presence itself
    # gets a weight too (a customer with no long-term loan is not "average" on it).
    columns = []
    for part in parts:
        present = data.present[part.term]
        columns += [np.where(present, log_odds[part.term], 0.0), present.astype(float)]
    x = np.column_stack(columns)
    holdout = sd.split(data.customers, _seed(game, number))
    intercept, coefficients = sm.fit_logistic(x[~holdout], data.bad[~holdout].astype(float))
    p_bad = sm.predict_bad(intercept, coefficients, x)
    scores = sm.score_of(p_bad)
    each = {
        part.term: sd.finite(sm.auc(data.bad[holdout], log_odds[part.term][holdout]))
        for part in parts
    }
    results = {
        "term": sd.COMPOSITE,
        "observation": observation.isoformat(),
        "components": [{"number": p.number, "term": p.term} for p in parts],
        "weights": [
            {
                "term": p.term,
                "log_odds_weight": round(float(coefficients[2 * i]), 4),
                "presence_weight": round(float(coefficients[2 * i + 1]), 4),
            }
            for i, p in enumerate(parts)
        ],
        "holdout": {
            "customers": int(holdout.sum()),
            "bads": int(data.bad[holdout].sum()),
            "auc": sd.finite(sm.auc(data.bad[holdout], p_bad[holdout])),
            "gini": sd.finite(sm.gini(data.bad[holdout], p_bad[holdout])),
            "ks": sd.finite(sm.ks(data.bad[holdout], p_bad[holdout])),
        },
        "each_term_on_everyone": each,
        "score_bands": sd._bands(scores, data.bad),
        "truth": debrief(game, sd.ALL, data, scores, holdout),
        "development": _histogram(scores),
        "fairness": {
            "restricted_used": sorted({f for p in parts for f in p.features} & sd.RESTRICTED)
        },
    }
    return ScoreModel.objects.create(
        game=game, number=number, term=sd.COMPOSITE, observation_date=observation,
        window_months=window, features=[], seed=_seed(game, number),
        spec={"components": [p.number for p in parts], "intercept": intercept,
              "coefficients": [float(c) for c in coefficients]},
        results=results, built_tick=tick,
    )  # fmt: skip


def _logit(model: ScoreModel, data: sd.Dataset) -> np.ndarray:
    columns = [
        sd.stored_binning(b).transform(data.features[b["feature"]]) for b in model.spec["binnings"]
    ]
    result: np.ndarray = model.spec["intercept"] + np.column_stack(columns) @ np.array(
        model.spec["coefficients"]
    )
    return result


def scores_for(model: ScoreModel, data: sd.Dataset) -> np.ndarray:
    """A stored model's scores for a dataset's customers (composites from their parts)."""
    if model.term != sd.COMPOSITE:
        return sm.score_of(1.0 / (1.0 + np.exp(-_logit(model, data))))
    parts = {
        p.number: p
        for p in ScoreModel.objects.filter(game=model.game, number__in=model.spec["components"])
    }
    columns = []
    for number in model.spec["components"]:
        part = parts[number]
        present = data.present[part.term]
        columns += [np.where(present, _logit(part, data), 0.0), present.astype(float)]
    p = sm.predict_bad(
        model.spec["intercept"], np.array(model.spec["coefficients"]), np.column_stack(columns)
    )
    return sm.score_of(p)


def deploy(game: Game, number: int, tick: int, at: datetime) -> ScoreModel:
    """Put a model into use; the one it replaces for the same term is retired. A model that
    uses a restricted attribute brings a Compliance finding."""
    model = ScoreModel.objects.filter(game=game, number=number).first()
    if model is None:
        raise ScorecardError(f"There is no scorecard {number}")
    if model.status == ScoreModel.Status.DEPLOYED:
        raise ScorecardError(f"Scorecard {number} is already in use")
    replaced = ScoreModel.objects.filter(
        game=game, term=model.term, status=ScoreModel.Status.DEPLOYED
    )
    _settle_findings(game, list(replaced.values_list("number", flat=True)), tick)
    replaced.update(status=ScoreModel.Status.RETIRED)
    model.status, model.deployed_tick = ScoreModel.Status.DEPLOYED, tick
    baseline = _population(game, model, None)
    if baseline is not None:  # the population it went live on, to watch for change (P3.12)
        as_of, scores = baseline
        model.results = {
            **model.results,
            "deployed": {"as_of": as_of.isoformat(), **_deciles(scores)},
        }
    model.save(update_fields=["status", "deployed_tick", "results"])
    restricted = model.results.get("fairness", {}).get("restricted_used", [])
    if restricted:
        detail = (
            f"Scorecard {number} ({model.term.lower()} term) uses {', '.join(restricted)}, an "
            "attribute that may not be used to decide credit. Retire it, or build one without it."
        )
        duties.raise_finding(
            game, "RESTRICTED_ATTRIBUTE_IN_SCORECARD", f"SCORECARD-{number}", detail,
            f"Retire scorecard {number} (Data Analytics).", tick, at,
        )  # fmt: skip
        feed = Feed(game, tick, at)
        feed.add(
            "COMPLIANCE_FINDING", Severity.WARNING, f"Compliance finding: scorecard {number} uses {restricted[0]}",
            detail, {"screen": "scorecards", "params": {"number": str(number)}},
        )  # fmt: skip
        feed.save()
    refresh_scores(game)  # reports carry the new scores at once (P3.6)
    return model


def debrief(
    game: Game, term: str, data: sd.Dataset, scores: np.ndarray, holdout: np.ndarray
) -> dict[str, Any]:
    """How the model ranks the world's true outcomes on the holdout, and how many of the
    bureau's labels its own data errors got wrong."""
    customers = data.customers[holdout].tolist()
    borrowers = customer_borrowers(game, customers)
    people = {b[1] for b in borrowers.values() if b[0] == "person"}
    defaulted: set[int] = set()
    for person, disbursed, maturity, facility in Loan.objects.filter(
        world=game.world,
        customer__person_id__in=people,
        first_default_period__gt=data.observation,
        first_default_period__lte=data.window_end,
    ).values_list("customer__person_id", "disbursement_date", "maturity_date", "facility_type"):
        if term in (sd.ALL, sd.COMPOSITE) or sd.term_of(disbursed, maturity, facility) == term:
            defaulted.add(person)
    known = [i for i, c in enumerate(customers) if c in borrowers]
    if not known:
        return {}
    true_bad = np.array(
        [
            borrowers[customers[i]][1] in defaulted and borrowers[customers[i]][0] == "person"
            for i in known
        ]
    )
    bureau_bad = data.bad[holdout][known]
    held_scores = scores[holdout][known]
    return {
        "customers": len(known),
        "true_defaults": int(true_bad.sum()),
        "auc_against_truth": sd.finite(sm.auc(true_bad, -held_scores.astype(float)))
        if 0 < true_bad.sum() < len(true_bad)
        else None,
        "auc_against_bureau_labels": sd.finite(sm.auc(bureau_bad, -held_scores.astype(float))),
        "labels": {
            "both_default": int((bureau_bad & true_bad).sum()),
            "bureau_only": int((bureau_bad & ~true_bad).sum()),
            "truth_only": int((~bureau_bad & true_bad).sum()),
            "neither": int((~bureau_bad & ~true_bad).sum()),
        },
    }


def _population(
    game: Game, model: ScoreModel, as_of: date | None
) -> tuple[date, np.ndarray] | None:
    """The model's scores for everyone on file at a reporting date (the latest by default)."""
    latest = as_of or latest_reporting_date(game.organization_id)
    if latest is None or latest <= model.observation_date:
        return None
    term = sd.ALL if model.term == sd.COMPOSITE else model.term
    data = sd.dataset(game.organization_id, term, latest, 0)
    if len(data.customers) == 0:
        return None
    return latest, scores_for(model, data)


def _shift(psi: float) -> str:
    return "major" if psi > DRIFT_PSI else "moderate" if psi > SHIFT_PSI else "stable"


def monitor(game: Game, model: ScoreModel, as_of: date | None = None) -> dict[str, Any] | None:
    """Population stability of a model's scores at a reporting date (the latest by default):
    against its development, by band, and against the population it was deployed on, by
    decile (P3.12), which shows a change since it went live, such as an economic shock."""
    found = _population(game, model, as_of)
    if found is None:
        return None
    latest, scores = found
    now = _histogram(scores)
    psi = _psi(model.results["development"], now)
    since = None
    deployed = model.results.get("deployed")
    if deployed and latest > date.fromisoformat(deployed["as_of"]):
        moved = _psi(deployed["counts"], _counts(scores, deployed["edges"]))
        since = {"from": deployed["as_of"], "psi": round(moved, 4), "shift": _shift(moved)}
    return {
        "as_of": latest.isoformat(), "customers": len(scores), "psi": round(psi, 4),
        "drift": psi > DRIFT_PSI, "shift": _shift(psi), "development": model.results["development"],
        "now": now, "since_deployment": since,
    }  # fmt: skip


def _psi(expected: list[int], actual: list[int]) -> float:
    e = np.array(expected, dtype=float) + sm.SMOOTHING
    a = np.array(actual, dtype=float) + sm.SMOOTHING
    pe, pa = e / e.sum(), a / a.sum()
    return float(np.sum((pa - pe) * np.log(pa / pe)))


def summary(model: ScoreModel) -> dict[str, Any]:
    r = model.results
    return {
        "number": model.number, "term": model.term, "status": model.status,
        "observation": model.observation_date.isoformat(), "window_months": model.window_months,
        "features": model.features, "holdout": r.get("holdout"),
        "restricted_used": r.get("fairness", {}).get("restricted_used", []),
    }  # fmt: skip


# --- The score on reports (P3.6) --------------------------------------------------------------

REASONS_SHOWN = 4
SCORED_ORDER = (sd.LONG, sd.MID, sd.SHORT)  # without a composite: the longest term held


def _points_and_reasons(model: ScoreModel, data: sd.Dataset) -> tuple[np.ndarray, list[list[str]]]:
    """Each customer's score on a term model, and the characteristics that cost them most."""
    descriptions = {name: d for name, (d, _) in sd.FEATURES.items()}
    losses = []
    for b, coef in zip(model.spec["binnings"], model.spec["coefficients"], strict=True):
        binning = sd.stored_binning(b)
        points = -coef * np.array(binning.woe) * sm.FACTOR
        losses.append(points.max() - points[binning.bin_of(data.features[b["feature"]])])
    loss = np.column_stack(losses)
    features = [b["feature"] for b in model.spec["binnings"]]
    reasons = []
    for row in loss:
        order = np.argsort(-row, kind="mergesort")[:REASONS_SHOWN]
        reasons.append([descriptions[features[j]] for j in order if row[j] > 0.5])
    return scores_for(model, data), reasons


def retire(game: Game, number: int, tick: int) -> ScoreModel:
    """Take a scorecard out of use (P3.7): its term goes unscored until another is deployed.
    Retiring a scorecard settles any finding about it."""
    model = ScoreModel.objects.filter(game=game, number=number).first()
    if model is None:
        raise ScorecardError(f"There is no scorecard {number}")
    if model.status != ScoreModel.Status.DEPLOYED:
        raise ScorecardError(f"Scorecard {number} is not in use")
    model.status = ScoreModel.Status.RETIRED
    model.save(update_fields=["status"])
    _settle_findings(game, [number], tick)
    refresh_scores(game)
    return model


def _settle_findings(game: Game, numbers: list[int], tick: int) -> None:
    for number in numbers:
        duties.resolve_findings(game, tick, reference=f"SCORECARD-{number}")


def refresh_scores(game: Game) -> int:
    """Score every individual customer on file with the deployed scorecards, at the latest
    reporting month. Returns how many customers have a score."""
    from apps.bureau.reports.models import CreditScore

    deployed = {
        m.term: m for m in ScoreModel.objects.filter(game=game, status=ScoreModel.Status.DEPLOYED)
    }
    CreditScore.objects.filter(organization_id=game.organization_id).delete()
    terms = [t for t in SCORED_ORDER if t in deployed]
    latest = latest_reporting_date(game.organization_id)
    if not terms or latest is None:
        return 0
    data = sd.dataset(game.organization_id, sd.ALL, latest, 0, scoring=True)
    per_term = {t: _points_and_reasons(deployed[t], data) for t in terms}
    composite = deployed.get(sd.COMPOSITE)
    main = scores_for(composite, data) if composite else None
    rows = []
    for i, customer in enumerate(data.customers.tolist()):
        held = [t for t in terms if data.present[t][i]]
        if not held:
            continue  # nothing open to score on: "no score" (a thin or closed file)
        term_scores = {t: int(per_term[t][0][i]) for t in held}
        if main is not None:
            score, source = int(main[i]), f"COMPOSITE-{composite.number}"  # type: ignore[union-attr]
        else:
            score, source = term_scores[held[0]], f"{held[0]}-{deployed[held[0]].number}"
        weakest = min(held, key=lambda t: term_scores[t])
        rows.append(
            CreditScore(
                organization_id=game.organization_id,
                customer_id=customer,
                as_of=latest,
                score=score,
                band=sm.band_of(score),
                reasons=per_term[weakest][1][i],
                terms=term_scores,
                model=source,
            )
        )
    CreditScore.objects.bulk_create(rows, batch_size=5000)
    return len(rows)
