"""Plot ChatGPT portfolio performance against the S&P 500.

The script loads logged portfolio equity, fetches S&P 500 data, and
renders a comparison chart. Core behaviour remains unchanged; the code
is simply reorganised and commented for clarity.
"""

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

DATA_DIR = "Scripts and CSV Files"
PORTFOLIO_CSV = f"{DATA_DIR}/chatgpt_portfolio_update.csv"


def load_portfolio_totals() -> pd.DataFrame:
    """Load portfolio equity history."""
    chatgpt_df = pd.read_csv(PORTFOLIO_CSV)
    chatgpt_totals = chatgpt_df[chatgpt_df["Ticker"] == "TOTAL"].copy()
    chatgpt_totals["Date"] = pd.to_datetime(chatgpt_totals["Date"])
    return chatgpt_totals.sort_values("Date")


def download_sp500(start_date: pd.Timestamp, end_date: pd.Timestamp, baseline_equity: float) -> pd.DataFrame:
    """Download S&P 500 prices and scale to the starting equity."""
    sp500 = yf.download("^GSPC", start=start_date, end=end_date + pd.Timedelta(days=1), progress=False)
    sp500 = sp500.reset_index()
    if isinstance(sp500.columns, pd.MultiIndex):
        sp500.columns = sp500.columns.get_level_values(0)
    base_price = sp500.iloc[0]["Close"]
    scaling_factor = baseline_equity / base_price
    sp500["SPX Value"] = sp500["Close"] * scaling_factor
    return sp500


def main() -> None:
    """Generate and display the comparison graph."""
    chatgpt_totals = load_portfolio_totals()

    start_date = chatgpt_totals["Date"].min()
    end_date = chatgpt_totals["Date"].max()
    baseline_equity = float(chatgpt_totals["Total Equity"].iloc[0])
    sp500 = download_sp500(start_date, end_date, baseline_equity)

    plt.figure(figsize=(10, 6))
    plt.style.use("seaborn-v0_8-whitegrid")
    plt.plot(
        chatgpt_totals["Date"],
        chatgpt_totals["Total Equity"],
        label="ChatGPT",
        marker="o",
        color="blue",
        linewidth=2,
    )
    plt.plot(
        sp500["Date"],
        sp500["SPX Value"],
        label="S&P 500",
        marker="o",
        color="orange",
        linestyle="--",
        linewidth=2,
    )

    final_date = chatgpt_totals["Date"].iloc[-1]
    final_chatgpt = float(chatgpt_totals["Total Equity"].iloc[-1])
    final_spx = sp500["SPX Value"].iloc[-1]

    pct_chatgpt = (final_chatgpt - baseline_equity) / baseline_equity * 100
    pct_spx = (final_spx - baseline_equity) / baseline_equity * 100
    plt.text(final_date, final_chatgpt + 0.03 * baseline_equity, f"{pct_chatgpt:+.1f}%", color="blue", fontsize=9)
    plt.text(final_date, final_spx + 0.03 * baseline_equity, f"{pct_spx:+.1f}%", color="orange", fontsize=9)

    plt.title("ChatGPT's Micro Cap Portfolio vs. S&P 500")
    plt.xlabel("Date")
    plt.ylabel("Total Equity ($)")
    plt.xticks(rotation=15)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()

