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
  per item), grouped by ticker then source. No email is sent if nothing new
  was found.
- State (which items have already been alerted on) is stored in
  `data/state.json` and committed back to the repo after every run, since
  GitHub Actions runners don't persist anything themselves.
- The **first ever run**, and the first run after adding a brand-new ticker,
  only seeds state — it won't email you a backlog of everything that already
  existed.

## One-time setup

### 1. Create a Resend account and API key

Email is sent via the [Resend](https://resend.com) HTTP API, not Gmail SMTP —
GitHub-hosted runners use rotating cloud IPs, and Google's anti-abuse checks
block plain SMTP username/password logins from them almost every run
(`534 5.7.9 WebLoginRequired`), regardless of how correct the app password is.

1. Sign up at [resend.com](https://resend.com) (free tier is plenty for a
   low-volume digest) and create an API key.
2. Without a verified sending domain, Resend's sandbox sender
   (`onboarding@resend.dev`) can only deliver to the email address you signed
   up to Resend with — not to arbitrary recipients. If `RECIPIENT_EMAIL` /
   `BOND_RECIPIENT_EMAIL` need to be a different address, verify a domain
   under Resend → Domains and set `RESEND_FROM_EMAIL` to an address on it.

### 2. Set GitHub Actions secrets

With the GitHub CLI installed and authenticated (`gh auth login`), from this
repo's directory:

```
gh secret set RESEND_API_KEY
gh secret set RECIPIENT_EMAIL
```

`RECIPIENT_EMAIL` is where digests are delivered. Optionally also set
`RESEND_FROM_EMAIL` (defaults to `Newswire Terminal <onboarding@resend.dev>`)
if you've verified your own domain.

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

- `poll.yml` — the main job, every ~15 minutes.
- `bonds.yml` — hourly global bond-yield digest (see below).
- `keepalive.yml` — monthly no-op commit, so GitHub never auto-disables the
  scheduled workflows after 60 days of inactivity.
- `watchdog.yml` — every 6 hours, emails you if no successful `poll.yml` run
  has been recorded in over 2 hours (catches the case where the schedule
  itself silently stops firing).

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
- Reuses the `RESEND_API_KEY` secret. Recipient is `mmautom_258@outlook.com`,
  overridable with an optional `BOND_RECIPIENT_EMAIL` secret — note this
  requires a verified Resend domain, since it isn't the Resend account's own
  address (see setup step 1 above).

Run it locally the same way as the poller:

```
set PYTHONPATH=src
python -m bondwire.main
```

First run manually with `gh workflow run bonds.yml`.
