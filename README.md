# ⚽ World Cup 2026 — Live Analytics Dashboard

A self-updating football analytics dashboard. Real match data is scraped from
[FBref](https://fbref.com/en/comps/1/World-Cup-Stats), processed in Python, and
visualised in an interactive single-page dashboard — with **no server required**.

🔗 **Live demo:** _(add your GitHub Pages URL here once enabled)_

---

## How it works

```
┌─────────────────────┐   cron every 6h   ┌──────────────────┐
│  GitHub Actions      │ ────────────────▶ │  fetch_data.py    │
│  (.github/workflows) │                   │  soccerdata→FBref │
└─────────────────────┘                   └────────┬─────────┘
                                                    │ writes
                                                    ▼
                                            ┌──────────────┐
                                            │  data.json    │
                                            └──────┬───────┘
                                                   │ committed to repo
                                                   ▼
                                     ┌──────────────────────────┐
                                     │  index.html (GitHub Pages)│
                                     │  fetch('data.json') + Plotly │
                                     └──────────────────────────┘
```

The dashboard is a **static site** — the only "backend" is a scheduled GitHub
Action that refreshes `data.json`. This is a deliberate design choice: it costs
nothing to host, never goes down, and the data pipeline is fully transparent in
the commit history.

## Files

| File | Purpose |
|------|---------|
| `fetch_data.py` | Scrapes FBref via `soccerdata`, computes team & player metrics, writes `data.json`. |
| `.github/workflows/update.yml` | Runs the fetch every 6 hours and commits the result. |
| `index.html` | The dashboard. Loads `data.json` and renders 5 tabs with Plotly. |
| `data.json` | The data the dashboard reads. Auto-updated by the Action. |

## Metrics

All metrics are derived **only from FBref data** (FBref has no transfer values,
so there is deliberately no "market value" metric — every number is traceable):

- **Production / 90′** — (Goals + Assists + xG + xAG) per 90 minutes
- **G − xG** — finishing quality (clinical vs wasteful)
- **Team xG / xGA / xGD** — expected goals for and against
- **Win/Draw/Loss %** and points
- **Defensive actions** — tackles, interceptions, clearances

## Running it yourself

```bash
pip install soccerdata pandas
python fetch_data.py        # writes a fresh data.json
python -m http.server 8000  # then open http://localhost:8000
```

## Notes & limitations

- FBref updates stats **after** matches finish (it has no real-time API), and
  rate-limits to ~1 request / 3s. `soccerdata` handles caching and throttling.
- FBref uses Cloudflare bot protection. Scraping from GitHub Actions runners can
  occasionally hit a 403; the workflow is built to **keep the last good
  `data.json`** rather than overwrite it with an error.
- `data.json` ships with sample data so the dashboard renders before the first
  real Action run. The header shows a **SAMPLE** badge until real data lands.

---

_Data: [FBref.com](https://fbref.com) · Built with soccerdata, pandas & Plotly._
