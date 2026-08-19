# Newswire Terminal

Watches a list of stock tickers and emails you a digest whenever there's a new
SEC EDGAR filing or newswire press release (via Yahoo Finance RSS and
Finnhub's company-news API). Runs automatically every ~15 minutes on GitHub
Actions.

## How it works

- `data/watchlist.txt` — your ticker list. One per line, `#` for comments.
  Edit this file (directly on GitHub, or locally + push) to add/remove tickers.
- Three sources are polled independently every run: SEC EDGAR, Yahoo Finance
  RSS, and Finnhub. If one fails, the other two still run and you still get
  an email for whatever they found.
- New items are emailed to you as one batched digest per run (never one email
  per item), grouped by ticker then source. No email is sent if nothing new
  was found.
- State (which items have already been alerted on) is stored in
  `data/state.json` and committed back to the repo after every run, since
  GitHub Actions runners don't persist anything themselves.
- The **first ever run**, and the first run after adding a brand-new ticker,
  only seeds state — it won't email you a backlog of everything that already
  existed.

## One-time setup

### 1. Enable 2-Step Verification and create a Gmail App Password

1. Go to your Google Account → Security → 2-Step Verification, and turn it on
   if it isn't already.
2. Go to Security → App Passwords, create one (name it e.g. "Newswire
   Terminal"), and copy the 16-character password it gives you.

### 2. Get a free Finnhub API key

1. Sign up at https://finnhub.io/register (free tier).
2. Copy your API key from the dashboard.

### 3. Set GitHub Actions secrets

With the GitHub CLI installed and authenticated (`gh auth login`), from this
repo's directory:

```
gh secret set GMAIL_ADDRESS
gh secret set GMAIL_APP_PASSWORD
gh secret set FINNHUB_API_KEY
```

Each prompts for the value (paste it and press Enter/Ctrl-D).

### 4. Turn on failure-notification emails

GitHub → Settings (your account) → Notifications → Actions: make sure
"Send notifications for failed workflows" (or equivalent) is enabled. This is
the outer safety net — if the pipeline hard-fails, GitHub emails you
independently of anything this app does itself.

### 5. Add your tickers

Edit `data/watchlist.txt` and add your tickers, one per line. Commit and push
(or edit directly on GitHub).

### 6. Trigger a first run manually

```
gh workflow run poll.yml
gh run watch
```

The first run seeds state and sends no email — that's expected. Subsequent
runs will alert you on anything genuinely new.

## Local development

```
cd newswire_terminal
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements-dev.txt
copy .env.example .env       # fill in real values
```

Load `.env` (e.g. via `python -m dotenv run -- python -m newswire.main`, or
export the variables yourself) and run:

```
set PYTHONPATH=src
python -m newswire.main
```

## Workflows

- `poll.yml` — the main job, every ~15 minutes.
- `keepalive.yml` — monthly no-op commit, so GitHub never auto-disables the
  scheduled workflows after 60 days of inactivity.
- `watchdog.yml` — every 6 hours, emails you if no successful `poll.yml` run
  has been recorded in over 2 hours (catches the case where the schedule
  itself silently stops firing).
