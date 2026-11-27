from urllib.error import HTTPError
#!/usr/bin/env python3
"""GoalGrid V7 scheduled data refresh. Does not alter V7 model logic or weights."""
import csv, json, re, sys, subprocess, unicodedata
from pathlib import Path
from datetime import datetime, timezone, date
from urllib.request import urlopen, Request
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
BASE = "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data"
SEASON = "2627"

LEAGUES = {
    # Existing eight competitions
    "Premier League": ("ENG_1_premier-league", "Premier League"),
    "La Liga": ("ESP_1_la-liga", "La Liga"),
    "Bundesliga": ("GER_1_bundesliga", "Bundesliga"),
    "Serie A": ("ITA_1_serie-a", "Serie A"),
    "Ligue 1": ("FRA_1_ligue-1", "Ligue 1"),
    "Eredivisie": ("NED_1_eredivisie", "Eredivisie"),
    "Primeira Liga": ("POR_1_primeira-liga", "Primeira Liga"),
    "English Championship": ("ENG_2_championship", "EFL Championship"),

    # UEFA competitions
    "UEFA Champions League": (
        "UEFA_1_champions-league", "UEFA Champions League"
    ),
    "UEFA Europa League": (
        "UEFA_1_europa-league", "UEFA Europa League"
    ),
    "UEFA Conference League": (
        "UEFA_1_conference-league", "UEFA Conference League"
    ),

    # Stage A domestic expansion
    "Belgian Pro League": (
        "BEL_1_pro-league", "Belgian Pro League"
    ),
    "Süper Lig": (
        "TUR_1_super-lig", "Süper Lig"
    ),
    "Scottish Premiership": (
        "SCO_1_premiership", "Scottish Premiership"
    ),
    "2. Bundesliga": (
        "GER_2_2-bundesliga", "2. Bundesliga"
    ),
    "Ligue 2": (
        "FRA_2_ligue-2", "Ligue 2"
    ),
    "Ekstraklasa": (
        "POL_1_ekstraklasa", "Ekstraklasa"
    ),
    "Chance Liga": (
        "CZE_1_chance-liga", "Chance Liga"
    ),
    "Liga I": (
        "ROU_1_liga-1", "Liga I"
    ),
}



def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = s.split()
    leading = {"1", "fc", "afc", "ac", "as", "ss", "us", "ogc", "rc", "rcd", "ssc", "sv", "tsg", "sc", "vfb", "vfl", "ca", "es"}
    trailing = {"fc", "cf", "ac", "afc", "cfc", "ud", "sc", "sco", "cde"}
    while words and words[0] in leading:
        words.pop(0)
    words = [w for w in words if not w.isdigit()]
    while words and words[-1] in trailing:
        words.pop()
    return " ".join(words)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    if not rows:
        if fields:
            with open(path, "w", encoding="utf-8", newline="") as f:
                w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)


def fetch_csv(url):
    req=Request(url, headers={"User-Agent":"GoalGridV7-personal-noncommercial/1.0"})
    with urlopen(req, timeout=45) as r:
        return list(csv.DictReader(line.decode("utf-8-sig") for line in r))


UEFA_HISTORY_BASE = "https://raw.githubusercontent.com/openfootball/champions-league/master"

UEFA_HISTORY_FILES = {
    "2020-21": {
        "UEFA Champions League": "cl.txt",
        "UEFA Europa League": "el.txt",
    },
    "2021-22": {
        "UEFA Champions League": "cl.txt",
        "UEFA Europa League": "el.txt",
        "UEFA Conference League": "conf.txt",
    },
    "2022-23": {
        "UEFA Champions League": "cl.txt",
        "UEFA Europa League": "el.txt",
        "UEFA Conference League": "conf.txt",
    },
    "2023-24": {
        "UEFA Champions League": "cl.txt",
        "UEFA Europa League": "el.txt",
        "UEFA Conference League": "conf.txt",
    },
    "2024-25": {
        "UEFA Champions League": "cl.txt",
        "UEFA Europa League": "el.txt",
        "UEFA Conference League": "conf.txt",
    },
    "2025-26": {
        "UEFA Champions League": "cl.txt",
    },
}


def fetch_text(url):
    req = Request(url, headers={
        "User-Agent": "GoalGridV7-personal-noncommercial/1.0"
    })
    try:
        with urlopen(req, timeout=45) as response:
            return response.read().decode("utf-8-sig")
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def parse_openfootball_results(content):
    rows = []
    current_date = None
    current_year = None

    date_pattern = re.compile(
        r"^\s{2,}(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
        r"([A-Z][a-z]{2})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$"
    )

    match_pattern = re.compile(
        r"^\s*(?:\d{1,2}:\d{2}\s+)?"
        r"(.+?)\s+v\s+(.+?)\s+"
        r"(\d+)-(\d+)"
        r"(?:\s+\(\d+-\d+\))?"
        r"(?:\s+\[([^\]]+)\])?\s*$"
    )

    for line in content.splitlines():
        date_match = date_pattern.match(line)

        if date_match:
            month, day, year = date_match.groups()
            month_number = datetime.strptime(month, "%b").month

            if year:
                current_year = int(year)
            elif current_year is None:
                continue
            elif current_date and month_number < current_date.month:
                current_year += 1

            current_date = datetime.strptime(
                f"{month} {day} {current_year}", "%b %d %Y"
            ).date()
            continue

        if current_date is None:
            continue

        match = match_pattern.match(line)
        if not match:
            continue

        home, away, home_goals, away_goals, note = match.groups()

        # Do not treat awarded matches as normally played results.
        if note and "awarded" in note.lower():
            continue

        # Remove the three-letter country code, e.g. (ENG).
        home = re.sub(r"\s+\([A-Z]{3}\)$", "", home).strip()
        away = re.sub(r"\s+\([A-Z]{3}\)$", "", away).strip()

        rows.append({
            "date": current_date.isoformat(),
            "home": home,
            "away": away,
            "home_goals": home_goals,
            "away_goals": away_goals,
        })

    return rows

def main():
    now=datetime.now(timezone.utc)
    aliases={}
    for row in read_csv(ROOT/"live_v7_team_aliases.csv"):
        k=(row["league"].strip(), norm(row["alias"]))
        value=row["canonical_team"].strip()
        if k in aliases and aliases[k] != value:
            raise RuntimeError(f"Conflicting aliases: {k}")
        aliases[k]=value

    def resolve(league, name):
        return aliases.get((league, norm(name)))

    # Keep the original 2025 historical baseline immutable; build a separate live copy.
    history=[]
    for r in read_csv(ROOT/"historical_matches_2025_8_leagues.csv"):
        history.append({"league":r["league"],"source_season":r.get("season", "2025/26"),"date":r["date"][:10],
                        "home_team":r["home_team"],"away_team":r["away_team"],
                        "home_goals":r["home_goals"],"away_goals":r["away_goals"]})

    source_results=0; unmatched_results=[]; fixture_rows=[]; source_fixture_count=0
    for league,(folder, source_name) in LEAGUES.items():
        url=f"{BASE}/{folder}/results_{SEASON}.csv"
        results=fetch_csv(url)
        source_results += len(results)
        for r in results:
            if r.get("ft_home","")=="" or r.get("ft_away","")=="":
                continue
            h=resolve(league,r.get("home")); a=resolve(league,r.get("away"))
            if not h or not a:
                unmatched_results.append({"league":league,"date":r.get("date",""),"home":r.get("home",""),"away":r.get("away",""),"issue":"UNMATCHED_RESULT_TEAM"})
                continue
            history.append({"league":league,"source_season":"2026/27","date":r["date"][:10],"home_team":h,"away_team":a,
                            "home_goals":r["ft_home"],"away_goals":r["ft_away"]})
        fixtures=fetch_csv(f"{BASE}/{folder}/fixtures_{SEASON}.csv")
        for r in fixtures:
            if not r.get("date") or not r.get("time") or not r.get("home") or not r.get("away"):
                continue
            # Source kickoff clock is published in fixed UTC+1 (CET) notation; convert to UTC.
            try:
                from datetime import timedelta
                # Provider's fixed CET-1 convention is UTC+1; convert clock time to UTC.
                dt=(datetime.strptime(r["date"]+" "+r["time"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)-timedelta(hours=1))
                iso=dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                raise RuntimeError(f"Bad fixture date/time: {r}")
            if dt.date() < now.date():
                continue
            fixture_rows.append({"league":league,"date":iso,"home":r["home"].strip(),"away":r["away"].strip()})
            source_fixture_count += 1

    # Deduplicate results by competition/date/canonical home/away; keep first identical result.
    unique={}
    for r in history:
        key=(r["league"],r["date"],r["home_team"],r["away_team"])
        if key in unique:
            old=unique[key]
            if (old["home_goals"],old["away_goals"]) != (r["home_goals"],r["away_goals"]):
                raise RuntimeError(f"Conflicting duplicate result: {key}")
        else: unique[key]=r
    history=list(unique.values())
    history.sort(key=lambda x:(x["date"],x["league"],x["home_team"]))
    fixture_keys=set(); deduped=[]
    for r in fixture_rows:
        key=(r["league"],r["date"],r["home"],r["away"])
        if key not in fixture_keys: fixture_keys.add(key); deduped.append(r)
    fixture_rows=deduped
    if not history or not fixture_rows:
        raise RuntimeError("Source returned empty history or fixture set; refusing to publish.")

    # Audit all new names before predictions. Unknown names remain visible to the V7 runner
    # as unmatched fixtures and are not silently mapped to another club.
    for f in fixture_rows:
        for side in ("home","away"):
            if not resolve(f["league"],f[side]):
                unmatched_results.append({"league":f["league"],"date":f["date"],"home":f[side],"away":"","issue":"UNMATCHED_FIXTURE_TEAM"})

    write_csv(ROOT/"live_v7_combined_history.csv",history)
    write_csv(ROOT/"upcoming_fixtures.csv",fixture_rows)
    write_csv(ROOT/"team_matching_audit.csv",unmatched_results,["league","date","home","away","issue"])

    # Run the existing live V7 wrapper. The V7 baseline module is copied unchanged.
    subprocess.run([sys.executable,str(ROOT/"live_v7_prediction_engine.py")],cwd=ROOT,check=True)
    predictions=read_csv(ROOT/"v7_live_predictions.csv")
    eligibility=read_csv(ROOT/"v7_fixture_eligibility_report.csv")
    eligible=[r for r in predictions if r.get("status")=="PREDICTED"]
    by_date=defaultdict(list)
    for r in eligible: by_date[r["date"][:10]].append(r)
    top10={}
    for d,rows in by_date.items():
        rows.sort(key=lambda r:float(r.get("strongest_1x2_probability") or 0),reverse=True)
        top10[d]=rows[:10]

    payload={"product":"GoalGrid","engine":"V7","baseline_locked":True,"updated_at_utc":now.isoformat(timespec="seconds"),
             "data_provider":"Open Matchday","provider_attribution":"Data: Open Matchday (oladeeayo/open-matchday)",
             "fixture_count":len(fixture_rows),"prediction_count":len(eligible),"unmatched_team_count":len(unmatched_results),
             "fixtures":predictions,"top10_by_date":top10,"eligibility":eligibility,
             "data_quality":{"source_result_rows":source_results,"history_rows_after_deduplication":len(history),
                             "source_fixture_rows":source_fixture_count,"unmatched_team_audit":"team_matching_audit.csv"}}
    out=ROOT/"data"/"goalgrid_predictions.json"; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    (ROOT/"data"/"last_successful_update.txt").write_text(now.isoformat(timespec="seconds")+"\n",encoding="utf-8")
    print(f"AUTOMATION SUCCESS: {len(history)} history rows; {len(fixture_rows)} fixtures; {len(eligible)} predictions; {len(unmatched_results)} team audit items")

if __name__=="__main__":
    main()
