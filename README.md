# Newswire Terminal

Watches a list of stock tickers and emails you a digest whenever there's a new
SEC EDGAR filing or newswire press release (via Yahoo Finance RSS, which
aggregates PR Newswire/Business Wire/GlobeNewswire content). Runs
automatically every ~15 minutes on GitHub Actions.

## How it works

- `data/watchlist.txt` — your ticker list. One per line, `#` for comments.
  Edit this file (directly on GitHub, or locally + push) to add/remove tickers.
- Two sources are polled independently every run: SEC EDGAR and Yahoo Finance
  RSS. If one fails, the other still runs and you still get an email for
  whatever it found.
- New items are emailed to you as one batched digest per run (never one email
  per item). Each story is one sentence (the first sentence of the feed's
  summary, or a plain description of the SEC form), newest first, with a
  coloured ticker badge (blue = Yahoo news, orange = SEC filing), the source
  and Toronto time underneath, and finance keywords highlighted in yellow. A
  story listed under several tickers is shown once with all their badges.
  Click the sentence to open it. No email is sent if nothing new was found.
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

### 2. Set GitHub Actions secrets

With the GitHub CLI installed and authenticated (`gh auth login`), from this
repo's directory:

```
gh secret set GMAIL_ADDRESS
gh secret set GMAIL_APP_PASSWORD
gh secret set RECIPIENT_EMAIL
```

`RECIPIENT_EMAIL` is where digests are delivered; it can be any address and
doesn't need to match `GMAIL_ADDRESS` (the account digests are sent *from*).

Each prompts for the value (paste it and press Enter/Ctrl-D).

### 3. Turn on failure-notification emails

GitHub → Settings (your account) → Notifications → Actions: make sure
"Send notifications for failed workflows" (or equivalent) is enabled. This is
the outer safety net — if the pipeline hard-fails, GitHub emails you
independently of anything this app does itself.

### 4. Add your tickers

Edit `data/watchlist.txt` and add your tickers, one per line. Commit and push
(or edit directly on GitHub).

### 5. Trigger a first run manually

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

- `poll.yml` — the main job, every ~15 minutes. After the watchlist digest it
  also sends the whole-market sector emails (see below).
- `universe.yml` — Sundays, re-downloads the whole-market stock list.
- `bonds.yml` — hourly global bond-yield digest (see below).
- `technicals.yml` — morning and evening stock-technicals emails (see below).
- `keepalive.yml` — monthly no-op commit, so GitHub never auto-disables the
  scheduled workflows after 60 days of inactivity.
- `watchdog.yml` — every 6 hours, emails you if no successful `poll.yml` run
  has been recorded in over 3 hours (catches the case where the schedule
  itself silently stops firing).

## Whole-market sector emails (`newswire.market`)

Covers every US-listed, US-based company worth over $100M (about 3,000),
except the tickers in your watchlist, which already get the full digest.

- **Stock list:** `data/market_universe.csv`, built from Nasdaq's free stock
  screener (NYSE, Nasdaq and AMEX). Preferred shares, bonds, warrants, SPACs,
  closed-end funds and royalty trusts are left out. `universe.yml` refreshes
  it every Sunday; run `python -m newswire.market.universe` to do it by hand.
- **SEC filings:** 8-K (with its topics, e.g. "Results of Operations"), 10-Q,
  10-K, S-1 and 13D stake reports, from EDGAR's all-company "latest filings"
  feed, so it takes a few requests rather than one per company.
- **Yahoo news:** every company's feed each run, six at a time (about a
  minute). If Yahoo starts blocking, set `MARKET_YAHOO_SMALL_PER_RUN` in
  `config.py` so companies under $10B are checked in rotation instead.
- **Emails:** one per sector, companies over $10B first, then newest first.
  A sector with more than 120 stories is split into parts, e.g.
  "Technology (1/2)", so Gmail doesn't clip it.
- **Memory:** `data/market_state.json` lives in the GitHub Actions cache, not
  git. Stories are forgotten after 14 days and anything older than 3 days is
  never sent. The first time a company (or the SEC feed) is checked, nothing
  is sent; it just learns what's already out there.

## Bond yields digest (`bondwire`)

A separate, self-contained module (`src/bondwire/`) that emails an hourly
snapshot of government-bond yields for the US, Canada, Germany, UK, France,
Italy and Japan (2Y / 10Y / 30Y each), plus a euro-area AAA reference row,
2s10s curve slopes, and key benchmark spreads (BTP–Bund, OAT–Bund,
Gilt–Bund, UST–Bund, UST–JGB, UST–GoC).

- **Primary source:** CNBC's public quote endpoint — near-real-time, one
  request, no key.
- **Official backups:** US Treasury, Bank of Canada, Japan MOF, Bundesbank
  and the ECB yield curve. These fill any gap CNBC leaves, always supply the
  euro-area row, and are printed as a "last official close" reference for
  cross-checking. They refresh only at each market's daily close.
- Sends **every run** regardless of whether anything moved (`bonds.yml` cron
  is hourly at minute 17). Each email also shows the move since the previous
  email, read from `data/bond_state.json` (committed back after every run).
- Reuses the `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` secrets. Recipient is
  `mmautom_258@outlook.com`, overridable with an optional `BOND_RECIPIENT_EMAIL`
  secret.

Run it locally the same way as the poller:

```
set PYTHONPATH=src
python -m bondwire.main
```

First run manually with `gh workflow run bonds.yml`.

## Stock technicals email (`techwire`)

A separate module (`src/techwire/`) that emails technical-analysis alerts for
the US tickers in `data/watchlist.txt`. Foreign tickers (anything with a `.`)
and those in `EXCLUDE_TICKERS` are skipped. It uses daily candles from Yahoo
Finance's chart API, two years of history.

- **Evening email (~5pm Toronto):** the signals that fired at that day's close,
  plus a table of every stock (trend, RSI, MACD, % from the 50/200-day
  averages, Bollinger %B, Stochastic, % from the 52-week high). It is sent
  every weekday, even when nothing fired.
- **Morning email (~8am Toronto):** the same signals from the last close, with
  each stock's pre-market move.
- **Signals** are events, so each one alerts on the day it happens:
  - 50/200-day golden and death crosses, and price crossing either average
  - RSI moving into or out of overbought/oversold (70/30)
  - MACD crossing its signal line
  - Stochastic crosses in the overbought/oversold zones
  - new 52-week highs and lows
  - closes outside the Bollinger Bands, and Bollinger squeezes
  - support/resistance breaks (recent swing lows/highs)
  - volume spikes (2x the 20-day average)
  - bullish/bearish divergences on RSI, MACD and OBV
- All settings are in `src/techwire/config.py`.
- **Triggers:** cron-job.org calls the workflow_dispatch API with `mode`
  `morning` or `evening`. The workflow's own schedule is a late backup.
  `data/tech_state.json` records the day each email was sent, so neither one
  goes out twice.
- Reuses `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` and `RECIPIENT_EMAIL`.

Preview locally without sending:

```
set PYTHONPATH=src
python -m techwire.main --mode evening --force --preview preview.html
```
