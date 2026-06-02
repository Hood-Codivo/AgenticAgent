# Telegram and Deployment Guide

## 1. Create Telegram Bot

1. Open Telegram and message `@BotFather`.
2. Send `/newbot`.
3. Choose a bot name and username.
4. Copy the bot token.
5. Send any message to your new bot so Telegram creates the chat.

Get your Telegram user ID:

```bash
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates"
```

Look for:

```json
"from": { "id": 123456789 }
```

That number is your `TELEGRAM_USER_ID`.

## 2. Configure Hermes Env

Edit:

```bash
nano ~/.hermes/.env
```

Set:

```bash
export TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN"
export TELEGRAM_ALLOWED_USERS="YOUR_TELEGRAM_USER_ID"
export TELEGRAM_ALERT_CHAT_IDS="YOUR_TELEGRAM_USER_ID"
export HERMES_DATA_PROVIDER="yfinance"
export HERMES_WATCHLIST="EURUSD,GBPUSD,AAPL,BTCUSD"
export HERMES_INTERVAL="1h"
export HERMES_USE_PPO="true"
export HERMES_MODEL_PATH="/home/godwin/Downloads/AI_agent/model_eurusd_best.zip"
export HERMES_MIN_CONFIDENCE="0.50"
export HERMES_REQUIRE_TECH_CONFIRM="false"
export HERMES_ALERT_MONITOR="true"
export HERMES_ALERT_POLL_SECONDS="900"
export HERMES_ALERT_QUALITY_MIN="90"
export HERMES_ALERT_REPEAT_SECONDS="21600"
```

If your Groq key is invalid, comment it out for now:

```bash
# export GROQ_API_KEY="..."
```

Save with `Ctrl+O`, `Enter`, `Ctrl+X`.

## 3. Configure Hermes Telegram Gateway

Copy config:

```bash
cp /home/godwin/Downloads/AI_agent/hermes_config.example.yaml ~/.hermes/config.yaml
```

Edit:

```bash
nano ~/.hermes/config.yaml
```

Change:

```yaml
gateway:
  telegram:
    enabled: true
    token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users:
      - 123456789
```

Also replace every `YOUR_TELEGRAM_USER_ID` under cron delivery with your real numeric ID.

## 4. Test Locally

```bash
cd /home/godwin/Downloads/AI_agent
source ~/.hermes/.env
venv/bin/python -c "from hermes_trading_skill_optimized import skill_handler; import json; print(json.dumps(skill_handler('signals', verbose=False), indent=2))"
```

You can run the standalone Telegram bot included in this repo without starting the Hermes gateway:

```bash
cd /home/godwin/Downloads/AI_agent
source ~/.hermes/.env
venv/bin/python telegram_bot.py
```

Message your Telegram bot:

```text
/signal
/signals
/stats
/learning
/win
/loss
```

You can also test command formatting without Telegram:

```bash
venv/bin/python telegram_bot.py --once "/signal EURUSD"
```

If you prefer Hermes' own gateway, start Hermes:

```bash
hermes
```

In another terminal, start the gateway if Hermes requires it separately:

```bash
hermes gateway start
```

Then message your Telegram bot:

```text
/trading_signal
/trading_signals_watchlist
/trading_learning_summary
```

## 5. Deploy on a VPS

Recommended minimum:

- Ubuntu 22.04 or 24.04
- 2 CPU
- 4 GB RAM
- 20 GB disk

On the VPS:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git curl
```

Copy or clone this project to:

```bash
/home/godwin/Downloads/AI_agent
```

Install Hermes:

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

Install Python dependencies:

```bash
cd /home/godwin/Downloads/AI_agent
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Set up env/config:

```bash
mkdir -p ~/.hermes
cp hermes.env.example ~/.hermes/.env
cp hermes_config.example.yaml ~/.hermes/config.yaml
nano ~/.hermes/.env
nano ~/.hermes/config.yaml
chmod 600 ~/.hermes/.env
```

Start the standalone Telegram bot:

```bash
venv/bin/python telegram_bot.py
```

## 6. Deploy on Render Background Worker

Render must use a Python version compatible with the pinned ML stack. This repo
includes `runtime.txt` with:

```text
python-3.12.8
```

Without that file, Render may choose a newer default Python version. The pinned
`torch==2.6.0` dependency does not publish wheels for Python 3.14, which causes
the build failure:

```text
ERROR: No matching distribution found for torch==2.6.0
```

Use these Render settings for a manually created Background Worker:

```text
Build command: pip install -r requirements.txt
Start command: python telegram_bot.py
```

Set secrets in Render Environment, not in files committed to GitHub:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USERS
TELEGRAM_ALERT_CHAT_IDS
GROQ_API_KEY
OPENROUTER_API_KEY
```

Set the non-secret worker config in Render Environment too:

```text
HERMES_DATA_PROVIDER=yfinance
HERMES_SYMBOL=EURUSD
HERMES_WATCHLIST=EURUSD,GBPUSD,AAPL,BTCUSD
HERMES_INTERVAL=1h
HERMES_ALERT_MONITOR=true
HERMES_ALERT_POLL_SECONDS=900
HERMES_ALERT_QUALITY_MIN=90
HERMES_ALERT_REPEAT_SECONDS=21600
```

## 7. Keep It Running With systemd

Create service:

```bash
sudo nano /etc/systemd/system/hermes-trading.service
```

Paste, replacing `YOUR_USER`:

```ini
[Unit]
Description=Hermes Trading Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/Downloads/AI_agent
EnvironmentFile=/home/YOUR_USER/.hermes/.env
ExecStart=/home/YOUR_USER/Downloads/AI_agent/venv/bin/python /home/YOUR_USER/Downloads/AI_agent/telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-trading
sudo systemctl start hermes-trading
sudo systemctl status hermes-trading
```

View logs:

```bash
journalctl -u hermes-trading -f
```

## Safety

This deployment should send signals and alerts only. Do not connect real execution until the model has been paper-tested and the feedback loop has enough history.
