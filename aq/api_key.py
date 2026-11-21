import logging
import os
import tomllib

from aq.config import SECRETS_PATH

_SECRETS: set[str] = set()


def redact(text: object) -> str:
    out = str(text)
    for secret in _SECRETS:
        out = out.replace(secret, "****")
    return out


class _RedactKeyFilter(logging.Filter):
    # hide the api key if it ever ends up in a log message
    def filter(self, record: logging.LogRecord) -> bool:
        if _SECRETS:
            record.msg = redact(record.getMessage())
            record.args = None
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_RedactKeyFilter())


def env_api_key() -> str:
    """Read the key from .streamlit/secrets.toml, or from the environment."""
    try:
        with open(SECRETS_PATH, "rb") as f:
            key = str(tomllib.load(f).get("OPENAQ_API_KEY", "")).strip()
        if key:
            return key
    except (OSError, tomllib.TOMLDecodeError):
        pass
    return os.getenv("OPENAQ_API_KEY", "").strip()
