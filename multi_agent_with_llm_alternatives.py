"""
Enhanced Multi-Agent System with Multiple LLM Options
Supports: Groq, OpenRouter, Local Ollama
"""

import json
import os
import requests
from typing import Dict, Optional


class LLMDecisionMaker:
    """Unified LLM interface for multiple providers"""
    
    def __init__(self, provider: str = "groq", api_key: str = None):
        """
        provider: "groq", "openrouter", "ollama"
        api_key: Your API key (required for groq/openrouter)
        """
        self.provider = provider.lower()
        self.api_key = api_key
        
        if self.provider == "groq":
            try:
                from groq import Groq
                self.client = Groq(api_key=api_key)
                print("✓ Groq initialized")
            except ImportError:
                print("✗ Groq not installed. Install: pip install groq")
        
        elif self.provider == "openrouter":
            print("✓ OpenRouter initialized")
        
        elif self.provider == "ollama":
            print("✓ Ollama (local) initialized")
    
    def make_decision(self, analysis: Dict) -> Dict:
        """Route to appropriate LLM provider"""
        
        if self.provider == "groq":
            return self._groq_decision(analysis)
        elif self.provider == "openrouter":
            return self._openrouter_decision(analysis)
        elif self.provider == "ollama":
            return self._ollama_decision(analysis)
        else:
            return {"error": f"Unknown provider: {self.provider}"}
    
    def _groq_decision(self, analysis: Dict) -> Dict:
        """Groq LLM decision"""
        
        prompt = f"""You are a professional forex trader AI.

Technical Analysis:
{analysis['analysis_text']}

Current Signal: {analysis['overall_signal']}
Confidence: {analysis['confidence']:.2%}

Make a TRADING DECISION. Response format:
{{
  "decision": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "Brief 1-sentence reason"
}}

Be strict. Only recommend BUY/SELL if high conviction."""
        
        try:
            response = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="openai/gpt-oss-120b",
                max_tokens=150,
                temperature=0.1,
            )
            
            text = response.choices[0].message.content
            result = json.loads(text)
            result["provider"] = "Groq (Llama-3.1-70b)"
            return result
        except Exception as e:
            return {"error": str(e), "provider": "Groq"}
    
    def _openrouter_decision(self, analysis: Dict) -> Dict:
        """OpenRouter LLM decision (supports Claude, Llama, etc)"""
        
        prompt = f"""You are a professional forex trader AI.

Technical Analysis:
{analysis['analysis_text']}

Current Signal: {analysis['overall_signal']}
Confidence: {analysis['confidence']:.2%}

Make a TRADING DECISION. Response format:
{{
  "decision": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "Brief 1-sentence reason"
}}"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/yourusername/trading-agent",
            "X-Title": "Forex Trading Agent",
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": "anthropic/claude-3.5-sonnet",  # Fast & cheap
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 150,
                }
            )
            
            text = response.json()["choices"][0]["message"]["content"]
            result = json.loads(text)
            result["provider"] = "OpenRouter (Claude 3.5 Sonnet)"
            return result
        except Exception as e:
            return {"error": str(e), "provider": "OpenRouter"}
    
    def _ollama_decision(self, analysis: Dict) -> Dict:
        """Local Ollama LLM decision (free, private)"""
        
        prompt = f"""You are a professional forex trader.

Analysis: {analysis['overall_signal']}
Confidence: {analysis['confidence']:.2%}

Decision (BUY/SELL/HOLD)?"""
        
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False,
                }
            )
            
            text = response.json()["response"]
            
            if "BUY" in text.upper():
                decision = "BUY"
            elif "SELL" in text.upper():
                decision = "SELL"
            else:
                decision = "HOLD"
            
            return {
                "decision": decision,
                "confidence": 0.6,
                "reasoning": text[:100],
                "provider": "Ollama (Mistral - Local)"
            }
        except Exception as e:
            return {"error": str(e), "provider": "Ollama"}


# ============================================================================
# COSTS & COMPARISON
# ============================================================================
"""
LLM PROVIDER COMPARISON:

1. GROQ (Recommended for speed)
   - Cost: FREE tier (600 calls/min, limited)
   - Speed: ~100ms per decision
   - Model: Mixtral-8x7b
   - Best for: High-frequency trading
   
2. OPENROUTER (Best model access)
   - Cost: $0.003 per 1K tokens (Claude) = ~$0.01 per trade
   - Speed: ~500ms
   - Models: Claude, Llama, GPT-4
   - Best for: High accuracy needed
   
3. OLLAMA (Free & Private)
   - Cost: FREE (runs locally)
   - Speed: ~2-5s (depends on GPU)
   - Models: Mistral, Llama, Neural Chat
   - Best for: Privacy, no API costs
   
4. CURRENT RL MODEL (Baseline)
   - Cost: FREE
   - Speed: ~10ms
   - Models: PPO neural network
   - Best for: Speed, no API dependency

RECOMMENDATION:
- Use Groq for free tier trading
- Use OpenRouter if you need Claude's reasoning
- Use Ollama for maximum privacy
- Use RL model as fallback/backup
"""


# ============================================================================
# EXAMPLE: HYBRID APPROACH (RL + LLM)
# ============================================================================
class HybridTradingDecision:
    """Combines RL model + LLM for best-of-both-worlds"""
    
    def __init__(self, rl_model, llm_provider: str = "groq", api_key: str = None):
        self.rl_model = rl_model
        self.llm = LLMDecisionMaker(provider=llm_provider, api_key=api_key)
    
    def decide(self, market_data: Dict, analysis: Dict) -> Dict:
        """Get decisions from both RL and LLM, then vote"""
        
        # Get RL decision
        rl_decision = self.rl_model.predict(market_data)[0]
        rl_actions = {0: "HOLD", 1: "BUY", 2: "SELL"}
        rl_action = rl_actions.get(rl_decision, "HOLD")
        
        # Get LLM decision
        llm_result = self.llm.make_decision(analysis)
        llm_action = llm_result.get("decision", "HOLD")
        
        # Vote
        if rl_action == llm_action:
            # Both agree
            final_decision = rl_action
            confidence = 0.95
            reason = f"Agreement: RL ({rl_action}) + LLM ({llm_action})"
        else:
            # Disagreement - prefer LLM for reasoning, RL for speed
            final_decision = llm_action
            confidence = 0.7
            reason = f"LLM ({llm_action}) overrides RL ({rl_action})"
        
        return {
            "final_decision": final_decision,
            "confidence": confidence,
            "rl_decision": rl_action,
            "llm_decision": llm_action,
            "reasoning": reason,
            "llm_provider": llm_result.get("provider", "Unknown")
        }


if __name__ == "__main__":
    # Example usage
    print("=" * 70)
    print("LLM DECISION MAKERS - SETUP GUIDE")
    print("=" * 70)
    
    print("""
OPTION 1: GROQ (Recommended)
--------------------------------
1. Get free API key: https://console.groq.com
2. Install: pip install groq
3. Use: 
   llm = LLMDecisionMaker("groq", api_key="your-key")
   
OPTION 2: OPENROUTER
--------------------------------
1. Get API key: https://openrouter.ai
2. Use:
   llm = LLMDecisionMaker("openrouter", api_key="your-key")
   
OPTION 3: OLLAMA (Local & Free)
--------------------------------
1. Install: https://ollama.ai
2. Run: ollama run mistral
3. Use:
   llm = LLMDecisionMaker("ollama")
""")
