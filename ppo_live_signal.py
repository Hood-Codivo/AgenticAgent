from pathlib import Path
from typing import Any, Dict

import numpy as np
import torch
from stable_baselines3 import PPO

from trading_env import ForexTradingEnv


SL_OPTS = [5, 10, 15, 25, 30, 60, 90, 120]
TP_OPTS = [5, 10, 15, 25, 30, 60, 90, 120]
WINDOW_SIZE = 30


class PPOLiveSignalGenerator:
    """Run the trained PPO model on the latest preprocessed candle window."""

    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.model = PPO.load(str(self.model_path))

    def predict(self, df, feature_cols, symbol: str = "EURUSD") -> Dict[str, Any]:
        env = ForexTradingEnv(
            df=df,
            window_size=WINDOW_SIZE,
            sl_options=SL_OPTS,
            tp_options=TP_OPTS,
            spread_pips=1.0,
            commission_pips=0.0,
            max_slippage_pips=0.0,
            random_start=False,
            episode_max_steps=None,
            feature_columns=feature_cols,
            hold_reward_weight=0.00,
            open_penalty_pips=0.0,
            time_penalty_pips=0.0,
            unrealized_delta_weight=0.0,
        )
        env.reset()
        env.current_step = env.n_steps - 1
        env.position = 0
        env.entry_price = None
        env.sl_price = None
        env.tp_price = None
        env.time_in_trade = 0
        env.prev_unrealized_pips = 0.0

        obs = env._get_observation()
        action, _ = self.model.predict(obs, deterministic=True)
        action_int = int(np.asarray(action).item())
        action_prob, direction_probs = self._probabilities(obs, env.action_map, action_int)
        act_type, direction, sl_pips, tp_pips = env.action_map[action_int]

        price = float(df.iloc[-1]["Close"])
        pip_size = 0.01 if "JPY" in symbol.upper() else 0.0001
        decoded = self._decode_action(
            act_type=act_type,
            direction=direction,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            price=price,
            pip_size=pip_size,
        )
        decoded.update(
            {
                "model_action_index": action_int,
                "model_action_probability": action_prob,
                "model_confidence": direction_probs.get(decoded["decision"], action_prob),
                "direction_probabilities": direction_probs,
                "model_path": str(self.model_path),
                "trained_for": "EURUSD-like forex, 1h candles",
            }
        )
        return decoded

    def _probabilities(self, obs: np.ndarray, action_map, action_int: int):
        with torch.no_grad():
            obs_tensor, _ = self.model.policy.obs_to_tensor(obs)
            distribution = self.model.policy.get_distribution(obs_tensor)
            probs = distribution.distribution.probs.detach().cpu().numpy()[0]

        direction_probs = {"HOLD": 0.0, "BUY": 0.0, "SELL": 0.0}
        for idx, (act_type, direction, _, _) in enumerate(action_map):
            if act_type in {"HOLD", "CLOSE"}:
                direction_probs["HOLD"] += float(probs[idx])
            elif direction == 1:
                direction_probs["BUY"] += float(probs[idx])
            else:
                direction_probs["SELL"] += float(probs[idx])

        return float(probs[action_int]), direction_probs

    @staticmethod
    def _decode_action(
        act_type: str,
        direction,
        sl_pips,
        tp_pips,
        price: float,
        pip_size: float,
    ) -> Dict[str, Any]:
        if act_type in {"HOLD", "CLOSE"}:
            return {
                "decision": "HOLD",
                "reasoning": f"PPO model selected {act_type}",
                "sl_pips": None,
                "tp_pips": None,
                "stop_loss": None,
                "take_profit": None,
            }

        decision = "BUY" if direction == 1 else "SELL"
        sl_distance = float(sl_pips) * pip_size
        tp_distance = float(tp_pips) * pip_size

        if decision == "BUY":
            stop_loss = price - sl_distance
            take_profit = price + tp_distance
        else:
            stop_loss = price + sl_distance
            take_profit = price - tp_distance

        return {
            "decision": decision,
            "reasoning": f"PPO model selected {decision} with SL={sl_pips:g} pips and TP={tp_pips:g} pips",
            "sl_pips": float(sl_pips),
            "tp_pips": float(tp_pips),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
        }
