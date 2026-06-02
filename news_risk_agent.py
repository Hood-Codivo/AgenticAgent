from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional, Set

import requests


FOREX_FACTORY_THIS_WEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


class NewsRiskAgent:
    """Blocks new trades around high-impact ForexFactory calendar events."""

    _events_cache: Dict[str, Any] = {}
    _cache_time: Dict[str, datetime] = {}

    def __init__(
        self,
        calendar_url: Optional[str] = None,
        block_before_minutes: Optional[int] = None,
        block_after_minutes: Optional[int] = None,
    ):
        self.calendar_url = calendar_url or os.environ.get(
            "FOREX_FACTORY_CALENDAR_URL",
            FOREX_FACTORY_THIS_WEEK_URL,
        )
        self.block_before_minutes = int(
            block_before_minutes
            if block_before_minutes is not None
            else os.environ.get("NEWS_BLOCK_BEFORE_MINUTES", "60")
        )
        self.block_after_minutes = int(
            block_after_minutes
            if block_after_minutes is not None
            else os.environ.get("NEWS_BLOCK_AFTER_MINUTES", "30")
        )

    def evaluate(self, symbol: str, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Return ALLOW, BLOCK, or UNAVAILABLE for the symbol's currencies."""
        now = self._aware_utc(now or datetime.now(timezone.utc))
        currencies = self._symbol_currencies(symbol)

        try:
            events = self._fetch_events()
        except Exception as exc:
            return {
                "status": "UNAVAILABLE",
                "should_block": False,
                "reason": f"News calendar unavailable: {exc}",
                "source": self.calendar_url,
                "currencies": sorted(currencies),
                "events": [],
            }

        relevant_events = []
        for event in events:
            if event.get("impact") != "High":
                continue
            country = str(event.get("country", "")).upper()
            if country not in currencies and country != "ALL":
                continue

            event_time = self._parse_event_time(event.get("date"))
            if event_time is None:
                continue

            minutes_to_event = (event_time - now).total_seconds() / 60
            in_block_window = (
                -self.block_after_minutes
                <= minutes_to_event
                <= self.block_before_minutes
            )
            event_info = {
                "title": event.get("title"),
                "currency": country,
                "impact": event.get("impact"),
                "time": event_time.isoformat(),
                "minutes_to_event": round(minutes_to_event, 1),
                "forecast": event.get("forecast", ""),
                "previous": event.get("previous", ""),
                "in_block_window": in_block_window,
            }
            relevant_events.append(event_info)

        blocking_events = [event for event in relevant_events if event["in_block_window"]]
        if blocking_events:
            return {
                "status": "BLOCK",
                "should_block": True,
                "reason": "High-impact ForexFactory event is inside the no-trade window",
                "source": self.calendar_url,
                "currencies": sorted(currencies),
                "block_before_minutes": self.block_before_minutes,
                "block_after_minutes": self.block_after_minutes,
                "events": blocking_events,
            }

        return {
            "status": "ALLOW",
            "should_block": False,
            "reason": "No high-impact ForexFactory event inside the no-trade window",
            "source": self.calendar_url,
            "currencies": sorted(currencies),
            "block_before_minutes": self.block_before_minutes,
            "block_after_minutes": self.block_after_minutes,
            "events": relevant_events[:5],
        }

    def _fetch_events(self) -> List[Dict[str, Any]]:
        cached_events = self._events_cache.get(self.calendar_url)
        cached_at = self._cache_time.get(self.calendar_url)
        if cached_events is not None and cached_at is not None:
            cache_age_seconds = (
                datetime.now(timezone.utc) - cached_at
            ).total_seconds()
            if cache_age_seconds < int(os.environ.get("NEWS_CACHE_SECONDS", "900")):
                return cached_events

        response = requests.get(
            self.calendar_url,
            headers={"User-Agent": "HermesTradingSkill/1.0"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("unexpected calendar response")
        self._events_cache[self.calendar_url] = payload
        self._cache_time[self.calendar_url] = datetime.now(timezone.utc)
        return payload

    def _symbol_currencies(self, symbol: str) -> Set[str]:
        cleaned = (
            symbol.upper()
            .replace("/", "")
            .replace("_", "")
            .replace("=X", "")
            .replace("-", "")
        )

        if cleaned.startswith("^"):
            return {"USD"}
        if cleaned in {"XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "SOLUSD"}:
            return {"USD"}
        if len(cleaned) == 6 and cleaned.isalpha():
            return {cleaned[:3], cleaned[3:]}
        if cleaned.endswith("USD"):
            return {"USD"}
        return {"USD"}

    def _parse_event_time(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return self._aware_utc(datetime.fromisoformat(str(value)))
        except ValueError:
            return None

    @staticmethod
    def _aware_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
