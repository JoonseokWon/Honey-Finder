from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import RLock

logger = logging.getLogger("honey-finder")

_TICKER_PATTERN = re.compile(r"^[A-Z0-9^][A-Z0-9.^-]{0,14}$")


def parse_tickers(value: str) -> list[str]:
    """Parse a comma or whitespace separated ticker list while preserving order."""
    tickers: list[str] = []
    invalid: list[str] = []

    for raw_ticker in re.split(r"[\s,]+", value.strip()):
        if not raw_ticker:
            continue
        ticker = raw_ticker.upper()
        if not _TICKER_PATTERN.fullmatch(ticker):
            invalid.append(raw_ticker)
            continue
        if ticker not in tickers:
            tickers.append(ticker)

    if invalid:
        raise ValueError(f"올바르지 않은 티커 형식: {', '.join(invalid)}")
    return tickers


class RuntimeSettingsStore:
    """Persist settings that can be changed while the bot is running."""

    def __init__(self, default_tickers: list[str], path: Path = Path("data/settings.json")) -> None:
        self.path = path
        self._lock = RLock()
        self._default_tickers = parse_tickers(",".join(default_tickers))
        if not self._default_tickers:
            raise ValueError("기본 후보군에는 티커가 하나 이상 필요합니다.")
        self._tickers = self._load_tickers()

    def _load_tickers(self) -> list[str]:
        if not self.path.exists():
            return self._default_tickers.copy()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw_tickers = data.get("candidate_tickers", [])
            if not isinstance(raw_tickers, list):
                raise ValueError("candidate_tickers must be a list")
            tickers = parse_tickers(",".join(str(ticker) for ticker in raw_tickers))
            if not tickers:
                raise ValueError("candidate_tickers cannot be empty")
            return tickers
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Could not load %s; using DEFAULT_TICKERS: %s", self.path, exc)
            return self._default_tickers.copy()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps({"candidate_tickers": self._tickers}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)

    def get_tickers(self) -> list[str]:
        with self._lock:
            return self._tickers.copy()

    def add_tickers(self, value: str) -> list[str]:
        additions = parse_tickers(value)
        if not additions:
            raise ValueError("추가할 티커를 하나 이상 입력하세요.")
        with self._lock:
            self._tickers.extend(ticker for ticker in additions if ticker not in self._tickers)
            self._save()
            return self._tickers.copy()

    def remove_tickers(self, value: str) -> list[str]:
        removals = parse_tickers(value)
        if not removals:
            raise ValueError("삭제할 티커를 하나 이상 입력하세요.")
        with self._lock:
            remaining = [ticker for ticker in self._tickers if ticker not in removals]
            if not remaining:
                raise ValueError("후보군을 비워둘 수 없습니다. 교체 또는 초기화를 사용하세요.")
            self._tickers = remaining
            self._save()
            return self._tickers.copy()

    def replace_tickers(self, value: str) -> list[str]:
        replacements = parse_tickers(value)
        if not replacements:
            raise ValueError("새 후보군 티커를 하나 이상 입력하세요.")
        with self._lock:
            self._tickers = replacements
            self._save()
            return self._tickers.copy()

    def reset_tickers(self) -> list[str]:
        with self._lock:
            self._tickers = self._default_tickers.copy()
            self._save()
            return self._tickers.copy()
