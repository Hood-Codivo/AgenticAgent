"""
Standalone Telegram bot for the Hermes trading skill.

Environment:
  TELEGRAM_BOT_TOKEN       Required. Token from BotFather.
  TELEGRAM_ALLOWED_USERS   Optional comma-separated Telegram user IDs.
  TELEGRAM_USER_ID         Optional single allowed user ID fallback.
"""

import argparse
import json
import os
import shlex
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# pandas_ta can trip Numba's cache loader in some Python/package layouts before
# any bot command runs. Disabling JIT for the bot process keeps startup reliable.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")


HELP_TEXT = """Hermes Trading Bot

Commands:
/signal [SYMBOL] - Get one optimized signal
/signals [A,B,C] - Get watchlist signals
/stats - Show trading stats
/learning - Show signal feedback memory
/win [SIGNAL_ID] [notes] - Reward a signal
/loss [SIGNAL_ID] [notes] - Penalize a signal
/feedback win|loss [SIGNAL_ID] [notes] - Record feedback
/help - Show this menu
"""


class TelegramAPIError(RuntimeError):
    """Raised when Telegram returns an unsuccessful API response."""


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE or export KEY=VALUE lines without overriding env."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        try:
            parts = shlex.split(value)
            value = parts[0] if parts else ""
        except ValueError:
            value = value.strip("\"'")
        os.environ[key] = value


def load_default_env() -> None:
    load_env_file(Path.home() / ".hermes" / ".env")
    load_env_file(PROJECT_ROOT / ".env")


def allowed_users_from_env() -> Optional[set[int]]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS") or os.environ.get("TELEGRAM_USER_ID")
    if not raw:
        return None

    users = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            users.add(int(item))
        except ValueError:
            print(f"Skipping invalid Telegram user ID: {item}", file=sys.stderr)
    return users or None


def telegram_request(token: str, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    response = requests.post(url, json=payload, timeout=35)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise TelegramAPIError(data.get("description", f"Telegram {method} failed"))
    return data


def send_message(token: str, chat_id: int, text: str) -> None:
    chunks = split_message(text)
    for chunk in chunks:
        telegram_request(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
        )


def split_message(text: str, limit: int = 3900) -> List[str]:
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def get_updates(token: str, offset: Optional[int]) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {"timeout": 25, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    data = telegram_request(token, "getUpdates", payload)
    return data.get("result", [])


def parse_command(text: str) -> Tuple[str, List[str]]:
    parts = text.strip().split()
    if not parts:
        return "", []
    command = parts[0].split("@", 1)[0].lower()
    return command, parts[1:]


def handle_command(text: str) -> str:
    command, args = parse_command(text)

    if command in {"/start", "/help"}:
        return HELP_TEXT

    trading_handler = get_trading_handler()

    if command in {"/signal", "/trading_signal"}:
        kwargs = {"verbose": False}
        if args:
            kwargs["symbol"] = args[0].upper()
        return format_signal(trading_handler("signal", **kwargs))

    if command in {"/signals", "/trading_signals_watchlist"}:
        symbols = " ".join(args).strip() if args else None
        kwargs = {"verbose": False}
        if symbols:
            kwargs["symbols"] = symbols
        return format_signals(trading_handler("signals", **kwargs))

    if command in {"/stats", "/trading_stats"}:
        return format_stats(trading_handler("stats"))

    if command in {"/learning", "/trading_learning_summary"}:
        return format_learning(trading_handler("learning"))

    if command in {"/win", "/reward_signal"}:
        signal_id, notes = parse_feedback_args(args)
        return format_feedback(
            trading_handler("feedback", signal_id=signal_id, outcome="win", reward=1.0, notes=notes)
        )

    if command in {"/loss", "/penalize_signal"}:
        signal_id, notes = parse_feedback_args(args)
        return format_feedback(
            trading_handler("feedback", signal_id=signal_id, outcome="loss", reward=-1.0, notes=notes)
        )

    if command == "/feedback":
        if not args or args[0].lower() not in {"win", "loss", "profit", "good", "bad"}:
            return "Usage: /feedback win|loss [SIGNAL_ID] [notes]"
        outcome = args[0].lower()
        reward = 1.0 if outcome in {"win", "profit", "good"} else -1.0
        signal_id, notes = parse_feedback_args(args[1:])
        return format_feedback(
            trading_handler("feedback", signal_id=signal_id, outcome=outcome, reward=reward, notes=notes)
        )

    if command == "/backtest":
        return format_backtest(trading_handler("backtest"))

    return "Unknown command. Send /help to see available commands."


def get_trading_handler():
    from hermes_trading_skill_optimized import skill_handler

    return skill_handler


def parse_feedback_args(args: List[str]) -> Tuple[Optional[str], str]:
    if not args:
        return None, ""
    first = args[0]
    if len(first) == 12 and first.replace("-", "").isalnum():
        return first, " ".join(args[1:])
    return None, " ".join(args)


def format_signal(signal: Dict[str, Any]) -> str:
    if signal.get("error"):
        return f"Signal error: {signal['error']}"

    lines = [
        f"{signal.get('symbol', 'UNKNOWN')} {signal.get('action', 'HOLD')}",
        f"Signal ID: {signal.get('signal_id', 'n/a')}",
        f"Provider: {signal.get('data_provider', 'unknown')}",
        f"Confidence: {pct(signal.get('confidence'))}",
    ]

    if signal.get("quality_score") is not None:
        lines.append(f"Quality: {signal.get('quality_score')}/100")
    if signal.get("current_price") is not None:
        lines.append(f"Price: {fmt_num(signal.get('current_price'))}")
    if signal.get("filtered") is True:
        lines.append("Status: filtered / no trade")
    if signal.get("reason") or signal.get("reasoning"):
        lines.append(f"Reason: {signal.get('reason') or signal.get('reasoning')}")

    position = signal.get("position") or {}
    if position and position.get("action") != "HOLD":
        lines.extend(
            [
                "",
                "Position:",
                f"Entry: {fmt_num(position.get('entry_price'))}",
                f"Stop loss: {fmt_num(position.get('stop_loss'))}",
                f"Take profit: {fmt_num(position.get('take_profit'))}",
                f"Size: {fmt_num(position.get('quantity'))} {position.get('quantity_unit', '')}".strip(),
                f"Risk: ${fmt_num(position.get('risk_usd'))}",
            ]
        )

    market = signal.get("market_analysis") or {}
    if market:
        lines.extend(
            [
                "",
                "Market:",
                f"RSI: {fmt_num(market.get('rsi'))}",
                f"MA trend: {market.get('ma_trend', 'n/a')}",
                f"Volatility: {fmt_num(market.get('volatility'))}",
            ]
        )

    return "\n".join(lines)


def format_signals(result: Dict[str, Any]) -> str:
    if result.get("error"):
        return f"Signals error: {result['error']}"
    signals = result.get("signals", [])
    if not signals:
        return "No signals returned."
    return "\n\n".join(format_signal(signal) for signal in signals)


def format_stats(stats: Dict[str, Any]) -> str:
    if stats.get("error"):
        return f"Stats error: {stats['error']}"

    perf = stats.get("performance", stats)
    lines = ["Trading Stats"]
    for key in (
        "total_trades",
        "wins",
        "losses",
        "win_rate_percent",
        "total_pips",
        "avg_pips_per_trade",
        "latest_equity",
    ):
        if key in perf:
            lines.append(f"{title_key(key)}: {perf[key]}")

    learning = stats.get("learning")
    if learning:
        lines.extend(
            [
                "",
                "Learning:",
                f"Signals logged: {learning.get('signals_logged', 0)}",
                f"Feedback count: {learning.get('feedback_count', 0)}",
                f"Pending feedback: {learning.get('pending_feedback', 0)}",
                f"Total reward: {learning.get('total_reward', 0)}",
            ]
        )
    return "\n".join(lines)


def format_learning(summary: Dict[str, Any]) -> str:
    if summary.get("error"):
        return f"Learning error: {summary['error']}"

    lines = [
        "Learning Summary",
        f"Signals logged: {summary.get('signals_logged', 0)}",
        f"Feedback count: {summary.get('feedback_count', 0)}",
        f"Pending feedback: {summary.get('pending_feedback', 0)}",
        f"Total reward: {summary.get('total_reward', 0)}",
    ]

    pending = summary.get("recent_pending") or []
    if pending:
        lines.append("")
        lines.append("Recent pending:")
        for signal in pending[-5:]:
            lines.append(
                f"{signal.get('signal_id')} {signal.get('symbol')} {signal.get('action')} "
                f"{pct(signal.get('confidence'))}"
            )
    return "\n".join(lines)


def format_feedback(result: Dict[str, Any]) -> str:
    if not result.get("success"):
        return f"Feedback error: {result.get('error', 'Unknown error')}"
    feedback = result.get("feedback", {})
    return (
        "Feedback saved\n"
        f"Signal ID: {feedback.get('signal_id')}\n"
        f"Outcome: {feedback.get('outcome')}\n"
        f"Reward: {feedback.get('reward')}"
    )


def format_backtest(result: Dict[str, Any]) -> str:
    if not result.get("success"):
        return f"Backtest error: {result.get('error', 'Unknown error')}"
    return "\n".join(
        [
            "Backtest complete",
            f"Trades: {result.get('total_trades', 'n/a')}",
            f"Wins: {result.get('wins', 'n/a')}",
            f"Win rate: {result.get('win_rate_percent', 'n/a')}%",
            f"Total pips: {result.get('total_pips', 'n/a')}",
        ]
    )


def fmt_num(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 100:
        return f"{number:,.2f}"
    return f"{number:.5f}".rstrip("0").rstrip(".")


def pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return str(value)


def title_key(key: str) -> str:
    return key.replace("_", " ").title()


def iter_message_updates(updates: Iterable[Dict[str, Any]]) -> Iterable[Tuple[int, Dict[str, Any]]]:
    for update in updates:
        update_id = update.get("update_id")
        message = update.get("message") or {}
        if update_id is not None:
            yield update_id, message


def run_bot(token: str, allowed_users: Optional[set[int]]) -> None:
    print("Hermes Telegram bot started. Press Ctrl+C to stop.")
    if allowed_users:
        print(f"Allowed Telegram users: {', '.join(str(user) for user in sorted(allowed_users))}")
    else:
        print("Warning: TELEGRAM_ALLOWED_USERS is not set; all users can access this bot.")

    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    offset: Optional[int] = None
    while not stop:
        try:
            updates = get_updates(token, offset)
            for update_id, message in iter_message_updates(updates):
                offset = update_id + 1
                text = (message.get("text") or "").strip()
                chat = message.get("chat") or {}
                user = message.get("from") or {}
                chat_id = chat.get("id")
                user_id = user.get("id")

                if not text or chat_id is None:
                    continue
                if allowed_users is not None and user_id not in allowed_users:
                    send_message(token, chat_id, "You are not allowed to use this bot.")
                    continue

                try:
                    reply = handle_command(text)
                except Exception as exc:
                    reply = f"Command failed: {exc}"
                send_message(token, chat_id, reply)
        except requests.RequestException as exc:
            print(f"Telegram connection error: {exc}", file=sys.stderr)
            time.sleep(5)
        except TelegramAPIError as exc:
            print(f"Telegram API error: {exc}", file=sys.stderr)
            time.sleep(5)

    print("Hermes Telegram bot stopped.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Hermes trading Telegram bot.")
    parser.add_argument("--once", metavar="COMMAND", help="Run one bot command locally for testing.")
    args = parser.parse_args()

    load_default_env()

    if args.once:
        print(handle_command(args.once))
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your-telegram-bot-token":
        print(
            "TELEGRAM_BOT_TOKEN is required. Put it in ~/.hermes/.env or export it before running.",
            file=sys.stderr,
        )
        return 2

    run_bot(token, allowed_users_from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
