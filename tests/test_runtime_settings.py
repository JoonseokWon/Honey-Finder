from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from src.runtime_settings import RuntimeSettingsStore, parse_tickers


class ParseTickersTest(TestCase):
    def test_normalizes_deduplicates_and_preserves_order(self) -> None:
        self.assertEqual(parse_tickers(" nvda, AAPL nvda "), ["NVDA", "AAPL"])

    def test_rejects_invalid_ticker(self) -> None:
        with self.assertRaises(ValueError):
            parse_tickers("NVDA,not/a/ticker")


class RuntimeSettingsStoreTest(TestCase):
    def test_changes_are_persisted_and_reloaded(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = RuntimeSettingsStore(["NVDA", "AAPL"], path)

            self.assertEqual(store.add_tickers("MSFT, NVDA"), ["NVDA", "AAPL", "MSFT"])
            self.assertEqual(store.remove_tickers("AAPL"), ["NVDA", "MSFT"])
            self.assertEqual(RuntimeSettingsStore(["TSLA"], path).get_tickers(), ["NVDA", "MSFT"])

    def test_reset_uses_environment_defaults(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = RuntimeSettingsStore(["NVDA", "AAPL"], path)
            store.replace_tickers("MSFT")

            self.assertEqual(store.reset_tickers(), ["NVDA", "AAPL"])

    def test_candidate_universe_cannot_be_empty(self) -> None:
        with TemporaryDirectory() as directory:
            store = RuntimeSettingsStore(["NVDA"], Path(directory) / "settings.json")

            with self.assertRaises(ValueError):
                store.remove_tickers("NVDA")
