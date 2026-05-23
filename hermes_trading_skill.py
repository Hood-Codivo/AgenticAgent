"""
Hermes Trading Skill - Wraps trading system as Hermes-compatible tools.

This skill exposes your existing trading system to Hermes Agent, allowing:
- Real-time trading signal generation
- Automated backtesting
- Model retraining with schedules
- Trade performance reporting

Usage in Hermes:
  /trading_signal      - Get next trading signal
  /backtest_report     - Run backtest and get summary
  /retrain_model       - Trigger model retraining
  /trading_stats       - Get account and trade statistics
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from multi_agent_trading import (
    DataCollectorAgent,
    AnalystAgent,
    DecisionMakerAgent,
    RiskManagerAgent,
)
from live_market_data import live_provider_enabled
from signal_memory import SignalMemory
import os


class TradingSkill:
    """Hermes-compatible trading skill wrapper."""

    def __init__(
        self,
        symbol: Optional[str] = None,
        interval: Optional[str] = None,
        data_provider: Optional[str] = None,
    ):
        """Initialize trading agents."""
        csv_path = PROJECT_ROOT / "data" / "EURUSD_Candlestick_1_Hour_BID_01.07.2020-15.07.2023.csv"
        requested_provider = data_provider or os.environ.get("HERMES_DATA_PROVIDER")
        live_provider = (
            requested_provider
            if requested_provider and requested_provider.lower() != "csv"
            else None
        )
        symbol = symbol or os.environ.get("HERMES_SYMBOL", "EURUSD")
        interval = interval or os.environ.get("HERMES_INTERVAL", "1h")
        self.data_collector = DataCollectorAgent(
            str(csv_path),
            live_provider=live_provider,
            symbol=symbol,
            interval=interval,
        )
        self.analyst = AnalystAgent()
        
        # Get Groq API key from environment
        groq_api_key = os.environ.get("GROQ_API_KEY")
        self.decision_maker = DecisionMakerAgent(use_groq=bool(groq_api_key), api_key=groq_api_key)
        self.risk_manager = RiskManagerAgent()
        self.last_signal = None
        self.trade_log = PROJECT_ROOT / "trade_history_output.csv"
        self.signal_memory = SignalMemory(PROJECT_ROOT / "signal_feedback.jsonl")

    def get_trading_signal(self) -> Dict[str, Any]:
        """
        Execute multi-agent pipeline to generate trading signal.
        
        Returns:
            Dict with keys:
                - action: "BUY", "SELL", or "HOLD"
                - confidence: float 0-1
                - entry_price: float
                - stop_loss: float
                - take_profit: float
                - reasoning: str
        """
        try:
            # Agent 1: Collect market data
            market_data = self.data_collector.get_latest_market_data()
            current_price = market_data["price"]
            
            # Agent 2: Analyze technical indicators
            analysis = self.analyst.analyze(market_data)
            
            # Agent 3: Make decision
            decision = self.decision_maker.decide(analysis)
            
            # Agent 4: Calculate risk management
            atr = market_data["indicators"]["atr_14"]
            position = self.risk_manager.calculate_position(
                decision,
                current_price,
                atr,
                symbol=market_data.get("symbol", "EURUSD"),
            )
            
            signal = {
                "timestamp": datetime.now().isoformat(),
                "symbol": market_data.get("symbol", "EURUSD"),
                "data_provider": market_data.get("data_provider", "csv"),
                "action": decision["decision"],
                "confidence": decision["confidence"],
                "current_price": current_price,
                "reasoning": decision.get("reasoning", "No specific reason"),
                "position": position,
                "market_analysis": {
                    "rsi": market_data["indicators"]["rsi_14"],
                    "ma_trend": analysis["detailed_signals"]["ma_signal"],
                    "volatility": market_data["indicators"]["atr_14"],
                    "price_position": analysis["detailed_signals"]["price_position"],
                },
            }
            signal = self.signal_memory.log_signal(signal)
            self.last_signal = signal
            return signal

        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "action": "HOLD",
            }

    def run_backtest(self, model_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run backtest on test data.
        
        Args:
            model_path: Path to trained model (optional, uses best if None)
            
        Returns:
            Dict with backtest metrics
        """
        try:
            # Run test_agent.py
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "test_agent.py"),
                    "--model-path",
                    str(PROJECT_ROOT / (model_path or "model_eurusd_best")),
                ],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=PROJECT_ROOT,
            )
            
            if result.returncode != 0:
                return {"error": result.stderr, "success": False}
            
            # Parse results if trade history exists
            if self.trade_log.exists():
                trades_df = pd.read_csv(self.trade_log)
                total_trades = len(trades_df)
                pnl_col = "net_pips" if "net_pips" in trades_df.columns else "Profit/Loss"
                if pnl_col not in trades_df.columns:
                    return {
                        "error": f"Trade log missing P/L column. Found: {list(trades_df.columns)}",
                        "success": False,
                    }

                wins = len(trades_df[trades_df[pnl_col] > 0])
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                total_pnl = trades_df[pnl_col].sum()
                max_loss = trades_df[pnl_col].min()
                max_gain = trades_df[pnl_col].max()
                
                return {
                    "success": True,
                    "total_trades": total_trades,
                    "wins": wins,
                    "win_rate_percent": round(win_rate, 2),
                    "pnl_unit": "pips" if pnl_col == "net_pips" else "account_currency",
                    "total_pnl": round(total_pnl, 2),
                    "max_loss": round(max_loss, 2),
                    "max_gain": round(max_gain, 2),
                    "avg_trade": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
                    "timestamp": datetime.now().isoformat(),
                }
            
            return {
                "success": True,
                "message": "Backtest completed",
                "timestamp": datetime.now().isoformat(),
            }

        except subprocess.TimeoutExpired:
            return {"error": "Backtest timeout (>10 mins)", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    def retrain_model(
        self, timesteps: int = 100000, save_checkpoints: bool = True
    ) -> Dict[str, Any]:
        """
        Trigger model retraining.
        
        Args:
            timesteps: Number of training steps
            save_checkpoints: Whether to save checkpoints
            
        Returns:
            Dict with training status
        """
        try:
            # Run training with custom timesteps
            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "train_agent.py"),
                    "--timesteps",
                    str(timesteps),
                    *([] if save_checkpoints else ["--no-checkpoints"]),
                ],
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour max
                cwd=PROJECT_ROOT,
            )
            
            if result.returncode != 0:
                return {
                    "error": result.stderr,
                    "success": False,
                    "timestamp": datetime.now().isoformat(),
                }
            
            return {
                "success": True,
                "message": f"Training completed ({timesteps} steps)",
                "timestamp": datetime.now().isoformat(),
            }

        except subprocess.TimeoutExpired:
            return {"error": "Training timeout (>1 hour)", "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    def get_trading_stats(self) -> Dict[str, Any]:
        """
        Get current trading statistics.
        
        Returns:
            Dict with performance metrics
        """
        try:
            stats = {
                "timestamp": datetime.now().isoformat(),
                "last_signal": self.last_signal,
            }
            
            # Get trade history if available
            if self.trade_log.exists():
                trades_df = pd.read_csv(self.trade_log)
                total_trades = len(trades_df)
                
                # Calculate profit in pips
                total_pips = trades_df["net_pips"].sum()
                wins = len(trades_df[trades_df["net_pips"] > 0])
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                max_loss = trades_df["net_pips"].min()
                max_gain = trades_df["net_pips"].max()
                avg_pips = total_pips / total_trades if total_trades > 0 else 0
                
                stats.update({
                    "total_trades": total_trades,
                    "wins": wins,
                    "losses": total_trades - wins,
                    "win_rate_percent": round(win_rate, 2),
                    "total_pips": round(total_pips, 2),
                    "avg_pips_per_trade": round(avg_pips, 2),
                    "max_loss_pips": round(max_loss, 2),
                    "max_gain_pips": round(max_gain, 2),
                    "latest_equity": round(trades_df["equity_usd"].iloc[-1], 2) if len(trades_df) > 0 else 10000,
                    "recent_trades": trades_df.tail(3)[["reason", "net_pips", "equity_usd"]].to_dict("records"),
                })

            stats["learning"] = self.signal_memory.summary()
            
            return stats

        except Exception as e:
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    def record_signal_feedback(
        self,
        signal_id: Optional[str] = None,
        outcome: str = "loss",
        reward: Optional[float] = None,
        notes: str = "",
        exit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Reward or penalize a signal after seeing what happened."""
        return self.signal_memory.record_feedback(
            signal_id=signal_id,
            outcome=outcome,
            reward=reward,
            notes=notes,
            exit_price=exit_price,
        )

    def get_learning_summary(self) -> Dict[str, Any]:
        """Return signal feedback and reward/penalty summary."""
        return self.signal_memory.summary()


def skill_handler(action: str, **kwargs) -> Dict[str, Any]:
    """
    Hermes skill handler - routes commands to appropriate trading functions.
    
    Usage:
      skill_handler("signal")                    # Get trading signal
      skill_handler("signals")                   # Get signals for watchlist
      skill_handler("feedback", signal_id="...", outcome="win", reward=1)
      skill_handler("learning")                  # Get feedback summary
      skill_handler("backtest")                  # Run backtest
      skill_handler("retrain", timesteps=100000) # Retrain model
      skill_handler("stats")                      # Get statistics
    """
    action = action.lower()
    if action == "signals":
        symbols = kwargs.pop("symbols", None) or os.environ.get("HERMES_WATCHLIST", "EURUSD,GBPUSD,AAPL")
        if isinstance(symbols, str):
            symbols = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
        data_provider = kwargs.pop("data_provider", None)
        interval = kwargs.pop("interval", None)
        results = []
        for symbol in symbols:
            signal_kwargs = {"symbol": symbol}
            if data_provider is not None:
                signal_kwargs["data_provider"] = data_provider
            if interval is not None:
                signal_kwargs["interval"] = interval
            result = skill_handler("signal", **signal_kwargs)
            results.append(result)
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "signals": results,
        }

    skill_kwargs = {
        key: kwargs.pop(key)
        for key in ("symbol", "interval", "data_provider")
        if key in kwargs and kwargs[key] is not None
    }

    try:
        skill = TradingSkill(**skill_kwargs)
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "action": "HOLD",
            "success": False,
        }
    
    action_map = {
        "signal": skill.get_trading_signal,
        "backtest": skill.run_backtest,
        "retrain": skill.retrain_model,
        "stats": skill.get_trading_stats,
        "feedback": skill.record_signal_feedback,
        "learning": skill.get_learning_summary,
    }
    
    handler = action_map.get(action)
    if not handler:
        return {"error": f"Unknown action: {action}"}
    
    return handler(**kwargs)


if __name__ == "__main__":
    # Test the skill
    skill = TradingSkill()
    
    print("\n[1] Getting trading signal...")
    signal = skill.get_trading_signal()
    print(json.dumps(signal, indent=2))
    
    print("\n[2] Getting trading statistics...")
    stats = skill.get_trading_stats()
    print(json.dumps(stats, indent=2))
    
    print("\nHermes trading skill is ready!")
    print("Use /trading_signal, /backtest, /retrain, /trading_stats in Hermes")
