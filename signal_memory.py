import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


class SignalMemory:
    """Small JSONL feedback store for Hermes trading signals."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        signal = dict(signal)
        signal_id = signal.get("signal_id") or uuid4().hex[:12]
        signal["signal_id"] = signal_id
        signal["feedback_status"] = signal.get("feedback_status", "pending")
        self._append({"type": "signal", "signal": signal, "timestamp": datetime.now().isoformat()})
        return signal

    def record_feedback(
        self,
        signal_id: Optional[str] = None,
        outcome: str = "loss",
        reward: Optional[float] = None,
        notes: str = "",
        exit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        signal = self.find_signal(signal_id) if signal_id else self.latest_pending_signal()
        if not signal:
            return {
                "success": False,
                "error": "No matching signal found. Pass signal_id or create a signal first.",
            }

        normalized_outcome = outcome.lower()
        if reward is None:
            reward = 1.0 if normalized_outcome in {"win", "profit", "good"} else -1.0

        feedback = {
            "signal_id": signal["signal_id"],
            "symbol": signal.get("symbol"),
            "action": signal.get("action"),
            "data_provider": signal.get("data_provider"),
            "outcome": normalized_outcome,
            "reward": float(reward),
            "notes": notes,
            "exit_price": exit_price,
            "timestamp": datetime.now().isoformat(),
        }
        self._append({"type": "feedback", "feedback": feedback, "timestamp": feedback["timestamp"]})
        return {"success": True, "feedback": feedback}

    def summary(self) -> Dict[str, Any]:
        records = self._read_records()
        signals = [r["signal"] for r in records if r.get("type") == "signal"]
        feedback = [r["feedback"] for r in records if r.get("type") == "feedback"]
        feedback_by_id = {item["signal_id"]: item for item in feedback}
        pending = [s for s in signals if s.get("signal_id") not in feedback_by_id]

        groups = defaultdict(lambda: {"count": 0, "reward": 0.0, "wins": 0, "losses": 0})
        for item in feedback:
            key = f"{item.get('symbol', 'UNKNOWN')}:{item.get('action', 'UNKNOWN')}"
            group = groups[key]
            group["count"] += 1
            group["reward"] += float(item.get("reward", 0))
            if float(item.get("reward", 0)) > 0:
                group["wins"] += 1
            elif float(item.get("reward", 0)) < 0:
                group["losses"] += 1

        group_summary = {}
        for key, group in groups.items():
            avg_reward = group["reward"] / group["count"] if group["count"] else 0.0
            group_summary[key] = {
                **group,
                "avg_reward": round(avg_reward, 3),
                "win_rate_percent": round(group["wins"] / group["count"] * 100, 2)
                if group["count"]
                else 0,
            }

        total_reward = sum(float(item.get("reward", 0)) for item in feedback)
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "signals_logged": len(signals),
            "feedback_count": len(feedback),
            "pending_feedback": len(pending),
            "total_reward": round(total_reward, 3),
            "by_symbol_action": group_summary,
            "recent_pending": pending[-5:],
            "recent_feedback": feedback[-5:],
        }

    def find_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        for record in reversed(self._read_records()):
            if record.get("type") != "signal":
                continue
            signal = record.get("signal", {})
            if signal.get("signal_id") == signal_id:
                return signal
        return None

    def latest_pending_signal(self) -> Optional[Dict[str, Any]]:
        records = self._read_records()
        feedback_ids = {
            record.get("feedback", {}).get("signal_id")
            for record in records
            if record.get("type") == "feedback"
        }
        for record in reversed(records):
            if record.get("type") != "signal":
                continue
            signal = record.get("signal", {})
            if signal.get("signal_id") not in feedback_ids:
                return signal
        return None

    def _append(self, record: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    def _read_records(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records
