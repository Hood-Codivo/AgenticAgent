"""
Multi-Agent Trading System
- Agent 1: Data Collector (fetches market candles)
- Agent 2: Analyst Agent (reads price-action structure)
- Agent 3: Decision Agent (LLM - makes final decision)
- Agent 4: Risk Manager (position sizing & execution)
"""

import pandas as pd
from typing import Dict, List, Optional
import json
from datetime import datetime
import os

# For LLM integration
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

from price_action_data import load_and_preprocess_data
from live_market_data import LiveMarketDataClient


# ============================================================================
# AGENT 1: DATA COLLECTOR
# ============================================================================
class DataCollectorAgent:
    """Collects and preprocesses market data"""
    
    def __init__(self, csv_path: Optional[str], live_provider: str = None, symbol: str = "EURUSD", interval: str = "1h"):
        self.csv_path = csv_path
        self.live_provider = live_provider
        self.symbol = symbol if live_provider else "EURUSD"
        self.interval = interval
        self.live_client = (
            LiveMarketDataClient(live_provider, symbol=symbol, interval=interval)
            if live_provider
            else None
        )
        self.df, self.feature_cols = self._load_data()
        self.latest_row = self.df.iloc[-1]

    def _load_data(self):
        if self.live_client:
            return self.live_client.fetch_preprocessed()
        if not self.csv_path:
            raise ValueError(
                "No market data source configured. Set HERMES_DATA_PROVIDER to yfinance, deriv, oanda, or twelvedata."
            )
        return load_and_preprocess_data(self.csv_path)
    
    def get_latest_market_data(self) -> Dict:
        """Return latest market data with recent OHLCV candles."""
        if self.live_client:
            self.df, self.feature_cols = self._load_data()
            self.latest_row = self.df.iloc[-1]

        row = self.latest_row
        recent = self.df.tail(160).reset_index()
        time_col = recent.columns[0]
        candles = [
            {
                "timestamp": str(candle[time_col]),
                "open": float(candle["Open"]),
                "high": float(candle["High"]),
                "low": float(candle["Low"]),
                "close": float(candle["Close"]),
                "volume": float(candle["Volume"]),
            }
            for _, candle in recent.iterrows()
        ]
        
        return {
            "timestamp": str(row.name),
            "symbol": self.symbol,
            "data_provider": self.live_provider or "csv",
            "price": float(row["Close"]),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "volume": float(row["Volume"]),
            "candles": candles,
        }


# ============================================================================
# AGENT 2: ANALYST AGENT
# ============================================================================
class AnalystAgent:
    """Analyzes pure price-action structure and generates trading signals."""
    
    def analyze(self, market_data: Dict) -> Dict:
        """Analyze market structure: HH/HL, LH/LL, and candle-close BOS."""
        candles = market_data["candles"]
        price = market_data["price"]
        structure = self._analyze_market_structure(candles)

        if structure["trend"] == "UPTREND" and structure["break_of_structure"] == "BULLISH_BOS":
            overall_signal = "BUY"
            confidence = self._confidence(structure, candles[-1], bullish=True)
        elif structure["trend"] == "DOWNTREND" and structure["break_of_structure"] == "BEARISH_BOS":
            overall_signal = "SELL"
            confidence = self._confidence(structure, candles[-1], bullish=False)
        else:
            overall_signal = "HOLD"
            confidence = 0.45 if structure["trend"] in {"UPTREND", "DOWNTREND"} else 0.30
        
        return {
            "overall_signal": overall_signal,
            "confidence": float(confidence),
            "detailed_signals": {
                "trend": structure["trend"],
                "structure": structure["structure"],
                "break_of_structure": structure["break_of_structure"],
                "entry_bias": structure["entry_bias"],
            },
            "market_structure": structure,
            "analysis_text": self._generate_analysis_text(structure, price),
        }
    
    def _analyze_market_structure(self, candles: List[Dict]) -> Dict:
        swings = self._find_swings(candles)
        peaks = swings["peaks"]
        troughs = swings["troughs"]
        last_close = candles[-1]["close"]

        if len(peaks) < 2 or len(troughs) < 2:
            return self._empty_structure("Not enough confirmed swing points")

        previous_peak, current_peak = peaks[-2], peaks[-1]
        previous_trough, current_trough = troughs[-2], troughs[-1]
        has_hh = current_peak["price"] > previous_peak["price"]
        has_hl = current_trough["price"] > previous_trough["price"]
        has_lh = current_peak["price"] < previous_peak["price"]
        has_ll = current_trough["price"] < previous_trough["price"]

        bullish_bos = has_hh and has_hl and last_close > current_peak["price"]
        bearish_bos = has_lh and has_ll and last_close < current_trough["price"]

        if has_hh and has_hl:
            trend = "UPTREND"
            structure = "HH_HL"
            entry_bias = "Buy the dip at the higher low, then ride the break above the prior high"
            waiting_for = f"Candle close above {current_peak['price']:.5f}"
            trigger_price = current_peak["price"]
            invalidation_price = current_trough["price"]
        elif has_lh and has_ll:
            trend = "DOWNTREND"
            structure = "LH_LL"
            entry_bias = "Sell the rally at the lower high, then ride the break below the prior low"
            waiting_for = f"Candle close below {current_trough['price']:.5f}"
            trigger_price = current_trough["price"]
            invalidation_price = current_peak["price"]
        else:
            trend = "RANGE_OR_TRANSITION"
            structure = "MIXED"
            entry_bias = "Stand aside until price confirms clean HH/HL or LH/LL structure"
            waiting_for = "Clean HH/HL or LH/LL structure"
            trigger_price = None
            invalidation_price = None

        if bullish_bos:
            break_of_structure = "BULLISH_BOS"
            waiting_for = "Confirmed bullish break of structure"
        elif bearish_bos:
            break_of_structure = "BEARISH_BOS"
            waiting_for = "Confirmed bearish break of structure"
        else:
            break_of_structure = "NONE"

        return {
            "trend": trend,
            "structure": structure,
            "break_of_structure": break_of_structure,
            "entry_bias": entry_bias,
            "waiting_for": waiting_for,
            "trigger_price": trigger_price,
            "invalidation_price": invalidation_price,
            "last_close": float(last_close),
            "previous_peak": previous_peak,
            "current_peak": current_peak,
            "previous_trough": previous_trough,
            "current_trough": current_trough,
        }

    def _find_swings(self, candles: List[Dict], left: int = 2, right: int = 2) -> Dict:
        peaks = []
        troughs = []
        for index in range(left, len(candles) - right):
            window = candles[index - left:index + right + 1]
            candle = candles[index]
            high = candle["high"]
            low = candle["low"]
            if high == max(item["high"] for item in window):
                peaks.append({"index": index, "timestamp": candle["timestamp"], "price": float(high)})
            if low == min(item["low"] for item in window):
                troughs.append({"index": index, "timestamp": candle["timestamp"], "price": float(low)})
        return {"peaks": peaks, "troughs": troughs}

    def _confidence(self, structure: Dict, latest_candle: Dict, bullish: bool) -> float:
        confidence = 0.72
        candle_agrees = latest_candle["close"] > latest_candle["open"] if bullish else latest_candle["close"] < latest_candle["open"]
        if candle_agrees:
            confidence += 0.08
        if structure["structure"] in {"HH_HL", "LH_LL"}:
            confidence += 0.05
        return min(confidence, 0.90)

    def _empty_structure(self, reason: str) -> Dict:
        return {
            "trend": "UNKNOWN",
            "structure": "INSUFFICIENT_SWINGS",
            "break_of_structure": "NONE",
            "entry_bias": reason,
            "last_close": None,
            "previous_peak": None,
            "current_peak": None,
            "previous_trough": None,
            "current_trough": None,
        }

    def _generate_analysis_text(self, structure: Dict, price: float) -> str:
        current_peak = structure.get("current_peak") or {}
        current_trough = structure.get("current_trough") or {}
        return f"""
Pure Price Action Analysis for {price:.5f}:
- Trend: {structure['trend']}
- Structure: {structure['structure']}
- Break of Structure: {structure['break_of_structure']}
- Last Confirmed Swing High: {current_peak.get('price')}
- Last Confirmed Swing Low: {current_trough.get('price')}
- Bias: {structure['entry_bias']}
"""


# ============================================================================
# AGENT 3: DECISION MAKER (LLM)
# ============================================================================
class DecisionMakerAgent:
    """Uses LLM to make final trading decision"""
    
    def __init__(self, use_groq: bool = True, api_key: str = None):
        self.use_groq = False  # Default to False
        self.api_key = api_key
        self.client = None
        self.model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        if use_groq and HAS_GROQ and api_key:
            try:
                self.client = Groq(api_key=api_key)
                self.use_groq = True
                print("✓ Groq LLM enabled")
            except Exception as e:
                print(f"⚠️  Groq disabled: {e}")
                self.use_groq = False
    
    def decide(self, analyst_result: Dict) -> Dict:
        """Make final decision based on analyst recommendation"""
        
        if not self.use_groq:
            return self._simple_decision(analyst_result)
        
        return self._llm_decision(analyst_result)
    
    def _simple_decision(self, analyst_result: Dict) -> Dict:
        """Fallback decision without LLM"""
        signal = analyst_result["overall_signal"]
        confidence = analyst_result["confidence"]
        
        if confidence < 0.50:
            decision = "HOLD"
        else:
            decision = signal
        
        return {
            "decision": decision,
            "confidence": float(confidence),
            "reasoning": f"Price-action signal: {signal}, Confidence: {confidence:.2%}",
            "method": "Price Action Structure"
        }
    
    def _llm_decision(self, analyst_result: Dict) -> Dict:
        """Use LLM to make decision"""
        
        prompt = f"""
You are a professional price-action trader. Based on the market structure below,
decide whether to BUY, SELL, or HOLD. Be concise and explain your reasoning.
Follow trend structure only. Buy only after HH/HL plus a candle close above the prior swing high. Sell only after LH/LL plus a candle close below the prior swing low.

PRICE ACTION ANALYSIS:
{analyst_result['analysis_text']}

Price-action signal: {analyst_result['overall_signal']}
Confidence: {analyst_result['confidence']:.2%}

Respond in JSON format:
{{
  "decision": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "Your brief reasoning"
}}
"""
        
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                max_tokens=200,
                temperature=0.3,  # Low temp for consistent decisions
            )
            
            response_text = response.choices[0].message.content
            
            # Parse JSON from response
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                result = self._parse_text_response(response_text)
            
            result["method"] = "LLM (Groq)"
            return result
            
        except Exception as e:
            print(f"LLM Error: {e}, falling back to rule-based decision")
            return self._simple_decision(analyst_result)
    
    def _parse_text_response(self, text: str) -> Dict:
        """Parse LLM response that might not be pure JSON"""
        decision = "HOLD"
        confidence = 0.5
        
        if "BUY" in text.upper():
            decision = "BUY"
            confidence = 0.7
        elif "SELL" in text.upper():
            decision = "SELL"
            confidence = 0.7
        
        return {
            "decision": decision,
            "confidence": confidence,
            "reasoning": text[:100]
        }


# ============================================================================
# AGENT 4: RISK MANAGER
# ============================================================================
class RiskManagerAgent:
    """Manages position sizing and risk"""
    
    def __init__(self, account_balance: float = 10000, max_risk_per_trade: float = 0.02):
        self.account_balance = account_balance
        self.max_risk_per_trade = max_risk_per_trade  # 2% per trade
    
    def calculate_position(
        self,
        decision: Dict,
        current_price: float,
        structure: Optional[Dict] = None,
        symbol: str = "EURUSD",
    ) -> Dict:
        """Calculate position size and stops based on risk management"""
        
        if decision["decision"] == "HOLD":
            return {
                "action": "HOLD",
                "quantity": 0,
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_usd": 0
            }
        
        # Position size based on risk
        max_risk_usd = self.account_balance * self.max_risk_per_trade
        
        stop_loss = self._structure_stop_loss(decision["decision"], current_price, structure)
        stop_distance = abs(current_price - stop_loss)
        if stop_distance <= 0:
            stop_distance = current_price * 0.001
            stop_loss = current_price - stop_distance if decision["decision"] == "BUY" else current_price + stop_distance
        
        if self._looks_like_forex(symbol):
            pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
            stop_distance_pips = stop_distance / pip_size
            quantity = max_risk_usd / (stop_distance_pips * 10)  # 1 pip = $10 per standard lot
            quantity_unit = "standard_lots"
        else:
            quantity = max_risk_usd / stop_distance
            quantity_unit = "units"
        
        if decision["decision"] == "BUY":
            take_profit = current_price + (stop_distance * 2)
        else:
            take_profit = current_price - (stop_distance * 2)
        
        return {
            "action": decision["decision"],
            "quantity": max(0.01, quantity),
            "entry_price": float(current_price),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "risk_usd": float(max_risk_usd),
            "quantity_unit": quantity_unit,
            "confidence": decision["confidence"]
        }

    def _structure_stop_loss(self, decision: str, current_price: float, structure: Optional[Dict]) -> float:
        if not structure:
            return current_price * 0.999 if decision == "BUY" else current_price * 1.001

        if decision == "BUY":
            swing_low = structure.get("current_trough") or {}
            stop_loss = swing_low.get("price")
            if stop_loss and stop_loss < current_price:
                return float(stop_loss)
            return current_price * 0.999

        swing_high = structure.get("current_peak") or {}
        stop_loss = swing_high.get("price")
        if stop_loss and stop_loss > current_price:
            return float(stop_loss)
        return current_price * 1.001

    @staticmethod
    def _looks_like_forex(symbol: str) -> bool:
        cleaned = symbol.replace("/", "").replace("_", "").replace("=X", "").upper()
        if cleaned in {"BTCUSD", "ETHUSD", "SOLUSD"}:
            return False
        return len(cleaned) == 6 and cleaned.isalpha()


# ============================================================================
# MAIN MULTI-AGENT SYSTEM
# ============================================================================
class MultiAgentTradingSystem:
    """Orchestrates all agents"""
    
    def __init__(self, csv_path: Optional[str] = None, groq_api_key: str = None):
        import os

        live_provider = os.environ.get("HERMES_DATA_PROVIDER", "yfinance")
        if live_provider.lower() == "csv":
            live_provider = None
        symbol = os.environ.get("HERMES_SYMBOL", "EURUSD")
        interval = os.environ.get("HERMES_INTERVAL", "1h")
        self.collector = DataCollectorAgent(csv_path, live_provider=live_provider, symbol=symbol, interval=interval)
        self.analyst = AnalystAgent()
        self.decision_maker = DecisionMakerAgent(use_groq=HAS_GROQ, api_key=groq_api_key)
        self.risk_manager = RiskManagerAgent()
    
    def make_trading_decision(self) -> Dict:
        """Execute full multi-agent pipeline"""
        
        # Agent 1: Collect data
        market_data = self.collector.get_latest_market_data()
        print(f"\n[AGENT 1] Data Collected: {market_data['price']:.5f}")
        
        # Agent 2: Analyze
        analysis = self.analyst.analyze(market_data)
        print(f"[AGENT 2] Analysis: {analysis['overall_signal']} (Confidence: {analysis['confidence']:.2%})")
        print(f"  Signals: {analysis['detailed_signals']}")
        
        # Agent 3: Decide
        decision = self.decision_maker.decide(analysis)
        print(f"[AGENT 3] Decision: {decision['decision']} ({decision['method']})")
        print(f"  Reasoning: {decision['reasoning']}")
        
        # Agent 4: Risk Management
        position = self.risk_manager.calculate_position(
            decision,
            market_data["price"],
            analysis.get("market_structure"),
            symbol=market_data.get("symbol", "EURUSD"),
        )
        print(f"[AGENT 4] Position: {position['action']}")
        if position['action'] != 'HOLD':
            print(f"  Quantity: {position['quantity']:.2f}")
            print(f"  Stop Loss: {position['stop_loss']:.5f}")
            print(f"  Take Profit: {position['take_profit']:.5f}")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "market_data": market_data,
            "analysis": analysis,
            "decision": decision,
            "position": position
        }


# ============================================================================
# DEMO
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("MULTI-AGENT TRADING SYSTEM DEMO")
    print("=" * 70)
    
    # Get API key from environment variable (more secure)
    import os
    groq_api_key = os.getenv("GROQ_API_KEY", None)
    
    # Initialize system
    system = MultiAgentTradingSystem(
        groq_api_key=groq_api_key  # Uses environment variable
    )
    
    # Make a trading decision
    result = system.make_trading_decision()
    
    print("\n" + "=" * 70)
    print("FINAL DECISION SUMMARY")
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))
