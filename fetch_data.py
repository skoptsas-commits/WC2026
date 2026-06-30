#!/usr/bin/env python3
"""
World Cup 2026 — FBref data fetcher
====================================
Τραβάει στατιστικά από το FBref (μέσω soccerdata), τα επεξεργάζεται και
γράφει ένα data.json που διαβάζει το dashboard (index.html).

Τρέχει είτε τοπικά είτε μέσα σε GitHub Actions. Δεν έχει scheduler/threading
— το cron του GitHub Action αναλαμβάνει το χρονοπρογραμματισμό.

Σχεδιαστική αρχή: αν το scrape αποτύχει (π.χ. Cloudflare 403 στους runners),
ΔΕΝ σβήνει το παλιό data.json — απλώς βγαίνει με μήνυμα, ώστε το dashboard
να συνεχίζει να δείχνει τα τελευταία έγκυρα δεδομένα.
"""

import json
import sys
import datetime as dt
from pathlib import Path

import pandas as pd
import soccerdata as sd

# ── Ρυθμίσεις ──────────────────────────────────────────────────────────
LEAGUE      = "INT-World Cup"
SEASON      = "2026"
MIN_MINUTES = 90
OUT_PATH    = Path("data.json")
MAX_PLAYERS = 30   # πόσους παίκτες να κρατήσει στο JSON


# ── Βοηθητικά ──────────────────────────────────────────────────────────
def flatten_cols(df):
    """MultiIndex στήλες → flat strings (π.χ. ('Performance','Gls') → 'Performance_Gls')."""
    df = df.copy()
    df.columns = [
        "_".join(str(x) for x in c if x).strip("_") if isinstance(c, tuple) else c
        for c in df.columns
    ]
    return df


def find_col(df, *cands):
    """Βρίσκει στήλη ανεξαρτήτως κεφαλαίων/κενών."""
    norm = lambda s: str(s).lower().replace(" ", "")
    for c in cands:
        for actual in df.columns:
            if norm(actual) == norm(c):
                return actual
    return None


# ── Επεξεργασία ομάδων ─────────────────────────────────────────────────
def parse_score(val):
    """Δέχεται '2–1' / '2-1' / '2—1' (οποιαδήποτε παύλα) → (2, 1) ή None."""
    if not isinstance(val, str):
        return None
    import re
    m = re.match(r"\s*(\d+)\s*[\u2013\u2014\-]\s*(\d+)\s*", val)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def compute_team_table(sched):
    df = sched.copy().reset_index()
    print(f"   schedule: {len(df)} γραμμές, στήλες: {list(df.columns)}")

    rows = []
    for _, m in df.iterrows():
        hs = m.get("home_score")
        as_ = m.get("away_score")
        # αν δεν υπάρχουν ξεχωριστές στήλες, δοκίμασε το 'score'
        if pd.isna(hs) or pd.isna(as_):
            parsed = parse_score(m.get("score"))
            if parsed is None:
                continue
            hs, as_ = parsed
        if pd.isna(hs) or pd.isna(as_):
            continue
        hs, as_ = int(hs), int(as_)
        hxg = m.get("home_xg", 0) or 0
        axg = m.get("away_xg", 0) or 0
        for team, gf, ga, xg, xga in [
            (m["home_team"], hs, as_, hxg, axg),
            (m["away_team"], as_, hs, axg, hxg),
        ]:
            res = "W" if gf > ga else ("L" if gf < ga else "D")
            rows.append({"team": team, "GF": gf, "GA": ga,
                         "xG": xg, "xGA": xga, "result": res})

    print(f"   ολοκληρωμένοι αγώνες που διαβάστηκαν: {len(rows)//2}")
    pf = pd.DataFrame(rows)
    if pf.empty:
        return pf
    agg = pf.groupby("team").agg(
        MP=("result", "count"),
        W=("result", lambda s: (s == "W").sum()),
        D=("result", lambda s: (s == "D").sum()),
        L=("result", lambda s: (s == "L").sum()),
        GF=("GF", "sum"), GA=("GA", "sum"),
        xG=("xG", "sum"), xGA=("xGA", "sum"),
    ).reset_index()
    agg["win_pct"] = (agg["W"] / agg["MP"] * 100).round(1)
    agg["xG"]  = agg["xG"].round(2)
    agg["xGA"] = agg["xGA"].round(2)
    agg["xGD"] = (agg["xG"] - agg["xGA"]).round(2)
    return agg.sort_values(["win_pct", "xGD"], ascending=False)


# ── Επεξεργασία παικτών ────────────────────────────────────────────────
def compute_player_table(fbref):
    ps = flatten_cols(fbref.read_player_season_stats(stat_type="standard")).reset_index()
    print(f"   player stats: {len(ps)} γραμμές, στήλες: {list(ps.columns)[:15]}…")

    c_min  = find_col(ps, "Playing Time_Min", "Min", "minutes")
    c_g    = find_col(ps, "Performance_Gls", "Gls", "goals")
    c_a    = find_col(ps, "Performance_Ast", "Ast", "assists")
    c_xg   = find_col(ps, "Expected_xG", "xG")
    c_xag  = find_col(ps, "Expected_xAG", "xAG", "xA")
    c_pl   = find_col(ps, "player")
    c_team = find_col(ps, "team", "squad")
    c_nat  = find_col(ps, "nation", "nationality")

    # αν λείπει βασική στήλη, σταμάτα καθαρά (το log θα δείξει τι βρέθηκε)
    missing = [n for n, c in [("Min", c_min), ("Gls", c_g), ("xG", c_xg)] if c is None]
    if missing:
        print(f"   ⚠️  Δεν βρέθηκαν στήλες {missing} στα player stats — επιστρέφω κενό.")
        return []

    for c in [c_min, c_g, c_a, c_xg, c_xag]:
        if c:
            ps[c] = pd.to_numeric(ps[c], errors="coerce").fillna(0)

    ps = ps[ps[c_min] >= MIN_MINUTES].copy()
    n90 = ps[c_min] / 90
    ps["prod"]      = ps[c_g] + ps[c_a] + ps[c_xg] + (ps[c_xag] if c_xag else 0)
    ps["prod_per90"] = (ps["prod"] / n90).round(2)
    ps["g_minus_xg"] = (ps[c_g] - ps[c_xg]).round(2)

    out = []
    for _, r in ps.sort_values("prod_per90", ascending=False).head(MAX_PLAYERS).iterrows():
        out.append({
            "player":   str(r[c_pl]),
            "team":     str(r[c_team]),
            "nation":   str(r[c_nat]).split()[-1] if c_nat and pd.notna(r[c_nat]) else "",
            "min":      int(r[c_min]),
            "g":        int(r[c_g]),
            "a":        int(r[c_a]),
            "xg":       round(float(r[c_xg]), 2),
            "prod_per90": float(r["prod_per90"]),
            "g_minus_xg": float(r["g_minus_xg"]),
        })
    return out


def compute_defenders(fbref):
    """Top αμυντικοί με βάση tackles + interceptions (FBref 'defense' stat type)."""
    try:
        ds = flatten_cols(fbref.read_player_season_stats(stat_type="defense")).reset_index()
    except Exception as e:
        print(f"ℹ️  Δεν τράβηξα defensive stats: {e}")
        return []

    c_min = find_col(ds, "Playing Time_Min", "Min", "minutes")
    c_tkl = find_col(ds, "Tackles_Tkl", "Tkl", "tackles")
    c_int = find_col(ds, "Int", "interceptions")
    c_clr = find_col(ds, "Clr", "clearances")
    c_pl  = find_col(ds, "player")
    c_team = find_col(ds, "team", "squad")
    c_nat = find_col(ds, "nation", "nationality")

    for c in [c_min, c_tkl, c_int, c_clr]:
        if c:
            ds[c] = pd.to_numeric(ds[c], errors="coerce").fillna(0)

    if c_min:
        ds = ds[ds[c_min] >= MIN_MINUTES].copy()
    ds["def_actions"] = (ds[c_tkl] if c_tkl else 0) + (ds[c_int] if c_int else 0)

    out = []
    for _, r in ds.sort_values("def_actions", ascending=False).head(12).iterrows():
        out.append({
            "player": str(r[c_pl]),
            "team":   str(r[c_team]),
            "nation": str(r[c_nat]).split()[-1] if c_nat and pd.notna(r[c_nat]) else "",
            "tkl":    int(r[c_tkl]) if c_tkl else 0,
            "int":    int(r[c_int]) if c_int else 0,
            "clr":    int(r[c_clr]) if c_clr else 0,
        })
    return out


# ── Main ───────────────────────────────────────────────────────────────
def main():
    print(f"🔄 Fetching {LEAGUE} {SEASON} from FBref …")
    # no_cache=True ώστε ο runner να παίρνει πάντα φρέσκα δεδομένα
    fbref = sd.FBref(leagues=LEAGUE, seasons=SEASON, no_cache=True)

    sched = fbref.read_schedule()
    team_table = compute_team_table(sched)
    players    = compute_player_table(fbref)
    defenders  = compute_defenders(fbref)

    if team_table.empty and not players:
        print("⚠️  Δεν βρέθηκαν ολοκληρωμένοι αγώνες — δεν γράφω τίποτα.")
        sys.exit(0)

    payload = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "league": LEAGUE,
        "season": SEASON,
        "teams": json.loads(team_table.to_json(orient="records")) if not team_table.empty else [],
        "players": players,
        "defenders": defenders,
    }

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Έγραψα {OUT_PATH} — {len(payload['teams'])} ομάδες, {len(payload['players'])} παίκτες")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Δεν σβήνουμε το παλιό data.json· βγαίνουμε «καθαρά» ώστε το
        # GitHub Action να μην κάνει commit κενό/χαλασμένο αρχείο.
        print(f"❌ Fetch απέτυχε: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
