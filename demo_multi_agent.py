#!/usr/bin/env python3
"""
Multi-Agent Trading System - DEMO (Rule-Based Fallback)
This works WITHOUT an API key - uses technical analysis only
"""

import os
import json
from datetime import datetime

from multi_agent_trading import (
    DataCollectorAgent,
    AnalystAgent,
    DecisionMakerAgent,
    RiskManagerAgent,
)

def main():
    print("=" * 70)
    print("MULTI-AGENT TRADING SYSTEM - LIVE DEMO")
    print("=" * 70)
    print("\n⚠️  Running in RULE-BASED mode (no API key needed)")
    print("To enable LLM reasoning, set: export GROQ_API_KEY='your-key'\n")
    
    # Initialize agents
    collector = DataCollectorAgent("data/EURUSD_Candlestick_1_Hour_BID_01.07.2020-15.07.2023.csv")
    analyst = AnalystAgent()
    decision_maker = DecisionMakerAgent(use_groq=False)  # Force rule-based
    risk_manager = RiskManagerAgent()
    
    # ========== AGENT 1: COLLECT DATA ==========
    print("\n[AGENT 1] 📊 DATA COLLECTOR")
    print("-" * 70)
    market_data = collector.get_latest_market_data()
    print(f"Timestamp: {market_data['timestamp']}")
    print(f"Price:     {market_data['price']:.5f}")
    print(f"Volume:    {market_data['volume']:,.0f}")
    
    # ========== AGENT 2: ANALYZE ==========
    print("\n[AGENT 2] 🔍 ANALYST")
    print("-" * 70)
    analysis = analyst.analyze(market_data)
    print(f"Signal:      {analysis['overall_signal']}")
    print(f"Confidence:  {analysis['confidence']:.1%}")
    print("Signals:")
    for sig_name, sig_value in analysis['detailed_signals'].items():
        print(f"  - {sig_name}: {sig_value}")
    
    # ========== AGENT 3: DECIDE ==========
    print("\n[AGENT 3] 🤖 DECISION MAKER")
    print("-" * 70)
    decision = decision_maker.decide(analysis)
    print(f"Decision:    {decision['decision']}")
    print(f"Method:      {decision['method']}")
    print(f"Confidence:  {decision['confidence']:.1%}")
    print(f"Reasoning:   {decision['reasoning']}")
    
    # ========== AGENT 4: RISK MANAGER ==========
    print("\n[AGENT 4] 💰 RISK MANAGER")
    print("-" * 70)
    atr = market_data['indicators']['atr_14']
    position = risk_manager.calculate_position(decision, market_data['price'], atr)
    print(f"Action:      {position['action']}")
    if position['action'] != 'HOLD':
        print(f"Quantity:    {position['quantity']:.2f} lots")
        print(f"Entry:       {position['entry_price']:.5f}")
        print(f"Stop Loss:   {position['stop_loss']:.5f}")
        print(f"Take Profit: {position['take_profit']:.5f}")
        print(f"Risk:        ${position['risk_usd']:,.2f}")
    
    # ========== SUMMARY ==========
    print("\n" + "=" * 70)
    print("FINAL TRADING DECISION")
    print("=" * 70)
    
    decision_summary = {
        "timestamp": datetime.now().isoformat(),
        "market": {
            "price": market_data['price'],
            "rsi": market_data['indicators']['rsi_14'],
            "ma20": market_data['indicators']['ma_20'],
            "ma50": market_data['indicators']['ma_50'],
        },
        "analysis": analysis['overall_signal'],
        "decision": decision['decision'],
        "position": position['action'],
        "confidence": decision['confidence'],
    }
    
    print(json.dumps(decision_summary, indent=2))
    
    print("\n" + "=" * 70)
    print("HOW TO ENABLE LLM (Groq)")
    print("=" * 70)
    print("""
1. Get API key: https://console.groq.com
2. Set environment variable:
   export GROQ_API_KEY="your-api-key-here"
3. Run again to use LLM reasoning
   
Current available models:
- openai/gpt-oss-120b (recommended)
- llama-3.1-405b-reasoning (more powerful)
- gemma-2-9b-it (faster, lightweight)
""")


if __name__ == "__main__":
    main()
