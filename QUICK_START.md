# Hermes Trading Bot - Quick Start (30 minutes)

## What You Have Now

✅ **Hermes Trading Skill** - Fully functional Python skill that wraps your trading system
✅ **4 Built-in Agents** - Data Collector, Analyst, Decision Maker, Risk Manager
✅ **Live Signal Generation** - Real-time trading signals with position sizing
✅ **Trade Statistics** - Performance tracking and analytics
✅ **Configurable** - Works with or without Groq API key

## Getting Started (3 Steps)

### Step 1: Verify the Skill Works (Already Done! ✓)

```bash
cd /home/godwin/Downloads/AI_agent
source venv/bin/activate
python3 hermes_trading_skill.py
```

**Output shows:**

- ✅ Trading signal: BUY with 33% confidence
- ✅ Position: 10,324 lots with SL/TP
- ✅ Statistics: 601 trades, 6.32% win rate
- ✅ Latest equity: $10,040

---

### Step 2: Install Hermes Agent (Recommended - Optional)

To get Hermes messaging (Telegram, Discord, scheduling), install it:

```bash
# Install Hermes (handles platform detection)
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Verify installation
hermes --version

# Run setup wizard
hermes setup
```

When prompted:

- **Model Provider:** Choose `OpenRouter` (200+ models) or `Groq`
- **Telegram/Discord:** Skip for now (optional)
- **Working Directory:** `/home/godwin/Downloads/AI_agent`

### Step 3: Configure Credentials (2 minutes)

Create `~/.hermes/.env` from the template:

```bash
mkdir -p ~/.hermes
cp /home/godwin/Downloads/AI_agent/hermes.env.example ~/.hermes/.env
nano ~/.hermes/.env

# Protect credentials
chmod 600 ~/.hermes/.env
```

For free live/recent candles, edit `~/.hermes/.env` and set:

```bash
export HERMES_DATA_PROVIDER="yfinance"
export HERMES_SYMBOL="EURUSD"  # examples: GBPUSD, BTCUSD, AAPL, TSLA
export HERMES_INTERVAL="1h"
```

For Deriv forex data, use:

```bash
export HERMES_DATA_PROVIDER="deriv"
export HERMES_SYMBOL="EURUSD"  # maps to frxEURUSD
export HERMES_INTERVAL="1h"
```

Paid/keyed alternatives still work if you later want them:

```bash
export HERMES_DATA_PROVIDER="oanda"
export OANDA_API_KEY="your-oanda-api-token"
export OANDA_ENV="practice"
```

or:

```bash
export HERMES_DATA_PROVIDER="twelvedata"
export TWELVE_DATA_API_KEY="your-twelve-data-api-key"
```

---

## Using Your Trading Skill

### In Hermes CLI

```bash
# Start Hermes
hermes

# Then use slash commands:
/trading_signal         # Get next trading signal
/trading_stats          # Get performance metrics
/backtest_report        # Run backtest
/retrain_model          # Trigger model retraining (100k steps)
/model                  # Switch LLM model
```

### Programmatically

```python
from hermes_trading_skill import skill_handler

# Get signal
signal = skill_handler("signal")
print(f"Action: {signal['action']}")
print(f"Entry: {signal['position']['entry_price']}")

# Get stats
stats = skill_handler("stats")
print(f"Win Rate: {stats['win_rate_percent']}%")
```

### Direct Python Import

```python
from hermes_trading_skill import TradingSkill

skill = TradingSkill()
signal = skill.get_trading_signal()
stats = skill.get_trading_stats()
```

---

## Sample Outputs

### Trading Signal

```json
{
  "action": "BUY",
  "confidence": 0.33,
  "current_price": 1.12235,
  "position": {
    "entry_price": 1.12235,
    "stop_loss": 1.12041,
    "take_profit": 1.12622,
    "quantity": 10324.08,
    "risk_usd": 200
  },
  "market_structure": {
    "trend": "UPTREND",
    "structure": "HH_HL",
    "break_of_structure": "BULLISH_BOS",
    "entry_bias": "Buy the dip at the higher low, then ride the break above the prior high"
  }
}
```

### Trading Statistics

```json
{
  "total_trades": 601,
  "wins": 38,
  "win_rate_percent": 6.32,
  "total_pips": 4.0,
  "avg_pips_per_trade": 0.01,
  "latest_equity": 10040.0
}
```

---

## Architecture

```
Your Trading System (Hermes-Compatible)
│
├─ hermes_trading_skill.py
│  └─ TradingSkill class
│     ├─ get_trading_signal()    → BUY/SELL/HOLD
│     ├─ get_trading_stats()      → Performance metrics
│     ├─ run_backtest()           → Test on historical data
│     └─ retrain_model()          → Update PPO model
│
├─ multi_agent_trading.py
│  ├─ DataCollectorAgent          → Fetch OHLCV candles
│  ├─ AnalystAgent                → Pure price action structure
│  ├─ DecisionMakerAgent          → LLM decision (Groq or rule-based)
│  └─ RiskManagerAgent            → Position sizing + SL/TP
│
└─ Live Market Data
   └─ yfinance / Deriv / OANDA / Twelve Data
```

---

## Features

### Available Now (No Setup Needed)

- ✅ Trading signal generation
- ✅ Risk-managed position sizing
- ✅ Trade history tracking
- ✅ Performance statistics
- ✅ Pure price-action structure analysis
- ✅ Fallback rule-based decision making

### With Hermes + API Key

- 🔄 LLM-powered decisions (Groq, OpenAI, Claude, etc.)
- 📅 Automated scheduling (daily signals, weekly backtests)
- 💬 Multi-platform alerts (Telegram, Discord, Slack)
- 🧠 Persistent memory of trade patterns
- ⚙️ Model switching without code changes

---

## Troubleshooting

### Skill says "HOLD" always?

The skill uses a 30% confidence threshold to trade. Check:

```bash
# Test manually
python3 hermes_trading_skill.py
# Look for "confidence" value - needs > 0.30 to trade
```

### Want to customize behavior?

Edit `hermes_trading_skill.py`:

- Line 108: `max_risk_per_trade = 0.02` (change to 0.01 for smaller positions)
- Line 150: Confidence threshold in `_simple_decision`

### Need to change CSV data?

Update line 45:

```python
csv_path = PROJECT_ROOT / "data" / "YOUR_CSV_FILE.csv"
```

---

## Next Steps

**Option A: Keep it Simple** (Recommended for now)

- Use `python3 hermes_trading_skill.py` to get signals
- Integrate via your own API/schedule
- No Hermes installation needed

**Option B: Full Hermes Integration**

1. Install Hermes: `curl -fsSL ... | bash`
2. Copy skill to Hermes skills directory
3. Configure cron jobs for automation
4. Get Telegram alerts for trades

**Option C: Deploy to Cloud**

- Run on VPS (24/7 trading)
- Use Hermes Gateway + Telegram for monitoring
- Scheduled backtests every week
- Auto-retraining every month

---

## Files Created

1. **hermes_trading_skill.py** - Main skill file (importable, runnable)
2. **hermes_config.example.yaml** - Hermes configuration template
3. **HERMES_INTEGRATION.md** - Full setup guide (30+ pages)
4. **QUICK_START.md** - This file

---

## Support

- **Documentation:** See `HERMES_INTEGRATION.md` for detailed setup
- **Skill Tests:** Run `python3 hermes_trading_skill.py`
- **Hermes Help:** `hermes --help` or https://hermes-agent.nousresearch.com
- **Trading System:** Review `MULTI_AGENT_LLM_GUIDE.md` for architecture

---

**Your trading system is ready for Hermes!** 🚀

Start with Step 1 (already verified ✓), then optionally add Hermes for multi-platform access.
