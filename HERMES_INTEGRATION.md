# Hermes Agent Integration Guide

Your forex trading system is now **Hermes Agent-compatible**! This guide explains how to use Hermes as the orchestrator for all trading operations.

## Overview

Instead of running the trading bot standalone, Hermes Agent becomes your **trading AI's brain**:

- 🧠 **Orchestration**: Hermes calls your trading functions as needed
- 📅 **Scheduling**: Automated daily signals, weekly backtests, monthly retraining
- 💬 **Multi-Platform**: Get alerts on Telegram, Discord, Slack, or CLI
- 🧠 **Learning**: Hermes remembers trade history, learns from performance
- ⚙️ **Configuration**: All settings in one place, no code changes needed

## Quick Start

### Step 1: Install Hermes Agent

```bash
# Official installer (handles all setup)
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Reload shell
source ~/.bashrc  # or ~/.zshrc
```

After install, Hermes home is at `~/.hermes/`.

### Step 2: Configure Hermes

```bash
# Run interactive setup
hermes setup

# When prompted:
# - Model provider: Choose OpenRouter (supports 200+ models) or Groq
# - Telegram/Discord: Enable if you want platform alerts
# - Working directory: Use /home/godwin/Downloads/AI_agent
```

### Step 3: Copy Trading Skill

The skill file `hermes_trading_skill.py` is already created in your project root.

### Step 4: Set Up API Keys

Store credentials in `~/.hermes/.env` (never hardcode):

```bash
# Edit ~/.hermes/.env
export OPENROUTER_API_KEY="your-key-here"
export GROQ_API_KEY="your-key-here"
export TELEGRAM_BOT_TOKEN="your-bot-token"  # If using Telegram
```

### Step 5: Configure Hermes for Trading

```bash
# Copy the example config
cp /home/godwin/Downloads/AI_agent/hermes_config.example.yaml ~/.hermes/config.yaml

# Edit to customize:
# 1. Set your preferred model provider
# 2. Add your Telegram user ID or Discord server ID
# 3. Update the trading skill path (should be /home/godwin/Downloads/AI_agent/hermes_trading_skill.py)
# 4. Configure cron schedules to your timezone
```

### Step 6: Test the Integration

```bash
# Start Hermes CLI
hermes

# Test trading commands:
/trading_signal      # Get current signal
/trading_stats       # Get stats
/backtest_report     # Run backtest
/retrain_model       # Trigger retraining

# Or from command line:
hermes skill trading "Get the current trading signal"
```

## How It Works

```
┌─────────────────┐
│  Hermes Agent   │  ← Main orchestrator (Telegram/Discord/CLI)
└────────┬────────┘
         │
         ├─→ [Credential Pool] ← LLM API keys, trading secrets
         │
         ├─→ [Trading Skill] ← Your trading system
         │   ├─→ get_trading_signal()    ← Multi-agent decision
         │   ├─→ run_backtest()          ← Test performance
         │   ├─→ retrain_model()         ← Update PPO model
         │   └─→ get_trading_stats()     ← Performance tracking
         │
         ├─→ [Memory] ← Persistent trade history & analysis
         │
         ├─→ [Cron Scheduler] ← Automated tasks
         │   ├─→ Daily signals at 9 AM
         │   ├─→ Weekly backtest Friday 6 PM
         │   └─→ Monthly retraining 1st of month 2 AM
         │
         └─→ [Gateway] ← Multi-platform delivery
             ├─→ Telegram alerts
             ├─→ Discord messages
             ├─→ Slack notifications
             └─→ CLI output
```

## Available Commands

### Interactive CLI

```bash
hermes
# Then use slash commands:
/trading_signal         # Get next trading signal
/trading_stats          # Get performance metrics
/backtest_report        # Run full backtest
/retrain_model          # Trigger model update
/model                  # Change LLM model
/personalities          # View trading persona
/memory                 # View trade memory
/new                    # Start fresh conversation
/compress               # Compress context
```

### Telegram/Discord

Once configured, your bot will:

- Send daily trading signals at 9 AM
- Post weekly backtest summaries Friday evening
- Notify of monthly retraining completion
- Respond to `/signal`, `/stats`, `/backtest` commands

Example Telegram interaction:

```
You: /signal
Bot: 🔔 Trading Signal - EURUSD
     Action: BUY
     Confidence: 45%
     Entry: 1.1245
     SL: 1.1190 (-55 pips)
     TP: 1.1350 (+105 pips)
     Risk/Reward: 1:1.9
```

### Programmatic Access

```python
from hermes_trading_skill import skill_handler

# Get signal
signal = skill_handler("signal")
print(signal)

# Reward or penalize a signal later
skill_handler("feedback", signal_id=signal["signal_id"], outcome="win", reward=1.0)
skill_handler("feedback", signal_id=signal["signal_id"], outcome="loss", reward=-1.0)

# Review what Hermes has learned from feedback
learning = skill_handler("learning")
print(learning)

# Run backtest
backtest = skill_handler("backtest")
print(backtest)

# Get stats
stats = skill_handler("stats")
print(stats)
```

## Configuration Details

### Cron Schedules

Schedule format is standard crontab:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
│ │ │ │ │
│ │ │ │ │
* * * * *
```

Examples:

- `0 9 * * MON-FRI` → 9 AM on weekdays
- `0 18 * * FRI` → 6 PM on Fridays
- `0 2 1 * *` → 2 AM on 1st of each month
- `*/15 * * * *` → Every 15 minutes

### Model Providers

Supported providers in config:

- **OpenRouter** (200+ models) - Recommended
- **Groq** (fast inference)
- **OpenAI** (GPT-4, GPT-3.5)
- **Anthropic** (Claude)
- **Local** (Ollama, LM Studio)

Switch models anytime:

```bash
hermes model set openrouter/nous-hermes-2-mixtral-8x7b-dpo
```

### Skill Function Parameters

The `hermes_trading_skill.py` skill_handler accepts:

```python
skill_handler(action, **kwargs)

# action options:
#   "signal"  - Get trading signal (no kwargs)
#   "backtest" - Run backtest (optional: model_path)
#   "retrain" - Retrain model (timesteps=100000, save_checkpoints=True)
#   "stats"   - Get statistics (no kwargs)
```

## Live Market Data

By default, the skill reads the bundled historical CSV. Start by copying the env template:

```bash
mkdir -p ~/.hermes
cp /home/godwin/Downloads/AI_agent/hermes.env.example ~/.hermes/.env
nano ~/.hermes/.env
chmod 600 ~/.hermes/.env
```

To use free live/recent candles, set one of these providers in `~/.hermes/.env`:

```bash
# Option A: yfinance, no key, broad coverage
export HERMES_DATA_PROVIDER="yfinance"
export HERMES_SYMBOL="EURUSD"  # examples: GBPUSD, BTCUSD, AAPL, TSLA, ^GSPC
export HERMES_WATCHLIST="EURUSD,GBPUSD,AAPL,BTCUSD"
export HERMES_INTERVAL="1h"
export HERMES_USE_PPO="true"
export HERMES_MODEL_PATH="/home/godwin/Downloads/AI_agent/model_eurusd_best.zip"
export HERMES_MIN_CONFIDENCE="0.50"
export HERMES_REQUIRE_TECH_CONFIRM="false"

# Option B: Deriv public market data, no auth for ticks/candles
export HERMES_DATA_PROVIDER="deriv"
export HERMES_SYMBOL="EURUSD"  # maps to frxEURUSD
export HERMES_INTERVAL="1h"

# Option C: OANDA FX candles
export HERMES_DATA_PROVIDER="oanda"
export HERMES_SYMBOL="EURUSD"
export HERMES_INTERVAL="1h"
export OANDA_API_KEY="your-oanda-token"
export OANDA_ENV="practice"  # use "live" only after paper testing

# Option D: Twelve Data market data
export HERMES_DATA_PROVIDER="twelvedata"
export HERMES_SYMBOL="EURUSD"
export HERMES_INTERVAL="1h"
export TWELVE_DATA_API_KEY="your-twelve-data-key"
```

Then make sure those env vars are listed under `terminal.env_passthrough` in `~/.hermes/config.yaml`, restart Hermes, and run:

```bash
/trading_signal
```

If `HERMES_DATA_PROVIDER` is unset or set to `csv`, the skill falls back to the local historical CSV.

You can also override the default symbol programmatically:

```python
from hermes_trading_skill import skill_handler

print(skill_handler("signal", data_provider="yfinance", symbol="AAPL", interval="1h"))
print(skill_handler("signal", data_provider="deriv", symbol="GBPUSD", interval="1h"))
print(skill_handler("signals", data_provider="yfinance", symbols=["EURUSD", "AAPL", "BTCUSD"]))
```

When `HERMES_USE_PPO=true`, live signal flow is:

```text
live candles -> indicators -> 30-bar PPO observation -> model.predict() -> BUY/SELL/HOLD -> reward/penalty memory
```

The bundled model was trained on EURUSD-like 1-hour forex data. Signals for stocks and crypto are experimental until you train models for those assets.

## Troubleshooting

### "Cannot find trading skill"

- Verify path in `~/.hermes/config.yaml` matches actual location
- Should be: `/home/godwin/Downloads/AI_agent/hermes_trading_skill.py`
- Verify file exists: `ls -la /home/godwin/Downloads/AI_agent/hermes_trading_skill.py`

### "API key not found"

- Ensure `~/.hermes/.env` exists with credentials
- Check permissions: `chmod 600 ~/.hermes/.env`
- Reload Hermes: `hermes update` or restart

### Skill returns error

- Check logs: `tail -f ~/.hermes/logs/trading.log`
- Verify your trading system files exist (multi_agent_trading.py, test_agent.py, etc.)
- Test manually: `python3 hermes_trading_skill.py` from project root

### Telegram not receiving messages

- Verify `TELEGRAM_BOT_TOKEN` in `~/.hermes/.env`
- Verify user ID in config.yaml
- Send message to bot first to initiate chat
- Check gateway logs: `tail -f ~/.hermes/logs/gateway.log`

## Advanced Usage

### Creating Additional Skills

You can create more skills alongside trading:

```bash
# Create a market analysis skill
cat > ~/.hermes/skills/market_analysis.py << 'EOF'
def analyze_market(symbol="EURUSD"):
    # Your analysis logic
    return {"trend": "bullish", "strength": 0.75}
EOF
```

### Using Subagents for Parallel Analysis

Hermes can spawn subagents for complex workflows:

```bash
# In Hermes conversation:
[User]: Run 5 parallel backtests on different parameters and summarize
# → Hermes spawns subagents to test: SL/TP ratios, entry thresholds, etc.
# → Aggregates results → Reports best configuration
```

### Custom Memory & Learning

Hermes learns from your trading:

```bash
/memory review trading     # See what Hermes learned about your patterns
/memory add "EURUSD tends to breakout Fridays 14:00-16:00 GMT"
/memory search profitable patterns
```

## Security Best Practices

1. **Never commit credentials**

   ```bash
   # Good:
   export GROQ_API_KEY="abc123" # in ~/.hermes/.env

   # Bad:
   GROQ_API_KEY = "abc123" # in config.yaml or Python file
   ```

2. **Protect credentials file**

   ```bash
   chmod 600 ~/.hermes/.env
   ```

3. **Use Hermes approval system**
   - Dangerous operations require user confirmation
   - Enable in config: `approvals.mode: "on"` (default)

4. **For production/trading with real money**
   - Use container isolation: `terminal.backend: docker`
   - Enable command approval: `approvals.mode: "on"`
   - Test thoroughly on paper trading first
   - Monitor via Telegram/Discord alerts

## Next Steps

1. ✅ Install Hermes
2. ✅ Configure with your API keys
3. ✅ Set up Telegram/Discord (optional but recommended)
4. ✅ Test commands in CLI: `/trading_signal`, `/trading_stats`
5. ✅ Enable cron jobs for automation
6. ✅ Monitor alerts on Telegram (if enabled)
7. 🎯 Deploy to production (on VPS, Modal, or local 24/7 machine)

For Telegram bot setup and VPS/systemd deployment, see `TELEGRAM_DEPLOYMENT.md`.

## Support

- **Hermes Docs**: https://hermes-agent.nousresearch.com/docs/
- **Discord Community**: https://discord.gg/NousResearch
- **Issues**: https://github.com/NousResearch/hermes-agent/issues
- **Skills Hub**: https://agentskills.io/

---

**Your trading system is now a Hermes Agent skill!** 🎉

Hermes will handle all orchestration, scheduling, and communication while your trading logic remains independent and testable.
