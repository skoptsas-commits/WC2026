#!/usr/bin/env python3
"""
World Cup 2026 — football-data.org fetcher
===========================================
Τραβάει δεδομένα από το football-data.org REST API (αντί για FBref scraping,
που μπλοκάρεται από Cloudflare) και γράφει data.json για το dashboard.

Το API key διαβάζεται από το environment variable FOOTBALL_DATA_TOKEN
— ΔΕΝ γράφεται ποτέ μέσα στον κώδικα. Τοπικά: export FOOTBALL_DATA_TOKEN=...
Στο GitHub Actions: μπαίνει ως repository secret.

Σημείωση: το δωρεάν tier ΔΕΝ έχει xG. Οι μετρικές εδώ είναι goals/assists/
points/goal-difference — όλες πραγματικές και απευθείας από το API.
"""

import json
import os
import sys
import datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Ρυθμίσεις ──────────────────────────────────────────────────────────
BASE        = "https://api.football-data.org/v4"
COMPETITION = "WC"          # FIFA World Cup
OUT_PATH    = Path("data.json")
TOKEN       = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()


def api_get(path):
    """GET ένα endpoint του football-data.org με το auth header."""
    url = f"{BASE}{path}"
    req = Request(url, headers={"X-Auth-Token": TOKEN})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Standings → λίστα ομάδων ──────────────────────────────────────────
def get_teams():
    """
    Τα standings του World Cup επιστρέφονται ανά group (type=TOTAL).
    Τα ενώνουμε όλα σε μία λίστα ομάδων.
    """
    data = api_get(f"/competitions/{COMPETITION}/standings")
    teams = []
    for block in data.get("standings", []):
        if block.get("type") != "TOTAL":
            continue
        for row in block.get("table", []):
            t = row.get("team", {})
            mp = row.get("playedGames", 0) or 0
            w  = row.get("won", 0) or 0
            d  = row.get("draw", 0) or 0
            l  = row.get("lost", 0) or 0
            teams.append({
                "team":    t.get("shortName") or t.get("name", "?"),
                "group":   block.get("group", ""),
                "MP":      mp,
                "W":       w,
                "D":       d,
                "L":       l,
                "GF":      row.get("goalsFor", 0) or 0,
                "GA":      row.get("goalsAgainst", 0) or 0,
                "GD":      row.get("goalDifference", 0) or 0,
                "points":  row.get("points", 0) or 0,
                "win_pct": round(w / mp * 100, 1) if mp else 0.0,
            })
    return teams


# ── Scorers → λίστα παικτών ───────────────────────────────────────────
def get_players():
    """Top scorers (goals descending). Το δωρεάν tier δίνει goals + assists."""
    data = api_get(f"/competitions/{COMPETITION}/scorers?limit=30")
    players = []
    for s in data.get("scorers", []):
        p = s.get("player", {})
        team = s.get("team", {})
        players.append({
            "player":  p.get("name", "?"),
            "team":    team.get("shortName") or team.get("name", "?"),
            "nation":  (p.get("nationality") or "")[:3].upper(),
            "g":       s.get("goals", 0) or 0,
            "a":       s.get("assists", 0) or 0,
            "pen":     s.get("penalties", 0) or 0,
            "played":  s.get("playedMatches", 0) or 0,
        })
    return players


# ── Knockout matches → bracket + win probabilities ────────────────────
KO_STAGES = ["LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "THIRD_PLACE", "FINAL"]
KO_LABEL  = {"LAST_16":"Round of 16","QUARTER_FINALS":"Quarter-finals",
             "SEMI_FINALS":"Semi-finals","THIRD_PLACE":"Third place","FINAL":"Final"}

def _team_strength(teams):
    """
    Απλό, ειλικρινές rating ανά ομάδα από τη φάση ομίλων:
    points/game (0-3) + goal-difference bonus. Χρησιμοποιείται ΜΟΝΟ για
    εκτίμηση πιθανοτήτων — δεν είναι επίσημο νούμερο.
    """
    strength = {}
    for t in teams:
        mp = t["MP"] or 1
        ppg = t["points"] / mp                 # 0..3
        gd_per = t["GD"] / mp                   # goal diff per game
        strength[t["team"]] = ppg + 0.35 * gd_per
    return strength

def _win_prob(a, b, strength):
    """Λογιστική συνάρτηση πάνω στη διαφορά strength → πιθανότητα νίκης του a."""
    import math
    sa = strength.get(a, 1.0)
    sb = strength.get(b, 1.0)
    return round(1 / (1 + math.exp(-(sa - sb))) * 100)

def get_matches_raw():
    """Τραβάει ΟΛΟΥΣ τους αγώνες μία φορά — μοιράζεται σε bracket + matches list."""
    try:
        return api_get(f"/competitions/{COMPETITION}/matches")
    except Exception as e:
        print(f"ℹ️  Δεν τράβηξα matches: {e}")
        return {}


def build_matches(data):
    """Όλοι οι αγώνες (όμιλοι + νοκ-άουτ) σε ελαφρύ schema για τα νέα tabs.

    Χρησιμοποιεί shortName ώστε τα ονόματα να ταιριάζουν 1:1 με τα
    teams / players / bracket (name-based matching στο frontend)."""
    matches = []
    for m in data.get("matches", []):
        home = m.get("homeTeam", {}) or {}
        away = m.get("awayTeam", {}) or {}
        score = m.get("score", {}) or {}
        full = score.get("fullTime", {}) or {}
        half = score.get("halfTime", {}) or {}
        refs = m.get("referees") or []
        main_ref = next((r.get("name") for r in refs
                         if r.get("type") in (None, "REFEREE")), None)
        matches.append({
            "date":     m.get("utcDate"),
            "status":   m.get("status", ""),
            "matchday": m.get("matchday"),
            "stage":    m.get("stage"),
            "group":    (m.get("group") or "").replace("GROUP_", "Group "),
            "home":     home.get("shortName") or home.get("name") or "TBD",
            "away":     away.get("shortName") or away.get("name") or "TBD",
            "hg":       full.get("home"),
            "ag":       full.get("away"),
            "winner":   score.get("winner"),
            # Λεπτομέρειες αγώνα — ό,τι δίνει το free tier· null αν λείπει
            "ht_hg":    half.get("home"),
            "ht_ag":    half.get("away"),
            "venue":    m.get("venue"),
            "attendance": m.get("attendance"),
            "referee":  main_ref,
        })
    matches.sort(key=lambda x: x["date"] or "")
    return matches


def get_bracket(teams, data=None):
    """Knockout matches ανά stage, με εκτιμώμενες πιθανότητες νίκης."""
    if data is None:
        data = get_matches_raw()
    if not data:
        return []

    strength = _team_strength(teams)
    by_stage = {}
    for m in data.get("matches", []):
        stage = m.get("stage")
        if stage not in KO_STAGES:
            continue
        home = m.get("homeTeam", {}) or {}
        away = m.get("awayTeam", {}) or {}
        hn = home.get("shortName") or home.get("name") or "TBD"
        an = away.get("shortName") or away.get("name") or "TBD"
        score = m.get("score", {}) or {}
        full = score.get("fullTime", {}) or {}
        winner = score.get("winner")   # HOME_TEAM / AWAY_TEAM / DRAW / None
        entry = {
            "stage":  stage,
            "status": m.get("status", ""),      # SCHEDULED / FINISHED / ...
            "home":   hn,
            "away":   an,
            "hg":     full.get("home"),
            "ag":     full.get("away"),
            "winner": winner,
        }
        # πιθανότητες μόνο αν ξέρουμε και τις δύο ομάδες
        if hn != "TBD" and an != "TBD":
            entry["home_prob"] = _win_prob(hn, an, strength)
            entry["away_prob"] = 100 - entry["home_prob"]
        by_stage.setdefault(stage, []).append(entry)

    # επίστρεψε ταξινομημένα κατά στάδιο
    out = []
    for st in KO_STAGES:
        if st in by_stage:
            out.append({"stage": st, "label": KO_LABEL[st], "matches": by_stage[st]})
    return out
def main():
    if not TOKEN:
        print("❌ Λείπει το FOOTBALL_DATA_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    print(f"🔄 Fetching World Cup ({COMPETITION}) from football-data.org …")

    teams = get_teams()
    print(f"   ομάδες: {len(teams)}")
    players = get_players()
    print(f"   scorers: {len(players)}")
    matches_raw = get_matches_raw()
    matches = build_matches(matches_raw)
    print(f"   αγώνες: {len(matches)}")
    bracket = get_bracket(teams, matches_raw)
    print(f"   knockout stages: {len(bracket)}")

    if not teams and not players:
        print("⚠️  Δεν επέστρεψε δεδομένα — δεν γράφω τίποτα.")
        sys.exit(0)

    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "football-data.org",
        "competition": COMPETITION,
        "teams": teams,
        "players": players,
        "matches": matches,
        "bracket": bracket,
    }

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Έγραψα {OUT_PATH} — {len(teams)} ομάδες, {len(players)} παίκτες")


if __name__ == "__main__":
    try:
        main()
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        print(f"❌ HTTP {e.code}: {e.reason}  {body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"❌ Σφάλμα δικτύου: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fetch απέτυχε: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
