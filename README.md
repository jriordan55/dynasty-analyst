# Dynasty Fantasy Football Analyst

A league-aware fantasy football analyst that syncs your **full Sleeper league**, grades your roster against **4for4 ADP**, pulls **live ESPN news & injuries**, and surfaces **manager-specific trade leverage** — not just "this player is good," but *who in your league would want them and why*.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

## Use it in 60 seconds

### Option A — Web app (easiest)

```bash
git clone https://github.com/YOUR_USERNAME/dynasty-analyst.git
cd dynasty-analyst
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
streamlit run app.py
```

Open **http://localhost:8501**, enter your Sleeper league ID + username, click **Save & Sync**.

### Option B — Terminal

```bash
python -m src.cli set-team YOUR_USERNAME
python -m src.cli report
```

## Deploy free on Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set **Main file path** to `app.py`
5. Deploy — you get a public URL like `https://your-app.streamlit.app`

No server needed. Runs in the browser.

## Deploy on GitHub Codespaces

1. Open the repo on GitHub → **Code** → **Codespaces** → **Create codespace**
2. In the terminal:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py --server.address 0.0.0.0
   ```
3. Click the forwarded port link (8501)

## Features

| Feature | Description |
|---------|-------------|
| **League Map** | Every manager's positional depth, gaps, and surplus |
| **Roster Grades** | ADP tier + age + injury + live news |
| **Sell Alerts** | RB age cliffs, declining assets |
| **Trade Targets** | Match your surplus to managers who are desperate |
| **Waivers** | Pickups tailored to your roster holes |
| **AI Context** | Export full league context for Claude/Cursor chat |

## Connect your league

Your Sleeper league ID is in the URL when you open your league:

```
https://sleeper.app/leagues/1363674260144418816
                              ^^^^^^^^^^^^^^^^^^^
```

Or use an invite link — the inviter's current-season league is resolved automatically during setup.

## CLI commands

| Command | Description |
|---------|-------------|
| `python -m src.cli setup` | Interactive setup |
| `python -m src.cli sync` | Pull latest rosters |
| `python -m src.cli overview` | League needs map |
| `python -m src.cli grades` | Grade your roster |
| `python -m src.cli sell` | Sell candidates |
| `python -m src.cli trades` | Trade matches |
| `python -m src.cli waivers` | Waiver targets |
| `python -m src.cli report` | Full report |
| `python -m src.cli ask "..."` | AI chat (needs `ANTHROPIC_API_KEY`) |

## Data sources

- [Sleeper API](https://docs.sleeper.app/) — rosters, trending adds/drops
- [4for4 ADP](https://www.4for4.com/adp) — market values (`data/adp.json`)
- [Rotowire NFL RSS](https://www.rotowire.com/rss/news.php?sport=NFL) — player news & injury updates
- [Underdog NFL blog RSS](https://underblog.underdogfantasy.com/feed) — fantasy analysis & rankings
- [ESPN](https://site.api.espn.com/) — breaking news & official injury reports

Refresh ADP: drop updated 4for4 export into `data/adp-source.md`, then run `python -m src.cli refresh-adp-cmd`.

## Project structure

```
app.py                  # Streamlit web UI
src/
  analyst.py            # Orchestrator
  analysis.py           # Grades, trades, waivers
  sleeper.py            # League sync
  adp.py                # 4for4 ADP parser
  news.py               # ESPN news/injuries
  cli.py                # Terminal commands
config/league.example.json
data/adp.json
```

## License

MIT
