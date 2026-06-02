"""
Compatibility wrapper for the current Hermes trading skill.

The active strategy is pure price action:
- higher highs and higher lows for uptrends
- lower highs and lower lows for downtrends
- candle-close break of structure before BUY/SELL
"""

from hermes_trading_skill import TradingSkill, skill_handler


class OptimizedTradingSkill(TradingSkill):
    """Backward-compatible name for older Hermes configs."""


__all__ = ["OptimizedTradingSkill", "TradingSkill", "skill_handler"]
