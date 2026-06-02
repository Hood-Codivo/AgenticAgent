import json
import os
from typing import Dict

import pandas as pd
import requests
from websockets.sync.client import connect

from price_action_data import preprocess_ohlcv_dataframe


class LiveDataError(RuntimeError):
    """Raised when a live market-data provider cannot return usable candles."""


class LiveMarketDataClient:
    """Fetch recent OHLC candles from a configured live market-data provider."""

    def __init__(self, provider: str, symbol: str = "EURUSD", interval: str = "1h"):
        self.provider = provider.lower()
        self.symbol = symbol
        self.interval = interval

    def fetch_preprocessed(self, count: int = 200):
        candles = self.fetch_ohlcv(count=count)
        return preprocess_ohlcv_dataframe(candles)

    def fetch_ohlcv(self, count: int = 200) -> pd.DataFrame:
        if self.provider in {"yfinance", "yahoo"}:
            return self._fetch_yfinance(count)
        if self.provider == "deriv":
            return self._fetch_deriv(count)
        if self.provider == "oanda":
            return self._fetch_oanda(count)
        if self.provider in {"twelvedata", "twelve_data"}:
            return self._fetch_twelvedata(count)
        raise LiveDataError(f"Unsupported live data provider: {self.provider}")

    def _fetch_yfinance(self, count: int) -> pd.DataFrame:
        import yfinance as yf

        ticker = self._yfinance_symbol(self.symbol)
        interval = self._yfinance_interval(self.interval)
        period = self._yfinance_period(interval, count)
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
        )

        if df.empty:
            raise LiveDataError(f"yfinance returned no candles for {ticker}")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(
            columns={
                "Datetime": "Gmt time",
                "Date": "Gmt time",
                "Open": "Open",
                "High": "High",
                "Low": "Low",
                "Close": "Close",
                "Volume": "Volume",
            }
        )
        df = df.reset_index()
        time_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={time_col: "Gmt time"})
        if "Volume" not in df.columns:
            df["Volume"] = 0
        return df[["Gmt time", "Open", "High", "Low", "Close", "Volume"]].tail(count)

    def _fetch_deriv(self, count: int) -> pd.DataFrame:
        symbol = self._deriv_symbol(self.symbol)
        request = {
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": "candles",
            "granularity": self._deriv_granularity(self.interval),
        }
        app_id = os.environ.get("DERIV_APP_ID", "1089")
        url = f"wss://ws.derivws.com/websockets/v3?app_id={app_id}"

        with connect(url, open_timeout=15, close_timeout=5) as websocket:
            websocket.send(json.dumps(request))
            for _ in range(5):
                payload = json.loads(websocket.recv(timeout=15))
                if payload.get("error"):
                    raise LiveDataError(payload["error"].get("message", "Deriv returned an error"))
                if payload.get("msg_type") == "candles":
                    candles = payload.get("candles", [])
                    break
            else:
                raise LiveDataError("Deriv did not return candles")

        rows = [
            {
                "Gmt time": pd.to_datetime(candle["epoch"], unit="s", utc=True),
                "Open": candle["open"],
                "High": candle["high"],
                "Low": candle["low"],
                "Close": candle["close"],
                "Volume": 0,
            }
            for candle in candles
        ]
        if not rows:
            raise LiveDataError(f"Deriv returned no candles for {symbol}")
        return pd.DataFrame(rows)

    def _fetch_oanda(self, count: int) -> pd.DataFrame:
        token = os.environ.get("OANDA_API_KEY")
        if not token:
            raise LiveDataError("OANDA_API_KEY is required for HERMES_DATA_PROVIDER=oanda")

        instrument = self._oanda_instrument(self.symbol)
        granularity = self._oanda_granularity(self.interval)
        env = os.environ.get("OANDA_ENV", "practice").lower()
        host = "api-fxtrade.oanda.com" if env == "live" else "api-fxpractice.oanda.com"
        url = f"https://{host}/v3/instruments/{instrument}/candles"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "count": count,
                "granularity": granularity,
                "price": "M",
            },
            timeout=15,
        )
        response.raise_for_status()
        candles = response.json().get("candles", [])

        rows = []
        for candle in candles:
            if not candle.get("complete", False):
                continue
            mid = candle["mid"]
            rows.append(
                {
                    "Gmt time": candle["time"],
                    "Open": mid["o"],
                    "High": mid["h"],
                    "Low": mid["l"],
                    "Close": mid["c"],
                    "Volume": candle.get("volume", 0),
                }
            )

        if not rows:
            raise LiveDataError("OANDA returned no complete candles")
        return pd.DataFrame(rows)

    def _fetch_twelvedata(self, count: int) -> pd.DataFrame:
        api_key = os.environ.get("TWELVE_DATA_API_KEY")
        if not api_key:
            raise LiveDataError("TWELVE_DATA_API_KEY is required for HERMES_DATA_PROVIDER=twelvedata")

        response = requests.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": self._twelvedata_symbol(self.symbol),
                "interval": self._twelvedata_interval(self.interval),
                "outputsize": count,
                "timezone": "UTC",
                "apikey": api_key,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise LiveDataError(payload.get("message", "Twelve Data returned an error"))

        values = payload.get("values", [])
        rows = []
        for item in reversed(values):
            rows.append(
                {
                    "Gmt time": item["datetime"],
                    "Open": item["open"],
                    "High": item["high"],
                    "Low": item["low"],
                    "Close": item["close"],
                    "Volume": item.get("volume", 0) or 0,
                }
            )

        if not rows:
            raise LiveDataError("Twelve Data returned no candles")
        return pd.DataFrame(rows)

    @staticmethod
    def _oanda_instrument(symbol: str) -> str:
        cleaned = symbol.replace("/", "").replace("_", "").upper()
        if len(cleaned) == 6:
            return f"{cleaned[:3]}_{cleaned[3:]}"
        return symbol

    @staticmethod
    def _twelvedata_symbol(symbol: str) -> str:
        cleaned = symbol.replace("_", "").replace("/", "").upper()
        if len(cleaned) == 6:
            return f"{cleaned[:3]}/{cleaned[3:]}"
        return symbol

    @staticmethod
    def _yfinance_symbol(symbol: str) -> str:
        original = symbol.strip()
        cleaned = original.replace("/", "").replace("_", "").upper()
        if original.startswith("^") or "=" in original:
            return original
        if "-" in original:
            return original.upper()
        if cleaned in {"BTCUSD", "ETHUSD", "SOLUSD"}:
            return f"{cleaned[:3]}-USD"
        if len(cleaned) == 6 and cleaned.isalpha():
            return f"{cleaned}=X"
        return original.upper()

    @staticmethod
    def _deriv_symbol(symbol: str) -> str:
        cleaned = symbol.replace("/", "").replace("_", "").upper()
        if cleaned.startswith("FRX"):
            return cleaned
        if len(cleaned) == 6 and cleaned.isalpha():
            return f"frx{cleaned}"
        return symbol

    @staticmethod
    def _oanda_granularity(interval: str) -> str:
        mapping: Dict[str, str] = {
            "1m": "M1",
            "5m": "M5",
            "15m": "M15",
            "30m": "M30",
            "1h": "H1",
            "4h": "H4",
            "1d": "D",
        }
        return mapping.get(interval.lower(), "H1")

    @staticmethod
    def _twelvedata_interval(interval: str) -> str:
        mapping: Dict[str, str] = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
            "4h": "4h",
            "1d": "1day",
        }
        return mapping.get(interval.lower(), "1h")

    @staticmethod
    def _yfinance_interval(interval: str) -> str:
        mapping: Dict[str, str] = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "4h": "1h",
            "1d": "1d",
        }
        return mapping.get(interval.lower(), "1h")

    @staticmethod
    def _yfinance_period(interval: str, count: int) -> str:
        if interval == "1m":
            return "7d"
        if interval in {"5m", "15m", "30m", "1h"}:
            return "60d"
        return "2y" if count > 250 else "1y"

    @staticmethod
    def _deriv_granularity(interval: str) -> int:
        mapping: Dict[str, int] = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return mapping.get(interval.lower(), 3600)


def live_provider_enabled() -> bool:
    return os.environ.get("HERMES_DATA_PROVIDER", "csv").lower() != "csv"
