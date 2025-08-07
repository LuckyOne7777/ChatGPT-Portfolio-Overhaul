"""Plot ChatGPT portfolio performance against the S&P 500.

The script loads logged portfolio equity, filters it to a user supplied
timeframe, normalises the values to a configurable starting capital and
compares the result against the S&P 500.  The resulting chart can be
displayed interactively or written to an image/HTML file for embedding
in a web page.
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from typing import cast

DATA_DIR = Path(__file__).resolve().parent
PORTFOLIO_CSV = DATA_DIR / "chatgpt_portfolio_update.csv"


def parse_date(date_str: str, label: str) -> pd.Timestamp:
    """Safely parse a ``YYYY-MM-DD`` string into a timestamp."""

    try:
        return pd.to_datetime(date_str)
    except ValueError as exc:  # pragma: no cover - user input validation
        msg = f"Invalid {label} '{date_str}'. Use the YYYY-MM-DD format."
        raise SystemExit(msg) from exc


def load_portfolio_details(
    baseline_equity: float,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
) -> pd.DataFrame:
    """Load and normalise portfolio equity history.

    The CSV is filtered to the requested timeframe and scaled so the first
    entry equals ``baseline_equity``.
    """

    if not PORTFOLIO_CSV.exists():
        msg = (
            f"Portfolio file '{PORTFOLIO_CSV}' not found. Run Trading_Script.py "
            "to generate it."
        )
        raise SystemExit(msg)

    chatgpt_df = pd.read_csv(PORTFOLIO_CSV)
    chatgpt_totals = chatgpt_df[chatgpt_df["Ticker"] == "TOTAL"].copy()
    chatgpt_totals["Date"] = pd.to_datetime(chatgpt_totals["Date"])
    chatgpt_totals["Total Equity"] = pd.to_numeric(
        chatgpt_totals["Total Equity"], errors="coerce"
    )

    if chatgpt_totals.empty:
        raise SystemExit("Portfolio CSV contains no TOTAL rows.")

    min_date = chatgpt_totals["Date"].min()
    max_date = chatgpt_totals["Date"].max()

    if start_date is None or start_date < min_date:
        start_date = min_date
    if end_date is None or end_date > max_date:
        end_date = max_date
    if start_date > end_date:
        raise SystemExit("Start date must be on or before end date.")

    mask = (chatgpt_totals["Date"] >= start_date) & (chatgpt_totals["Date"] <= end_date)
    chatgpt_totals = chatgpt_totals.loc[mask].copy()

    baseline_value = float(chatgpt_totals["Total Equity"].iloc[0])
    scale = baseline_equity / baseline_value
    chatgpt_totals["Total Equity"] = chatgpt_totals["Total Equity"] * scale
    chatgpt_totals.iloc[0, chatgpt_totals.columns.get_loc("Total Equity")] = baseline_equity
    return chatgpt_totals


def download_sp500(dates: pd.Series, baseline_equity: float = 100.0) -> pd.DataFrame:
    """Download S&P 500 prices and align them with ``dates``.

    Any missing benchmark values are forward filled to ensure the returned
    DataFrame has a 1:1 match with the portfolio's timeline.
    """

    start_date = dates.min()
    end_date = dates.max()
    sp500 = yf.download(
        "^SPX", start=start_date, end=end_date + pd.Timedelta(days=1), progress=False
    )
    sp500 = cast(pd.DataFrame, sp500)["Close"]

    aligned = sp500.reindex(pd.to_datetime(dates)).ffill().bfill().interpolate()
    base_price = aligned.iloc[0]
    values = aligned / base_price * baseline_equity
    return pd.DataFrame({"Date": pd.to_datetime(dates), "SPX Value": values})


def main(
    baseline_equity: float,
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
    output: Path | None,
) -> None:
    """Generate the comparison graph."""

    if baseline_equity <= 0:
        raise SystemExit("Baseline equity must be positive.")

    chatgpt_totals = load_portfolio_details(baseline_equity, start_date, end_date)
    sp500 = download_sp500(chatgpt_totals["Date"], baseline_equity)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(
        chatgpt_totals["Date"],
        chatgpt_totals["Total Equity"],
        label=f"ChatGPT (${baseline_equity:.0f} Invested)",
        marker="o",
        color="blue",
        linewidth=2,
    )
    ax.plot(
        sp500["Date"],
        sp500["SPX Value"],
        label=f"S&P 500 (${baseline_equity:.0f} Invested)",
        marker="o",
        color="orange",
        linestyle="--",
        linewidth=2,
    )

    final_date = chatgpt_totals["Date"].iloc[-1]
    final_chatgpt = float(chatgpt_totals["Total Equity"].iloc[-1])
    final_spx = float(sp500["SPX Value"].iloc[-1])

    ax.text(
        final_date,
        final_chatgpt + 0.3,
        f"+{final_chatgpt - baseline_equity:.1f}%",
        color="blue",
        fontsize=9,
    )
    ax.text(
        final_date,
        final_spx + 0.9,
        f"+{final_spx - baseline_equity:.1f}%",
        color="orange",
        fontsize=9,
    )
    ax.set_title("ChatGPT's Micro Cap Portfolio vs. S&P 500")
    ax.set_xlabel("Date")
    ax.set_ylabel(f"Value of ${baseline_equity:.0f} Investment")
    ax.legend()
    ax.grid(True)
    fig.autofmt_xdate()

    if output:
        if not output.is_absolute():
            output = DATA_DIR / output
        if output.suffix.lower() == ".html":
            try:  # pragma: no cover - optional dependency
                import mpld3
            except ModuleNotFoundError as exc:  # pragma: no cover - user environment
                msg = (
                    "mpld3 is required for HTML output. Install it with 'pip install mpld3'."
                )
                raise SystemExit(msg) from exc
            mpld3.save_html(fig, str(output))
        else:
            fig.savefig(output, bbox_inches="tight")
    else:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot portfolio performance")
    parser.add_argument(
        "--starting-capital",
        "--baseline-equity",
        dest="starting_capital",
        type=float,
        default=100.0,
        help="Starting equity value used for normalisation",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for the chart (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for the chart (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional path to save the chart (.png or .html)",
    )
    args = parser.parse_args()

    start = parse_date(args.start_date, "start date") if args.start_date else None
    end = parse_date(args.end_date, "end date") if args.end_date else None
    output = Path(args.output) if args.output else None

    main(args.starting_capital, start, end, output)

