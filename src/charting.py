from __future__ import annotations

from pathlib import Path

import matplotlib
import yfinance as yf

from .models import AnalysisResult

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def create_price_chart(result: AnalysisResult, output_dir: Path = Path("charts")) -> Path | None:
    history = yf.Ticker(result.ticker).history(period="1y", interval="1d", auto_adjust=False)
    if history.empty:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.ticker.lower()}_chart.png"

    close = history["Close"]
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (price_ax, volume_ax) = plt.subplots(
        2,
        1,
        figsize=(11, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    price_ax.plot(close.index, close, label="Close", linewidth=1.8, color="#1f2937")
    price_ax.plot(ma50.index, ma50, label="MA50", linewidth=1.1, color="#2563eb")
    price_ax.plot(ma150.index, ma150, label="MA150", linewidth=1.1, color="#16a34a")
    price_ax.plot(ma200.index, ma200, label="MA200", linewidth=1.1, color="#dc2626")
    price_ax.set_title(f"{result.ticker} Price Trend | Score {result.score} ({result.grade})")
    price_ax.set_ylabel("Price (USD)")
    price_ax.legend(loc="upper left")

    volume_ax.bar(history.index, history["Volume"], color="#94a3b8", width=1.0)
    volume_ax.set_ylabel("Volume")
    volume_ax.set_xlabel("Date")

    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
