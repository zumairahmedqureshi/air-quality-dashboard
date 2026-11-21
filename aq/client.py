import time
from datetime import datetime, timezone
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from aq.api_key import _SECRETS
from aq.config import BASE_URL, MIN_SECONDS_BETWEEN_CALLS, log


class AuthError(RuntimeError):
    pass


def _parse_utc(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class OpenAQClient:
    def __init__(self, api_key: str):
        api_key = (api_key or "").strip()
        if not api_key:
            raise AuthError("API key not found. Add it to .streamlit/secrets.toml.")
        _SECRETS.add(api_key)
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": api_key, "Accept": "application/json"})
        retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self._last_call = 0.0

    def __repr__(self) -> str:
        return "OpenAQClient(api_key=****)"

    def _throttle(self) -> None:
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        self._throttle()
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=30)
        except requests.RequestException as exc:
            log.warning("Request failed for %s: %s", path, exc)
            return None

        if resp.status_code in (401, 403):
            raise AuthError(f"API key rejected ({resp.status_code}).")
        if not resp.ok:
            log.warning("HTTP %s for %s params=%s", resp.status_code, path, params)
            return None

        # wait if we are close to the rate limit
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if remaining is not None and reset is not None:
            try:
                if int(remaining) <= 1:
                    log.info("Rate limit almost reached, sleeping %ss", reset)
                    time.sleep(int(reset) + 1)
            except ValueError:
                pass
        try:
            return resp.json()
        except ValueError:
            log.warning("Bad JSON from %s", path)
            return None
