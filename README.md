# QBot

QBot is a private cycling assistant that connects training, recovery, nutrition, ride reports and Telegram/email notifications.

The app is designed to run from `/opt/qbot/app` on the QBot server.

## Main Jobs

- `daily_report.py` sends the morning training decision, weather, recovery, fuel and event context.
- `ride_report.py` detects new activities and sends a post-ride report.
- `weekly_review.py` sends a weekly coach review.
- `telegram_reply_processor.py` and `email_reply_processor.py` process user replies.
- `sync_nutrition.py` syncs nutrition data.
- `mcp_server.py` exposes QBot MCP tools.

## Local Setup

```bash
cd /opt/qbot/app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with real credentials. Do not commit `.env`.

## Common Commands

Run smoke tests:

```bash
/opt/qbot/app/.venv/bin/python -m scripts.qbot_smoke_tests
```

Check syntax:

```bash
python3 -m py_compile qbot_coach.py daily_report.py email_template.py ride_report.py weekly_review.py scripts/qbot_smoke_tests.py
```

Preview weekly review without sending:

```bash
/opt/qbot/app/.venv/bin/python weekly_review.py --preview
```

Check repository state:

```bash
git status
git diff
```

## GitHub

The repository is pushed to:

```text
git@github.com:QbotMS/QbotQ.git
```

Secrets, token stores, logs, local state, FIT files and generated reports are ignored by `.gitignore`.

## Auto Commit

`scripts/auto_commit_push.sh` creates an automatic snapshot commit when the working tree has changes, then pushes to `origin/main`.

It is installed in the `qbot` user crontab and logs to:

```text
/opt/qbot/logs/git_auto_commit.log
```

