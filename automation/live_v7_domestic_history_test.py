#!/usr/bin/env python3
# ============================================================
# LIVE FOOTBALL PREDICTIONS - VERSION 7
# Uses the official, unchanged Version 7 prediction functions.
# This script is a separate live-data layer; it does not tune V7.
# ============================================================

import csv
import os
import re
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict

# Android: place all project files in /storage/emulated/0/ggp_data/
ANDROID_FOLDER = Path("/storage/emulated/0/ggp_data")
SCRIPT_FOLDER = Path(__file__).resolve().parent
DATA_FOLDER = ANDROID_FOLDER if ANDROID_FOLDER.exists() else SCRIPT_FOLDER

HISTORY_FILE = DATA_FOLDER / "live_v7_combined_history.csv"
ALIASES_FILE = DATA_FOLDER / "live_v7_team_aliases.csv"
FIXTURES_FILE = DATA_FOLDER / "upcoming_fixtures.csv"
PREDICTIONS_FILE = DATA_FOLDER / "v7_live_predictions_domestic_test.csv"
ELIGIBILITY_FILE = DATA_FOLDER / "v7_fixture_eligibility_domestic_test.csv"

sys.path.insert(0, str(DATA_FOLDER))
import backtest_engine as v7

LEADING_LABELS = {
    "1", "fc", "afc", "ac", "as", "ss", "us", "ogc", "rc",
    "rcd", "ssc", "sv", "tsg", "sc", "vfb", "vfl", "ca", "es"
}
TRAILING_LABELS = {"fc", "cf", "ac", "afc", "cfc", "ud", "sc", "sco", "cde"}


def normalize_team_name(name):
    name = str(name).strip().lower()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    name = name.replace("&", " and ")
    name = re.sub(r"[^a-z0-9]+", " ", name)
    words = name.split()

    while words and words[0] in LEADING_LABELS:
        words.pop(0)

    words = [word for word in words if not word.isdigit()]

    while words and words[-1] in TRAILING_LABELS:
        words.pop()

    return " ".join(words)


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError("Required file not found: " + str(path))
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_aliases():
    aliases = {}
    for row in read_csv(ALIASES_FILE):
        league = row["league"].strip()
        alias = normalize_team_name(row["alias"])
        canonical = row["canonical_team"].strip()
        key = (league, alias)
        if key in aliases and aliases[key] != canonical:
            raise ValueError("Conflicting team alias: " + str(key))
        aliases[key] = canonical
    return aliases


def resolve_team(league, team, aliases):
    return aliases.get((league, normalize_team_name(team)))


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    print("=" * 62)
    print("       LIVE FOOTBALL PREDICTION ENGINE - VERSION 7")
    print("       V7 BASELINE LOCKED - NO RETUNING")
    print("=" * 62)

   
    # Point the unchanged V7 loader at the separate combined live history.
    v7.DATA_FILE = str(HISTORY_FILE)

    # Extend supported competitions without changing V7 calculations.
    ADDITIONAL_LEAGUES = [
        "UEFA Champions League",
        "UEFA Europa League",
        "UEFA Conference League",
        "Belgian Pro League",
        "Süper Lig",
        "Scottish Premiership",
        "2. Bundesliga",
        "Ligue 2",
        "Ekstraklasa",
        "Chance Liga",
        "Liga I",
    ]

    v7.LEAGUES = list(v7.LEAGUES) + [
        league for league in ADDITIONAL_LEAGUES
        if league not in v7.LEAGUES
    ]

    matches = v7.load_matches()
    aliases = load_aliases()
    fixtures = read_csv(FIXTURES_FILE)

    if not matches:
        raise ValueError("No valid historical or current-season matches loaded.")

    matches_by_league = defaultdict(list)
    for match in matches:
        matches_by_league[match["league"]].append(match)
        
    # UEFA competitions are kept separate from domestic competitions.
    UEFA_LEAGUES = {
        "UEFA Champions League",
        "UEFA Europa League",
        "UEFA Conference League"
    }

    # Index verified domestic home and away records by canonical team.
    domestic_home_matches = defaultdict(list)
    domestic_away_matches = defaultdict(list)

    for match in matches:
        domestic_league = match["league"]

        if domestic_league in UEFA_LEAGUES:
            continue

        domestic_home = resolve_team(
            domestic_league, match["home"], aliases
        )
        domestic_away = resolve_team(
            domestic_league, match["away"], aliases
        )

        if domestic_home:
            domestic_home_matches[domestic_home].append(match)

        if domestic_away:
            domestic_away_matches[domestic_away].append(match)
       

    prediction_rows = []
    eligibility_rows = []
    predicted_count = 0
    skipped_count = 0

    for fixture in fixtures:
        league = fixture["league"].strip()
        fixture_date = fixture["date"].strip()[:10]
        home_name = fixture["home"].strip()
        away_name = fixture["away"].strip()

        if league not in v7.LEAGUES:
            status = "UNSUPPORTED_LEAGUE"
            home = ""
            away = ""
            history_matches = []
        else:
            home = resolve_team(league, home_name, aliases)
            away = resolve_team(league, away_name, aliases)

            if not home or not away:
                status = "UNMATCHED_TEAM_NAME"
                history_matches = []
            else:
                # Critical no-leakage rule: same-day results are excluded.
                history_matches = [
                    m for m in matches_by_league[league]
                    if m["date"] < fixture_date
                ]
                status = "READY"

        history = v7.new_history()
        for match in history_matches:
            v7.add_match(history, match)
                   # Add verified domestic home records to the home team's
        # statistics only. Do not add them to UEFA league averages.
        if league in UEFA_LEAGUES and home:
            for match in domestic_home_matches[home]:
                if match["date"] < fixture_date:
                    team = history["teams"][home]
                    team["home_played"] += 1
                    team["home_scored"] += match["hg"]
                    team["home_conceded"] += match["ag"]

        # Add verified domestic away records to the away team's
        # statistics only. Do not add them to UEFA league averages.
       if league in UEFA_LEAGUES and away:
            for match in domestic_away_matches[away]:
                if match["date"] < fixture_date:
                    team = history["teams"][away]
                    team["away_played"] += 1
                    team["away_scored"] += match["ag"]
                    team["away_conceded"] += match["hg"] 

        home_played = history["teams"][home]["home_played"] if home else 0
        away_played = history["teams"][away]["away_played"] if away else 0

        context = None
        simple = None
        if status == "READY":
            context = v7.context_prediction(history, home, away)
            simple = v7.simple_prediction(history)

        if context is None:
            if status == "READY":
                status = "INSUFFICIENT_HISTORY"
            skipped_count += 1
            prediction_rows.append({
                "league": league,
                "date": fixture["date"],
                "home": home_name,
                "away": away_name,
                "status": status,
                "predicted_1x2": "",
                "home_probability": "",
                "draw_probability": "",
                "away_probability": "",
                "strongest_1x2_probability": "",
                "over_1_5_probability": "",
                "over_2_5_probability": "",
                "over_3_5_probability": "",
                "btts_probability": "",
                "estimated_correct_score": "",
                "home_xg": "",
                "away_xg": "",
                "history_matches": len(history_matches),
                "home_home_matches": home_played,
                "away_away_matches": away_played
            })
        else:
            predicted = max(
                ["HOME", "DRAW", "AWAY"],
                key=lambda label: context["result"][label]
            )

            # Keep the exact fixed V7 hybrid weights.
            hybrid_markets = {}
            for market in v7.MARKETS:
                weight = v7.WEIGHTS[market]
                hybrid_markets[market] = (
                    weight * context["markets"][market]
                    + (1 - weight) * simple["markets"][market]
                )

            matrix = v7.poisson_predictions(
                context["home_xg"], context["away_xg"]
            )
            best_score = max(
                (matrix[h][a], h, a)
                for h in range(len(matrix))
                for a in range(len(matrix[h]))
            )

            prediction_rows.append({
                "league": league,
                "date": fixture["date"],
                "home": home_name,
                "away": away_name,
                "status": "PREDICTED",
                "predicted_1x2": predicted,
                "home_probability": round(context["result"]["HOME"], 4),
                "draw_probability": round(context["result"]["DRAW"], 4),
                "away_probability": round(context["result"]["AWAY"], 4),
                "strongest_1x2_probability": round(
                    context["result"][predicted], 4
                ),
                "over_1_5_probability": round(hybrid_markets["OVER15"], 4),
                "over_2_5_probability": round(hybrid_markets["OVER25"], 4),
                "over_3_5_probability": round(hybrid_markets["OVER35"], 4),
                "btts_probability": round(hybrid_markets["BTTS"], 4),
                "estimated_correct_score": str(best_score[1]) + "-" + str(best_score[2]),
                "home_xg": round(context["home_xg"], 3),
                "away_xg": round(context["away_xg"], 3),
                "history_matches": len(history_matches),
                "home_home_matches": home_played,
                "away_away_matches": away_played
            })
            predicted_count += 1

        eligibility_rows.append({
            "league": league,
            "date": fixture["date"],
            "home": home_name,
            "away": away_name,
            "canonical_home_team": home,
            "canonical_away_team": away,
            "home_matches_before_fixture": home_played,
            "away_matches_before_fixture": away_played,
            "status": status,
            "same_date_results_excluded": "YES"
        })

    write_csv(PREDICTIONS_FILE, prediction_rows)
    write_csv(ELIGIBILITY_FILE, eligibility_rows)

    print("\nHistorical matches loaded:", len(matches))
    print("Fixtures processed:", len(fixtures))
    print("Predictions generated:", predicted_count)
    print("Fixtures not predicted:", skipped_count)
    print("\nPredictions saved to:", PREDICTIONS_FILE)
    print("Eligibility report saved to:", ELIGIBILITY_FILE)
    print("\nCorrect scores are estimates, not certainties.")
    print("V7 parameters and weights were not modified.")
    print("=" * 62)


if __name__ == "__main__":
    main()
