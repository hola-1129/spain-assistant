from __future__ import annotations

import logging
from typing import Optional

import requests
from requests.exceptions import ConnectionError as ReqConnectionError
from requests.exceptions import Timeout as ReqTimeout
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("polymarket_intelligence.client")


class PolymarketClient:
    def __init__(self, cfg: dict) -> None:
        poly = cfg.get("polymarket", {})
        self.gamma_base = poly.get("gamma_api_base", "https://gamma-api.polymarket.com")
        self.clob_base = poly.get("clob_api_base", "https://clob.polymarket.com")
        runtime = cfg.get("runtime", {})
        self.timeout = runtime.get("request_timeout_seconds", 15)
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ReqConnectionError, ReqTimeout)),
        reraise=True,
    )
    def _get(self, url: str, params: Optional[dict] = None) -> dict | list:
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch_active_markets(self, limit: int = 500) -> list[dict]:
        try:
            data = self._get(
                f"{self.gamma_base}/markets",
                params={"active": "true", "closed": "false", "limit": limit},
            )
            if isinstance(data, list):
                return data
            return data.get("markets", [])
        except Exception as e:
            logger.error(f"fetch_active_markets failed: {e}")
            return []

    def fetch_orderbook(self, token_id: str) -> Optional[dict]:
        try:
            return self._get(f"{self.clob_base}/book", params={"token_id": token_id})
        except Exception as e:
            logger.warning(f"fetch_orderbook unavailable [token={token_id[:12]}...]: {e}")
            return None

    def fetch_market_prices(self, condition_id: str) -> Optional[dict]:
        try:
            return self._get(f"{self.clob_base}/prices", params={"condition_id": condition_id})
        except Exception as e:
            logger.warning(f"fetch_market_prices unavailable [{condition_id[:12]}...]: {e}")
            return None
