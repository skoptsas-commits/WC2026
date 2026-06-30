# ⚽ World Cup 2026 — Live Analytics Dashboard

A self-updating football dashboard. Real tournament data is pulled from the
[football-data.org](https://www.football-data.org) REST API, processed in
Python, and visualised in an interactive single-page dashboard — **no server
required**.

🔗 **Live demo:** _(add your GitHub Pages URL here)_

---

## How it works

```
GitHub Actions (cron every 6h)
   └─ fetch_data.py  ──►  football-data.org API  (auth via secret token)
         └─ writes data.json
               └─ commits to repo
                     └─ index.html (GitHub Pages) reads data.json + Plotly
```

The dashboard is a **static site**; the only "backend" is a scheduled GitHub
Action that refreshes `data.json`. Free to host, nothing to maintain, and the
whole data pipeline is transparent in the commit history.

## Files

| File | Purpose |
|------|---------|
| `fetch_data.py` | Calls football-data.org, writes `data.json`. Token read from env var. |
| `.github/workflows/update.yml` | Runs the fetch every 6h and commits the result. |
| `index.html` | Dashboard — loads `data.json`, renders 3 tabs with Plotly. |
| `data.json` | The data the dashboard reads. Auto-updated by the Action. |

## Metrics

All data comes directly from football-data.org (free tier):

- **Top scorers** — goals, assists, penalties, matches played
- **Standings** — points, W/D/L, goals for/against, goal difference, win %
- **Goals analysis** — attack vs defence scatter, goal-difference ranking

> Note: the free tier does not include expected-goals (xG). The dashboard
> therefore focuses on goals-based metrics, all traceable to the API.

## Running it yourself

```bash
export FOOTBALL_DATA_TOKEN=your_token_here   # get a free one at football-data.org
python3 fetch_data.py                        # writes data.json
python3 -m http.server 8000                  # open http://localhost:8000
```

## Notes

- `data.json` ships with sample data so the dashboard renders before the first
  real Action run. A **SAMPLE** badge shows until real data lands.
- Free tier is rate-limited to 10 requests/minute — plenty for a 6-hour refresh.

---

_Data: [football-data.org](https://www.football-data.org) · Built with Python & Plotly._
