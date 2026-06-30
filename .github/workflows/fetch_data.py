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


# ── Main ───────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        print("❌ Λείπει το FOOTBALL_DATA_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    print(f"🔄 Fetching World Cup ({COMPETITION}) from football-data.org …")

    teams = get_teams()
    print(f"   ομάδες: {len(teams)}")
    players = get_players()
    print(f"   scorers: {len(players)}")

    if not teams and not players:
        print("⚠️  Δεν επέστρεψε δεδομένα — δεν γράφω τίποτα.")
        sys.exit(0)

    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "football-data.org",
        "competition": COMPETITION,
        "teams": teams,
        "players": players,
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
