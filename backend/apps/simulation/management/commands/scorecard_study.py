"""Measure the scorecard workbench's claims on a world (P3.5; Document 09).

python manage.py scorecard_study --world 12 --observation 2026-06-30 --window 6

Two bureaus over the same 12 months of provider files: one loaded with the usual
policies (the world's history template) and one loaded carelessly (fuzzy links made
automatically at a low score, nothing sent to review). For each, every term scorecard
and the single all-loans scorecard are built at the same date, and the composite from
the term scorecards; each is judged against the bureau's own labels and against the
world's truth. Results go to ``--out`` (JSON) and are printed. Games are deleted
afterwards unless ``--keep``.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from django.core.management.base import BaseCommand, CommandParser

from apps.bureau.analytics import scoredata as sd
from apps.bureau.analytics import scoremath as sm
from apps.simulation import scorecards
from apps.simulation.bridge import new_game, set_up_bureau, start_game
from apps.simulation.history import preload_history
from apps.simulation.lifecycle import delete_game
from apps.simulation.models import Game
from apps.world.models import World

CARELESS = {"match_auto_link": 0.6, "match_review": 0.6}
SEED = 20261123


def _careless_game(world: World, months: int) -> Game:
    game = new_game(world, bureau_name="Careless bureau (study)")
    set_up_bureau(game)
    org = game.organization
    for name, value in CARELESS.items():
        setattr(org, name, value)
    org.save(update_fields=list(CARELESS))
    preload_history(game, months)
    return game


def _logit(result: dict[str, Any], data: sd.Dataset) -> np.ndarray:
    woe = np.column_stack(
        [sd.stored_binning(b).transform(data.features[b["feature"]]) for b in result["binnings"]]
    )
    out: np.ndarray = result["intercept"] + woe @ np.array(result["coefficients"])
    return out


def study(game: Game, observation: date, window: int) -> dict[str, Any]:
    org = game.organization_id
    data = {term: sd.dataset(org, term, observation, window) for term in (*sd.TERMS, sd.ALL)}
    built = {term: sd.build(data[term], sd.recommended(term), SEED) for term in data}
    out: dict[str, Any] = {"models": {}, "term_against_single": {}}
    for term, result in built.items():
        scores = np.array(result["scores"]["scores"])
        holdout = np.array(result["scores"]["holdout"])
        truth = scorecards.debrief(game, term, data[term], scores, holdout)
        out["models"][term] = {"holdout": result["holdout"], "truth": truth}
    for term in sd.TERMS:
        d = data[term]
        h = sd.split(d.customers, SEED)
        out["term_against_single"][term] = {
            "own": sd.finite(sm.auc(d.bad[h], _logit(built[term], d)[h])),
            "single": sd.finite(sm.auc(d.bad[h], _logit(built[sd.ALL], d)[h])),
        }
    everyone = data[sd.ALL]
    columns = []
    for term in sd.TERMS:
        present = everyone.present[term]
        columns += [np.where(present, _logit(built[term], everyone), 0.0), present.astype(float)]
    x = np.column_stack(columns)
    h = sd.split(everyone.customers, SEED + 1)
    b0, b = sm.fit_logistic(x[~h], everyone.bad[~h].astype(float))
    p = sm.predict_bad(b0, b, x)
    out["composite"] = {
        "auc": sd.finite(sm.auc(everyone.bad[h], p[h])),
        "each_term_on_everyone": {
            t: sd.finite(sm.auc(everyone.bad[h], _logit(built[t], everyone)[h])) for t in sd.TERMS
        },
        "single": sd.finite(sm.auc(everyone.bad[h], _logit(built[sd.ALL], everyone)[h])),
    }
    return out


class Command(BaseCommand):
    help = "Compare scorecards built on clean and carelessly loaded data, against the truth."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--world", type=int, required=True)
        parser.add_argument("--observation", required=True)
        parser.add_argument("--window", type=int, default=6)
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--out", default="scorecard-study.json")
        parser.add_argument("--keep", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        world = World.objects.get(pk=options["world"])
        observation = date.fromisoformat(options["observation"])
        started = time.perf_counter()
        games = {"clean": start_game(world, history_months=options["months"])}
        self.stdout.write(f"clean bureau ready ({time.perf_counter() - started:.0f}s)")
        games["careless"] = _careless_game(world, options["months"])
        self.stdout.write(f"careless bureau ready ({time.perf_counter() - started:.0f}s)")
        try:
            results = {
                name: study(game, observation, options["window"]) for name, game in games.items()
            }
        finally:
            if not options["keep"]:
                for game in games.values():
                    delete_game(game)
        record = {
            "world": world.pk, "seed": world.seed, "scale": world.scale,
            "observation": observation.isoformat(), "window": options["window"],
            "careless": CARELESS, "results": results,
        }  # fmt: skip
        Path(options["out"]).write_text(json.dumps(record, indent=2), encoding="utf-8")
        for name, r in results.items():
            self.stdout.write(f"\n{name}")
            for term, m in r["models"].items():
                t = m["truth"]
                self.stdout.write(
                    f"  {term:6} holdout AUC {m['holdout']['auc']}  against truth "
                    f"{t.get('auc_against_truth')}  labels {t.get('labels')}"
                )
            self.stdout.write(f"  term vs single: {r['term_against_single']}")
            self.stdout.write(f"  composite: {r['composite']}")
