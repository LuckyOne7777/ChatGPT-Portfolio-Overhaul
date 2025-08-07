"""Wrapper for the shared trading script using local data directory."""

from pathlib import Path
import sys

# Allow importing the shared module from the repository root
sys.path.append(str(Path(__file__).resolve().parents[1]))

from trading_script import main

script_dir = Path(__file__).resolve().parent
csv_file = script_dir / "chatgpt_portfolio_update.csv"
main(str(csv_file), script_dir)


if __name__ == "__main__":

    data_dir = Path(__file__).resolve().parent
    main(str(csv_file), script_dir)


