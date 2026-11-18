GOALGRID V7 PERSONAL AUTOMATION - STAGE 1
========================================

This is a separate automation layer. It does NOT change the official V7 model,
its parameters, weights, or backtest_engine.py logic.

WHAT IT DOES
- Downloads 2026/27 results and fixtures for the existing eight leagues from
  Open Matchday once per day.
- Keeps historical_matches_2025_8_leagues.csv as the untouched baseline.
- Maps provider team names only through the reviewed alias table.
- Writes team_matching_audit.csv for names it cannot safely match.
- Runs the existing live_v7_prediction_engine.py and V7 engine.
- Publishes automation/data/goalgrid_predictions.json with all fixture outputs
  and a top-10-by-date list ranked by strongest 1X2 probability.
- Starts with a manual GitHub Actions run. The daily schedule will be enabled
  only after the first successful data and team-matching audit.

IMPORTANT BEFORE ACTIVATION
1. Keep this package separate from the currently working website/APK.
2. Add the contents of this automation folder to a new branch or test copy of
   your goalgrid-v7 repository. Do not overwrite the live site yet.
3. Run the workflow manually once and inspect team_matching_audit.csv and the
   generated reports. Add only verified aliases to live_v7_team_aliases.csv.
   The current workflow is manual-only; do not schedule it until this first test
   passes.
4. Confirm kickoff times and results against official schedules before relying
   on them. Open Matchday publishes a fixed UTC+1 clock convention; the script
   converts those fixture times to UTC before the app displays EAT.
5. If a download fails or source files are empty, the script stops and does not
   publish a new JSON prediction file.

PROVIDER
Open Matchday: https://github.com/oladeeayo/open-matchday
This is for personal, informational, non-commercial use only. Keep attribution
visible and review the provider's current disclaimer and data rights. Data is
refreshed daily, not live. Do not redistribute commercially.

REPOSITORY LAYOUT
Copy this automation folder into the repository root, preserving its internal
paths. GitHub Actions must be enabled and the workflow must be allowed to write
repository contents. The live PWA is not modified by this package.

NEXT STAGE
After the data workflow passes a manual run, update the website to fetch
/data/goalgrid_predictions.json, add the date picker, and display the top ten
eligible predictions for the selected date. Keep the existing manual CSV import
as a fallback during beta.
