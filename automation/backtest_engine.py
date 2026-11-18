import csv
import math
import os
from collections import defaultdict

# ==========================================
# FOOTBALL BACKTEST ENGINE - VERSION 7
# LEAGUE-BY-LEAGUE HOLDOUT AUDIT
# ==========================================

DATA_FILE = "/storage/emulated/0/ggp_data/historical_matches_2025_8_leagues.csv"
OUTPUT_FILE = "/storage/emulated/0/ggp_data/backtest_v7_league_report.csv"

MAX_GOALS = 15
MIN_TEAM_MATCHES = 5
SHRINKAGE = 5
DEVELOPMENT_PERCENT = 0.60

# Fixed weights selected in Version 6.
# These will NOT be adjusted using holdout results.
WEIGHTS = {
    "OVER15": 0.25,
    "OVER25": 0.00,
    "OVER35": 0.25,
    "BTTS": 0.00
}

MARKETS = ["OVER15", "OVER25", "OVER35", "BTTS"]

LEAGUES = [
    "Premier League",
    "La Liga",
    "Bundesliga",
    "Serie A",
    "Ligue 1",
    "Eredivisie",
    "Primeira Liga",
    "English Championship"
]


# ==========================================
# LOAD HISTORICAL MATCHES
# ==========================================

def load_matches():
    matches = []

    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            "Historical CSV file not found:\n" + DATA_FILE
        )

    with open(DATA_FILE, "r", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        required = [
            "league", "date", "home_team", "away_team",
            "home_goals", "away_goals"
        ]

        for column in required:
            if column not in (reader.fieldnames or []):
                raise ValueError(
                    "Missing required CSV column: " + column
                )

        for row in reader:
            try:
                league = row["league"].strip()
                date = row["date"].strip()[:10]
                home = row["home_team"].strip()
                away = row["away_team"].strip()
                hg = int(row["home_goals"])
                ag = int(row["away_goals"])

                if (
                    league in LEAGUES
                    and date
                    and home
                    and away
                    and hg >= 0
                    and ag >= 0
                ):
                    matches.append({
                        "league": league,
                        "date": date,
                        "home": home,
                        "away": away,
                        "hg": hg,
                        "ag": ag
                    })

            except (ValueError, TypeError, KeyError):
                continue

    matches.sort(key=lambda x: x["date"])
    return matches


# ==========================================
# HISTORY STORAGE
# ==========================================

def new_history():
    return {
        "matches": [],
        "teams": defaultdict(lambda: {
            "home_played": 0,
            "away_played": 0,
            "home_scored": 0,
            "home_conceded": 0,
            "away_scored": 0,
            "away_conceded": 0
        })
    }


def add_match(history, match):
    home = match["home"]
    away = match["away"]
    hg = match["hg"]
    ag = match["ag"]

    history["matches"].append(match)

    history["teams"][home]["home_played"] += 1
    history["teams"][home]["home_scored"] += hg
    history["teams"][home]["home_conceded"] += ag

    history["teams"][away]["away_played"] += 1
    history["teams"][away]["away_scored"] += ag
    history["teams"][away]["away_conceded"] += hg


# ==========================================
# POISSON DISTRIBUTION
# ==========================================

def poisson_probability(goals, expected):
    expected = max(0.05, min(5.0, expected))
    return (
        math.exp(-expected)
        * (expected ** goals)
        / math.factorial(goals)
    )


def poisson_predictions(home_xg, away_xg):
    home_probs = [
        poisson_probability(i, home_xg)
        for i in range(MAX_GOALS + 1)
    ]

    away_probs = [
        poisson_probability(i, away_xg)
        for i in range(MAX_GOALS + 1)
    ]

    matrix = []
    total = 0.0

    for h in range(MAX_GOALS + 1):
        row = []

        for a in range(MAX_GOALS + 1):
            probability = home_probs[h] * away_probs[a]
            row.append(probability)
            total += probability

        matrix.append(row)

    if total <= 0:
        return None

    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            matrix[h][a] /= total

    return matrix


def markets_from_matrix(matrix):
    probabilities = {
        "OVER15": 0.0,
        "OVER25": 0.0,
        "OVER35": 0.0,
        "BTTS": 0.0
    }

    result = {
        "HOME": 0.0,
        "DRAW": 0.0,
        "AWAY": 0.0
    }

    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            p = matrix[h][a]
            total_goals = h + a

            if total_goals >= 2:
                probabilities["OVER15"] += p

            if total_goals >= 3:
                probabilities["OVER25"] += p

            if total_goals >= 4:
                probabilities["OVER35"] += p

            if h > 0 and a > 0:
                probabilities["BTTS"] += p

            if h > a:
                result["HOME"] += p
            elif h == a:
                result["DRAW"] += p
            else:
                result["AWAY"] += p

    return result, probabilities


# ==========================================
# CONTEXT MODEL
# ==========================================

def context_prediction(history, home, away):
    matches = history["matches"]

    if not matches:
        return None

    home_team = history["teams"][home]
    away_team = history["teams"][away]

    if (
        home_team["home_played"] < MIN_TEAM_MATCHES
        or away_team["away_played"] < MIN_TEAM_MATCHES
    ):
        return None

    count = len(matches)

    league_home_avg = sum(
        m["hg"] for m in matches
    ) / count

    league_away_avg = sum(
        m["ag"] for m in matches
    ) / count

    if league_home_avg <= 0 or league_away_avg <= 0:
        return None

    # Shrink team rates towards league averages.
    home_scoring = (
        home_team["home_scored"]
        + league_home_avg * SHRINKAGE
    ) / (
        home_team["home_played"] + SHRINKAGE
    )

    away_defending = (
        away_team["away_conceded"]
        + league_home_avg * SHRINKAGE
    ) / (
        away_team["away_played"] + SHRINKAGE
    )

    away_scoring = (
        away_team["away_scored"]
        + league_away_avg * SHRINKAGE
    ) / (
        away_team["away_played"] + SHRINKAGE
    )

    home_defending = (
        home_team["home_conceded"]
        + league_away_avg * SHRINKAGE
    ) / (
        home_team["home_played"] + SHRINKAGE
    )

    home_xg = (
        home_scoring * away_defending / league_home_avg
    )

    away_xg = (
        away_scoring * home_defending / league_away_avg
    )

    matrix = poisson_predictions(home_xg, away_xg)

    if matrix is None:
        return None

    result_probs, market_probs = markets_from_matrix(matrix)

    return {
        "result": result_probs,
        "markets": market_probs,
        "home_xg": home_xg,
        "away_xg": away_xg
    }


# ==========================================
# SIMPLE MODEL
# ==========================================

def simple_prediction(history):
    matches = history["matches"]

    if not matches:
        return None

    total = len(matches)

    home_wins = sum(
        1 for m in matches if m["hg"] > m["ag"]
    )

    draws = sum(
        1 for m in matches if m["hg"] == m["ag"]
    )

    away_wins = sum(
        1 for m in matches if m["hg"] < m["ag"]
    )

    result_probs = {
        "HOME": (home_wins + 1) / (total + 3),
        "DRAW": (draws + 1) / (total + 3),
        "AWAY": (away_wins + 1) / (total + 3)
    }

    market_probs = {}

    for market in MARKETS:
        if market == "OVER15":
            count = sum(
                1 for m in matches
                if m["hg"] + m["ag"] >= 2
            )

        elif market == "OVER25":
            count = sum(
                1 for m in matches
                if m["hg"] + m["ag"] >= 3
            )

        elif market == "OVER35":
            count = sum(
                1 for m in matches
                if m["hg"] + m["ag"] >= 4
            )

        else:
            count = sum(
                1 for m in matches
                if m["hg"] > 0 and m["ag"] > 0
            )

        market_probs[market] = (count + 1) / (total + 2)

    return {
        "result": result_probs,
        "markets": market_probs
    }


# ==========================================
# ACTUAL MATCH OUTCOMES
# ==========================================

def actual_result(match):
    if match["hg"] > match["ag"]:
        return "HOME"

    if match["hg"] == match["ag"]:
        return "DRAW"

    return "AWAY"


def actual_market(match, market):
    goals = match["hg"] + match["ag"]

    if market == "OVER15":
        return int(goals >= 2)

    if market == "OVER25":
        return int(goals >= 3)

    if market == "OVER35":
        return int(goals >= 4)

    return int(match["hg"] > 0 and match["ag"] > 0)


# ==========================================
# METRIC STORAGE
# ==========================================

def new_result_metrics():
    return {
        "n": 0,
        "correct": 0,
        "brier": 0.0
    }


def new_market_metrics():
    return {
        "n": 0,
        "correct": 0,
        "brier": 0.0
    }


def evaluate_result(metrics, probabilities, actual):
    labels = ["HOME", "DRAW", "AWAY"]

    predicted = max(
        labels,
        key=lambda x: probabilities[x]
    )

    metrics["n"] += 1

    if predicted == actual:
        metrics["correct"] += 1

    for label in labels:
        target = 1.0 if label == actual else 0.0
        metrics["brier"] += (
            probabilities[label] - target
        ) ** 2


def evaluate_market(metrics, probability, actual):
    metrics["n"] += 1

    predicted = 1 if probability >= 0.5 else 0

    if predicted == actual:
        metrics["correct"] += 1

    metrics["brier"] += (
        probability - actual
    ) ** 2


def metric_values(metrics):
    n = metrics["n"]

    if n == 0:
        return 0, None, None

    accuracy = metrics["correct"] / n * 100
    brier = metrics["brier"] / n

    return n, accuracy, brier


# ==========================================
# REPORTING
# ==========================================

def print_metric(name, metrics):
    n, accuracy, brier = metric_values(metrics)

    if n == 0:
        print(f"{name:<22} No data")
        return

    print(
        f"{name:<22} "
        f"N={n:<5} "
        f"Accuracy={accuracy:6.2f}% "
        f"Brier={brier:.4f}"
    )


def safe_value(value):
    if value is None:
        return ""

    return round(value, 4)


# ==========================================
# MAIN BACKTEST
# ==========================================

def main():
    print("=" * 55)
    print("       FOOTBALL BACKTEST ENGINE")
    print("              VERSION 7")
    print("       LEAGUE-BY-LEAGUE AUDIT")
    print("=" * 55)

    matches = load_matches()

    if not matches:
        print("No historical matches found.")
        return

    dates = sorted(set(m["date"] for m in matches))

    split_index = int(
        len(dates) * DEVELOPMENT_PERCENT
    )

    if split_index <= 0 or split_index >= len(dates):
        print("Not enough match dates for the split.")
        return

    development_dates = set(dates[:split_index])
    holdout_dates = set(dates[split_index:])

    print("\nHistorical matches loaded:", len(matches))
    print("Calendar dates:", len(dates))
    print("Development dates:", len(development_dates))
    print("Holdout dates:", len(holdout_dates))

    print("\nHoldout period:")
    print(min(holdout_dates), "to", max(holdout_dates))

    histories = {
        league: new_history()
        for league in LEAGUES
    }

    # Metrics are separated by league.
    reports = {}

    for league in LEAGUES:
        reports[league] = {
            "matches": 0,
            "skipped": 0,
            "result_context": new_result_metrics(),
            "result_simple": new_result_metrics(),
            "markets": {}
        }

        for market in MARKETS:
            reports[league]["markets"][market] = {
                "context": new_market_metrics(),
                "simple": new_market_metrics(),
                "hybrid": new_market_metrics()
            }

    # Group all matches by calendar date.
    matches_by_date = defaultdict(list)

    for match in matches:
        matches_by_date[match["date"]].append(match)

    print("\nStarting chronological audit...")

    processed_dates = 0
    tested_total = 0
    skipped_total = 0

    for date in dates:
        todays_matches = matches_by_date[date]

        # IMPORTANT:
        # Every match on this date is predicted before
        # ANY match from this date enters the history.
        predictions_today = []

        for match in todays_matches:
            league = match["league"]
            history = histories[league]

            context = context_prediction(
                history,
                match["home"],
                match["away"]
            )

            simple = simple_prediction(history)

            if context is None or simple is None:
                if date in holdout_dates:
                    reports[league]["skipped"] += 1
                    skipped_total += 1

                continue

            predictions_today.append({
                "match": match,
                "context": context,
                "simple": simple
            })

        # Evaluate only the untouched chronological
        # holdout portion of the dataset.
        if date in holdout_dates:
            for item in predictions_today:
                match = item["match"]
                league = match["league"]
                context = item["context"]
                simple = item["simple"]

                report = reports[league]

                report["matches"] += 1
                tested_total += 1

                # Match result: CONTEXT is the selected model.
                result_actual = actual_result(match)

                evaluate_result(
                    report["result_context"],
                    context["result"],
                    result_actual
                )

                # Keep SIMPLE result as a comparison.
                evaluate_result(
                    report["result_simple"],
                    simple["result"],
                    result_actual
                )

                # Goal markets: compare all three approaches.
                for market in MARKETS:
                    actual = actual_market(match, market)

                    context_p = context["markets"][market]
                    simple_p = simple["markets"][market]

                    weight = WEIGHTS[market]

                    hybrid_p = (
                        weight * context_p
                        + (1 - weight) * simple_p
                    )

                    evaluate_market(
                        report["markets"][market]["context"],
                        context_p,
                        actual
                    )

                    evaluate_market(
                        report["markets"][market]["simple"],
                        simple_p,
                        actual
                    )

                    evaluate_market(
                        report["markets"][market]["hybrid"],
                        hybrid_p,
                        actual
                    )

        # Add today's results only after every fixture
        # on this calendar date has been processed.
        for match in todays_matches:
            add_match(
                histories[match["league"]],
                match
            )

        processed_dates += 1

        if processed_dates % 25 == 0:
            print(
                "Processed dates:",
                processed_dates,
                "/",
                len(dates)
            )

    # ======================================
    # PRINT LEAGUE-BY-LEAGUE RESULTS
    # ======================================

    print("\n")
    print("=" * 70)
    print("             VERSION 7 HOLDOUT RESULTS")
    print("=" * 70)

    print("Tested matches:", tested_total)
    print("Skipped matches:", skipped_total)

    csv_rows = []

    for league in LEAGUES:
        report = reports[league]

        print("\n" + "-" * 70)
        print(league.upper())
        print("-" * 70)

        print("Holdout matches tested:", report["matches"])
        print("Matches skipped:", report["skipped"])

        print("\nMATCH RESULT")
        print_metric(
            "CONTEXT",
            report["result_context"]
        )
        print_metric(
            "SIMPLE",
            report["result_simple"]
        )

        row = {
            "league": league,
            "holdout_matches": report["matches"],
            "skipped_matches": report["skipped"]
        }

        n, acc, brier = metric_values(
            report["result_context"]
        )

        row["result_context_accuracy"] = safe_value(acc)
        row["result_context_brier"] = safe_value(brier)

        n, acc, brier = metric_values(
            report["result_simple"]
        )

        row["result_simple_accuracy"] = safe_value(acc)
        row["result_simple_brier"] = safe_value(brier)

        print("\nGOAL MARKETS")

        for market in MARKETS:
            print("\n" + market)

            for model in ["context", "simple", "hybrid"]:
                metrics = report["markets"][market][model]

                print_metric(
                    model.upper(),
                    metrics
                )

                n, acc, brier = metric_values(metrics)

                row[f"{market}_{model}_accuracy"] = safe_value(acc)
                row[f"{market}_{model}_brier"] = safe_value(brier)

            row[f"{market}_hybrid_context_weight"] = WEIGHTS[market]

        csv_rows.append(row)

    # ======================================
    # SAVE REPORT
    # ======================================

    if csv_rows:
        columns = list(csv_rows[0].keys())

        with open(
            OUTPUT_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=columns
            )

            writer.writeheader()
            writer.writerows(csv_rows)

    print("\n" + "=" * 70)
    print("VERSION 7 AUDIT COMPLETE")
    print("=" * 70)

    print("Total holdout matches:", tested_total)
    print("Total skipped matches:", skipped_total)
    print("\nReport saved to:")
    print(OUTPUT_FILE)

    print("\nIMPORTANT:")
    print("These are historical holdout results.")
    print("They do not guarantee future betting profits.")
    print("No model weights were tuned using holdout results.")


if __name__ == "__main__":
    main()