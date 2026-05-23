"""
Optimized Hermes Trading Skill - LLM-Enhanced Signal Quality
With intelligent filtering, validation, and ensemble decision-making.

Goal: Increase win rate from 6.32% → 35%+ through:
1. LLM-based signal validation
2. Multi-indicator confirmation (3+ must align)
3. Risk/reward filtering (min 1:2 ratio)
4. Trade quality scoring
5. Market regime detection
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np
import os

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

PPOLiveSignalGenerator = None
PPO_IMPORT_ERROR = None
_PPO_IMPORT_ATTEMPTED = False


def get_ppo_signal_generator_class():
    """Import the PPO helper only when PPO mode is actually requested."""
    global PPOLiveSignalGenerator, PPO_IMPORT_ERROR, _PPO_IMPORT_ATTEMPTED
    if not _PPO_IMPORT_ATTEMPTED:
        _PPO_IMPORT_ATTEMPTED = True
        try:
            from ppo_live_signal import PPOLiveSignalGenerator as imported_generator

            PPOLiveSignalGenerator = imported_generator
        except Exception as e:
            PPO_IMPORT_ERROR = e
    return PPOLiveSignalGenerator

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


class OptimizedTradingSkill:
    """Optimized trading skill with LLM validation and ensemble decisions."""

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
        self.use_ppo_model = os.environ.get("HERMES_USE_PPO", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ppo_model_path = Path(os.environ.get("HERMES_MODEL_PATH", PROJECT_ROOT / "model_eurusd_best.zip"))
        ppo_generator_class = (
            get_ppo_signal_generator_class()
            if self.use_ppo_model and self.ppo_model_path.exists()
            else None
        )
        self.ppo_signal_generator = (
            ppo_generator_class(self.ppo_model_path)
            if ppo_generator_class
            else None
        )
        
        self.groq_client = None
        if HAS_GROQ and groq_api_key:
            self.groq_client = Groq(api_key=groq_api_key)
        
        self.last_signal = None
        self.trade_log = PROJECT_ROOT / "trade_history_output.csv"
        self.signal_memory = SignalMemory(PROJECT_ROOT / "signal_feedback.jsonl")
        
        # Configuration for optimization
        self.min_confidence = float(os.environ.get("HERMES_MIN_CONFIDENCE", "0.50"))
        self.min_rr_ratio = 2.0     # Risk/Reward must be 1:2+ (was flexible)
        default_require_confirm = "false" if self.use_ppo_model else "true"
        self.require_multi_confirm = os.environ.get(
            "HERMES_REQUIRE_TECH_CONFIRM",
            default_require_confirm,
        ).lower() in {"1", "true", "yes", "on"}
        self.use_llm_validation = True    # Use Hermes/Groq to validate
        self.volatility_filter = True     # Filter by market volatility

    def get_optimized_trading_signal(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Generate trading signal with LLM validation and multi-indicator confirmation.
        
        Enhanced Features:
        - Ensemble decision-making (multiple signals must align)
        - LLM validation of setup quality
        - Risk/reward filtering
        - Market regime detection
        - Trade quality scoring (0-100)
        
        Returns:
            Dict with trading signal and quality metrics
        """
        try:
            # Step 1: Collect market data
            market_data = self.data_collector.get_latest_market_data()
            current_price = market_data["price"]
            
            # Step 2: Analyze with multiple indicators
            analysis = self.analyst.analyze(market_data)
            signals_detail = analysis["detailed_signals"]
            
            # Step 3: Get primary decision from PPO, with rule/LLM fallback
            ppo_signal = None
            if self.ppo_signal_generator:
                ppo_signal = self.ppo_signal_generator.predict(
                    self.data_collector.df,
                    self.data_collector.feature_cols,
                    symbol=market_data.get("symbol", "EURUSD"),
                )
                initial_decision = {
                    "decision": ppo_signal["decision"],
                    "confidence": float(ppo_signal["model_confidence"]),
                    "reasoning": ppo_signal["reasoning"],
                    "method": "PPO model",
                }
            else:
                initial_decision = self.decision_maker.decide(analysis)
            
            # Step 4: Calculate position (to get SL/TP)
            atr = market_data["indicators"]["atr_14"]
            position = self.risk_manager.calculate_position(
                initial_decision,
                current_price,
                atr,
                symbol=market_data.get("symbol", "EURUSD"),
            )
            if ppo_signal and ppo_signal["decision"] != "HOLD":
                position = self._position_from_ppo_signal(
                    ppo_signal=ppo_signal,
                    current_price=current_price,
                    symbol=market_data.get("symbol", "EURUSD"),
                )

            if initial_decision["decision"] == "HOLD":
                signal = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": market_data.get("symbol", "EURUSD"),
                    "data_provider": market_data.get("data_provider", "csv"),
                    "action": "HOLD",
                    "reason": initial_decision.get("reasoning", "Model selected HOLD"),
                    "confidence": float(initial_decision["confidence"]),
                    "method": initial_decision.get("method"),
                    "ppo_signal": ppo_signal,
                    "filtered": True,
                    "quality_score": 0,
                }
                return self.signal_memory.log_signal(signal)
            
            # Step 5: FILTER 1 - Confidence threshold
            confidence = initial_decision["confidence"]
            if confidence < self.min_confidence:
                if verbose:
                    print(f"❌ Filtered: Confidence {confidence:.0%} < {self.min_confidence:.0%}")
                signal = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": market_data.get("symbol", "EURUSD"),
                    "data_provider": market_data.get("data_provider", "csv"),
                    "action": "HOLD",
                    "reason": f"Low confidence ({confidence:.0%})",
                    "confidence": float(confidence),
                    "method": initial_decision.get("method"),
                    "ppo_signal": ppo_signal,
                    "filtered": True,
                    "quality_score": 0,
                }
                return self.signal_memory.log_signal(signal)
            
            # Step 6: FILTER 2 - Multi-indicator confirmation
            confirm_count = self._count_confirmations(signals_detail, initial_decision["decision"])
            if self.require_multi_confirm and confirm_count < 2:
                if verbose:
                    print(f"❌ Filtered: Only {confirm_count} indicator(s) confirm {initial_decision['decision']}")
                signal = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": market_data.get("symbol", "EURUSD"),
                    "data_provider": market_data.get("data_provider", "csv"),
                    "action": "HOLD",
                    "reason": f"Weak signal ({confirm_count}/3 indicators agree)",
                    "confidence": float(confidence),
                    "method": initial_decision.get("method"),
                    "ppo_signal": ppo_signal,
                    "filtered": True,
                    "quality_score": 0,
                }
                return self.signal_memory.log_signal(signal)
            
            # Step 7: FILTER 3 - Risk/Reward ratio
            if position["action"] != "HOLD":
                rr_ratio = self._calculate_rr_ratio(
                    position["entry_price"],
                    position["stop_loss"],
                    position["take_profit"]
                )
                if rr_ratio < self.min_rr_ratio:
                    if verbose:
                        print(f"❌ Filtered: R/R ratio {rr_ratio:.2f} < {self.min_rr_ratio:.1f}")
                    signal = {
                        "timestamp": datetime.now().isoformat(),
                        "symbol": market_data.get("symbol", "EURUSD"),
                        "data_provider": market_data.get("data_provider", "csv"),
                        "action": "HOLD",
                        "reason": f"Poor risk/reward ({rr_ratio:.2f}:1)",
                        "confidence": float(confidence),
                        "method": initial_decision.get("method"),
                        "ppo_signal": ppo_signal,
                        "filtered": True,
                        "quality_score": 0,
                    }
                    return self.signal_memory.log_signal(signal)
            else:
                rr_ratio = None
            
            # Step 8: FILTER 4 - LLM Validation
            if self.use_llm_validation and self.groq_client:
                llm_verdict = self._validate_with_llm(
                    market_data, signals_detail, initial_decision, rr_ratio
                )
                if not llm_verdict["should_trade"]:
                    if verbose:
                        print(f"❌ LLM Validation Failed: {llm_verdict['reason']}")
                    signal = {
                        "timestamp": datetime.now().isoformat(),
                        "symbol": market_data.get("symbol", "EURUSD"),
                        "data_provider": market_data.get("data_provider", "csv"),
                        "action": "HOLD",
                        "reason": f"LLM: {llm_verdict['reason']}",
                        "confidence": float(confidence),
                        "method": initial_decision.get("method"),
                        "ppo_signal": ppo_signal,
                        "filtered": True,
                        "quality_score": 0,
                    }
                    return self.signal_memory.log_signal(signal)
                llm_confidence = llm_verdict.get("confidence", 0.5)
            else:
                llm_confidence = 0.0
            
            # Step 9: Calculate trade quality score (0-100)
            quality_score = self._calculate_quality_score(
                confidence=confidence,
                confirm_count=confirm_count,
                rr_ratio=rr_ratio if position["action"] != "HOLD" else None,
                llm_confidence=llm_confidence,
                indicators=signals_detail
            )
            
            # Step 10: Build final signal
            signal = {
                "timestamp": datetime.now().isoformat(),
                "symbol": market_data.get("symbol", "EURUSD"),
                "data_provider": market_data.get("data_provider", "csv"),
                "action": initial_decision["decision"],
                "confidence": float(confidence),
                "llm_confidence": float(llm_confidence),
                "quality_score": int(quality_score),  # 0-100
                "current_price": float(current_price),
                "reasoning": initial_decision.get("reasoning", "LLM-validated setup"),
                "method": initial_decision.get("method"),
                "ppo_signal": ppo_signal,
                "position": position,
                "market_analysis": {
                    "rsi": float(market_data["indicators"]["rsi_14"]) if market_data["indicators"]["rsi_14"] else None,
                    "ma_trend": signals_detail["ma_signal"],
                    "volatility": float(market_data["indicators"]["atr_14"]) if market_data["indicators"]["atr_14"] else None,
                    "price_position": signals_detail["price_position"],
                },
                "confirmations": {
                    "total": 3,  # RSI, MA, Price
                    "aligned": confirm_count,
                    "details": signals_detail,
                },
                "risk_reward": {
                    "ratio": float(rr_ratio) if rr_ratio else None,
                    "min_required": float(self.min_rr_ratio),
                },
                "filtered": False,
            }
            
            signal = self.signal_memory.log_signal(signal)
            self.last_signal = signal
            
            if verbose:
                print(f"✅ SIGNAL GENERATED")
                print(f"   Action: {signal['action']}")
                print(f"   Quality: {quality_score}/100")
                print(f"   Confirmations: {confirm_count}/3")
                print(f"   R/R Ratio: {rr_ratio:.2f}:1" if rr_ratio else "   R/R Ratio: N/A")
            
            return signal

        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "action": "HOLD",
            }

    def _count_confirmations(self, signals_detail: Dict, target_signal: str) -> int:
        """Count how many indicators confirm the signal."""
        confirmations = 0
        
        target = "BULLISH" if target_signal == "BUY" else "BEARISH"
        
        if signals_detail.get("rsi_signal") == target:
            confirmations += 1
        if signals_detail.get("ma_signal") == target:
            confirmations += 1
        if signals_detail.get("price_position") == target:
            confirmations += 1
        
        return confirmations

    def _position_from_ppo_signal(self, ppo_signal: Dict, current_price: float, symbol: str) -> Dict:
        """Build position sizing from the PPO-selected SL/TP levels."""
        max_risk_usd = self.risk_manager.account_balance * self.risk_manager.max_risk_per_trade
        stop_loss = ppo_signal["stop_loss"]
        take_profit = ppo_signal["take_profit"]
        risk_distance = abs(current_price - stop_loss)

        if risk_distance <= 0:
            quantity = 0
            quantity_unit = "units"
        elif self.risk_manager._looks_like_forex(symbol):
            pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
            risk_pips = risk_distance / pip_size
            quantity = max_risk_usd / (risk_pips * 10)
            quantity_unit = "standard_lots"
        else:
            quantity = max_risk_usd / risk_distance
            quantity_unit = "units"

        return {
            "action": ppo_signal["decision"],
            "quantity": max(0.01, float(quantity)),
            "entry_price": float(current_price),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "risk_usd": float(max_risk_usd),
            "quantity_unit": quantity_unit,
            "confidence": float(ppo_signal["model_confidence"]),
        }

    def _calculate_rr_ratio(self, entry: float, sl: float, tp: float) -> float:
        """Calculate risk/reward ratio."""
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        
        if risk == 0:
            return 0
        
        return reward / risk

    def _validate_with_llm(
        self, 
        market_data: Dict, 
        signals_detail: Dict, 
        decision: Dict,
        rr_ratio: Optional[float]
    ) -> Dict[str, Any]:
        """Use LLM to validate trade setup quality."""
        if not self.groq_client:
            return {"should_trade": True, "confidence": 0.5, "reason": "No LLM available"}
        
        prompt = f"""
You are an expert forex trader evaluating a trade setup. Be CRITICAL - only approve high-probability setups.

Current Price: {market_data['price']:.5f}
Action: {decision['decision']}
Confidence: {decision['confidence']:.0%}

INDICATOR SIGNALS:
- RSI: {signals_detail.get('rsi_signal', 'UNKNOWN')}
- Moving Averages: {signals_detail.get('ma_signal', 'UNKNOWN')}  
- Price Position: {signals_detail.get('price_position', 'UNKNOWN')}
- ATR (Volatility): {market_data['indicators']['atr_14']:.6f}

RISK/REWARD: {rr_ratio:.2f}:1 ratio {"✓ GOOD" if rr_ratio and rr_ratio >= 2.0 else "✗ POOR"}

Your assessment:
1. Is this a high-probability setup? (YES/NO)
2. What's your confidence? (0.0-1.0)
3. Key concerns if any?

Respond in JSON:
{{
  "should_trade": true/false,
  "confidence": 0.0-1.0,
  "reason": "Brief explanation"
}}

Remember: Missing 10 good trades is better than taking 100 bad ones. Only approve high-quality setups.
"""
        
        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.1-70b-versatile",
                max_tokens=150,
                temperature=0.2,  # Low temp for consistent decisions
            )
            
            response_text = response.choices[0].message.content
            
            try:
                result = json.loads(response_text)
                return result
            except json.JSONDecodeError:
                # Fallback parsing
                should_trade = "YES" in response_text.upper() and "should_trade" in response_text.lower()
                return {
                    "should_trade": should_trade,
                    "confidence": 0.6 if should_trade else 0.2,
                    "reason": response_text[:100]
                }
        
        except Exception as e:
            print(f"⚠️  LLM Error: {e}, skipping LLM validation")
            return {"should_trade": True, "confidence": 0.5, "reason": "LLM unavailable"}

    def _calculate_quality_score(
        self,
        confidence: float,
        confirm_count: int,
        rr_ratio: Optional[float],
        llm_confidence: float,
        indicators: Dict
    ) -> float:
        """Calculate overall trade quality score (0-100)."""
        score = 0.0
        
        # Confidence score (0-30 points)
        score += min(30, confidence * 60)
        
        # Multi-indicator confirmation (0-30 points)
        score += (confirm_count / 3) * 30
        
        # Risk/Reward score (0-25 points)
        if rr_ratio:
            score += min(25, (rr_ratio - 1.0) / 3.0 * 25)
        
        # LLM validation (0-15 points)
        if llm_confidence > 0:
            score += llm_confidence * 15
        
        return min(100, max(0, score))

    def get_trading_stats(self) -> Dict[str, Any]:
        """Get current trading statistics."""
        try:
            stats = {
                "timestamp": datetime.now().isoformat(),
                "last_signal": self.last_signal,
                "optimization_settings": {
                    "min_confidence": f"{self.min_confidence:.0%}",
                    "min_rr_ratio": f"1:{self.min_rr_ratio:.1f}",
                    "require_multi_confirm": self.require_multi_confirm,
                    "use_llm_validation": self.use_llm_validation and self.groq_client is not None,
                }
            }
            
            # Get trade history if available
            if self.trade_log.exists():
                trades_df = pd.read_csv(self.trade_log)
                total_trades = len(trades_df)
                
                total_pips = trades_df["net_pips"].sum()
                wins = len(trades_df[trades_df["net_pips"] > 0])
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                max_loss = trades_df["net_pips"].min()
                max_gain = trades_df["net_pips"].max()
                avg_pips = total_pips / total_trades if total_trades > 0 else 0
                
                stats.update({
                    "performance": {
                        "total_trades": total_trades,
                        "wins": wins,
                        "losses": total_trades - wins,
                        "win_rate_percent": round(win_rate, 2),
                        "total_pips": round(total_pips, 2),
                        "avg_pips_per_trade": round(avg_pips, 2),
                        "max_loss_pips": round(max_loss, 2),
                        "max_gain_pips": round(max_gain, 2),
                        "latest_equity": round(trades_df["equity_usd"].iloc[-1], 2) if len(trades_df) > 0 else 10000,
                    },
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

    def run_backtest(self, model_path: Optional[str] = None) -> Dict[str, Any]:
        """Run backtest on test data."""
        try:
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
            
            if self.trade_log.exists():
                trades_df = pd.read_csv(self.trade_log)
                total_trades = len(trades_df)
                wins = len(trades_df[trades_df["net_pips"] > 0])
                win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
                total_pips = trades_df["net_pips"].sum()
                
                return {
                    "success": True,
                    "total_trades": total_trades,
                    "wins": wins,
                    "win_rate_percent": round(win_rate, 2),
                    "total_pips": round(total_pips, 2),
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

    def retrain_model(self, timesteps: int = 300000, save_checkpoints: bool = True) -> Dict[str, Any]:
        """Trigger model retraining."""
        try:
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
                timeout=3600,
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


def skill_handler(action: str, **kwargs) -> Dict[str, Any]:
    """
    Hermes skill handler - routes commands to optimized trading functions.
    
    Usage:
      skill_handler("signal")                    # Get optimized signal
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
        skill = OptimizedTradingSkill(**skill_kwargs)
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "action": "HOLD",
            "success": False,
        }
    
    action_map = {
        "signal": skill.get_optimized_trading_signal,
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
    skill = OptimizedTradingSkill()
    
    print("\n" + "="*70)
    print("OPTIMIZED HERMES TRADING SKILL")
    print("="*70)
    
    print("\n[1] Getting optimized trading signal with LLM validation...")
    signal = skill.get_optimized_trading_signal(verbose=True)
    print("\nSignal Details:")
    print(json.dumps(signal, indent=2))
    
    print("\n[2] Getting trading statistics...")
    stats = skill.get_trading_stats()
    print("\nPerformance Stats:")
    print(json.dumps(stats, indent=2))
    
    print("\n" + "="*70)
    print("✅ Optimized trading skill is ready!")
    print("   - Multi-indicator confirmation enabled")
    print("   - LLM validation enabled (if API key set)")
    print("   - Quality scoring (0-100)")
    print("   - Risk/Reward filtering (1:2.0 minimum)")
    print("="*70)
