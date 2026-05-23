"""
Multi-Agent Trading System
- Agent 1: Data Collector (fetches market data & indicators)
- Agent 2: Analyst Agent (analyzes data, generates signals)
- Agent 3: Decision Agent (LLM - makes final decision)
- Agent 4: Risk Manager (position sizing & execution)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple
import requests
import json
from datetime import datetime

# For LLM integration
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

from indicators import load_and_preprocess_data
from live_market_data import LiveMarketDataClient, live_provider_enabled


# ============================================================================
# AGENT 1: DATA COLLECTOR
# ============================================================================
class DataCollectorAgent:
    """Collects and preprocesses market data"""
    
    def __init__(self, csv_path: str, live_provider: str = None, symbol: str = "EURUSD", interval: str = "1h"):
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
        return load_and_preprocess_data(self.csv_path)
    
    def get_latest_market_data(self) -> Dict:
        """Return latest market data with all indicators"""
        if self.live_client:
            self.df, self.feature_cols = self._load_data()
            self.latest_row = self.df.iloc[-1]

        row = self.latest_row
        
        return {
            "timestamp": str(row.name),
            "symbol": self.symbol,
            "data_provider": self.live_provider or "csv",
            "price": float(row["Close"]),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "volume": float(row["Volume"]),
            "indicators": {
                "rsi_14": float(row["rsi_14"]) if "rsi_14" in row and not np.isnan(row["rsi_14"]) else None,
                "atr_14": float(row["atr_14"]) if "atr_14" in row and not np.isnan(row["atr_14"]) else None,
                "ma_20": float(row["ma_20"]) if "ma_20" in row and not np.isnan(row["ma_20"]) else None,
                "ma_50": float(row["ma_50"]) if "ma_50" in row and not np.isnan(row["ma_50"]) else None,
                "ma_20_slope": float(row["ma_20_slope"]) if "ma_20_slope" in row and not np.isnan(row["ma_20_slope"]) else None,
                "close_ma20_diff": float(row["close_ma20_diff"]) if "close_ma20_diff" in row and not np.isnan(row["close_ma20_diff"]) else None,
            }
        }


# ============================================================================
# AGENT 2: ANALYST AGENT
# ============================================================================
class AnalystAgent:
    """Analyzes market data and generates trading signals"""
    
    def analyze(self, market_data: Dict) -> Dict:
        """Analyze market data and return trading signal"""
        
        price = market_data["price"]
        indicators = market_data["indicators"]
        
        signals = {
            "rsi_signal": self._analyze_rsi(indicators["rsi_14"]),
            "ma_signal": self._analyze_moving_averages(
                price, 
                indicators["ma_20"], 
                indicators["ma_50"],
                indicators.get("ma_20_slope")
            ),
            "price_position": self._analyze_price_position(price, indicators["ma_20"]),
        }
        
        # Combine signals with weighted voting
        bullish_count = sum(1 for s in signals.values() if s == "BULLISH")
        bearish_count = sum(1 for s in signals.values() if s == "BEARISH")
        neutral_count = sum(1 for s in signals.values() if s == "NEUTRAL")
        
        total_signals = len(signals)
        
        if bullish_count >= bearish_count and bullish_count > 0:
            overall_signal = "BUY"
            confidence = bullish_count / total_signals
        elif bearish_count > bullish_count:
            overall_signal = "SELL"
            confidence = bearish_count / total_signals
        else:
            overall_signal = "HOLD"
            confidence = neutral_count / total_signals
        
        return {
            "overall_signal": overall_signal,
            "confidence": float(confidence),
            "detailed_signals": signals,
            "analysis_text": self._generate_analysis_text(signals, indicators, price)
        }
    
    def _analyze_rsi(self, rsi: float) -> str:
        """RSI analysis - improved thresholds"""
        if rsi is None:
            return "NEUTRAL"
        if rsi < 35:  # Strong oversold
            return "BULLISH"
        elif rsi > 65:  # Strong overbought
            return "BEARISH"
        elif rsi < 50:  # Mild oversold
            return "NEUTRAL"
        else:  # Mild overbought
            return "NEUTRAL"
    
    def _analyze_moving_averages(self, price: float, ma20: float, ma50: float, ma_slope: float = None) -> str:
        """MA crossover analysis - improved logic"""
        if ma20 is None or ma50 is None:
            return "NEUTRAL"
        
        # Check trend direction
        in_uptrend = ma20 > ma50
        in_downtrend = ma20 < ma50
        
        # Check price position relative to MA20
        above_ma20 = price > ma20
        below_ma20 = price < ma20
        
        if in_uptrend and above_ma20:
            return "BULLISH"  # Strong uptrend
        elif in_downtrend and below_ma20:
            return "BEARISH"  # Strong downtrend
        elif in_uptrend and ma_slope and ma_slope > 0:
            return "BULLISH"  # MA20 rising
        elif in_downtrend and ma_slope and ma_slope < 0:
            return "BEARISH"  # MA20 falling
        else:
            return "NEUTRAL"
    
    def _analyze_price_position(self, price: float, ma20: float) -> str:
        """Price position relative to moving average"""
        if ma20 is None:
            return "NEUTRAL"
        
        distance_pct = abs(price - ma20) / ma20 * 100
        
        if price > ma20 and distance_pct < 0.3:
            return "BULLISH"  # Price near and above MA20
        elif price < ma20 and distance_pct < 0.3:
            return "BEARISH"  # Price near and below MA20
        else:
            return "NEUTRAL"
    
    def _generate_analysis_text(self, signals: Dict, indicators: Dict, price: float) -> str:
        text = f"""
Market Analysis for {price:.5f}:
- RSI Signal: {signals['rsi_signal']} (RSI={indicators['rsi_14']:.1f})
- MA Trend: {signals['ma_signal']} (MA20={indicators['ma_20']:.5f}, MA50={indicators['ma_50']:.5f})
- Price Position: {signals['price_position']} (Distance from MA20: {abs(price - indicators['ma_20']):.6f})
"""
        return text


# ============================================================================
# AGENT 3: DECISION MAKER (LLM)
# ============================================================================
class DecisionMakerAgent:
    """Uses LLM to make final trading decision"""
    
    def __init__(self, use_groq: bool = True, api_key: str = None):
        self.use_groq = False  # Default to False
        self.api_key = api_key
        self.client = None
        
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
        
        # Trade if confidence > 0.30 (1 out of 3 signals)
        # More aggressive = more trading opportunities
        if confidence < 0.30:
            decision = "HOLD"
        else:
            decision = signal
        
        return {
            "decision": decision,
            "confidence": float(confidence),
            "reasoning": f"Signal: {signal}, Confidence: {confidence:.2%}",
            "method": "Simple Rule-Based"
        }
    
    def _llm_decision(self, analyst_result: Dict) -> Dict:
        """Use LLM to make decision"""
        
        prompt = f"""
You are a professional forex trader. Based on the technical analysis below, 
decide whether to BUY, SELL, or HOLD. Be concise and explain your reasoning.

ANALYSIS:
{analyst_result['analysis_text']}

Signal from indicators: {analyst_result['overall_signal']}
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
                model="llama-3.1-70b-versatile",  # Updated from deprecated model
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
    
    def calculate_position(self, decision: Dict, current_price: float, atr: float, symbol: str = "EURUSD") -> Dict:
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
        
        # Use ATR for stop loss
        if atr is not None:
            stop_distance = atr * 1.5  # 1.5 ATR
        else:
            stop_distance = current_price * 0.001  # 0.1%
        
        if self._looks_like_forex(symbol):
            pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
            stop_distance_pips = stop_distance / pip_size
            quantity = max_risk_usd / (stop_distance_pips * 10)  # 1 pip = $10 per standard lot
            quantity_unit = "standard_lots"
        else:
            quantity = max_risk_usd / stop_distance
            quantity_unit = "units"
        
        if decision["decision"] == "BUY":
            stop_loss = current_price - stop_distance
            take_profit = current_price + (stop_distance * 2)  # 1:2 risk/reward
        else:  # SELL
            stop_loss = current_price + stop_distance
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
    
    def __init__(self, csv_path: str, groq_api_key: str = None):
        import os

        live_provider = os.environ.get("HERMES_DATA_PROVIDER") if live_provider_enabled() else None
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
        atr = market_data["indicators"]["atr_14"]
        position = self.risk_manager.calculate_position(
            decision,
            market_data["price"],
            atr,
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
        csv_path="data/EURUSD_Candlestick_1_Hour_BID_01.07.2020-15.07.2023.csv",
        groq_api_key=groq_api_key  # Uses environment variable
    )
    
    # Make a trading decision
    result = system.make_trading_decision()
    
    print("\n" + "=" * 70)
    print("FINAL DECISION SUMMARY")
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))
