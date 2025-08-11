import jwt
from decimal import Decimal
from json import JSONDecodeError
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo

import sys
import types
from pathlib import Path
import pandas as pd

dummy_ts = types.ModuleType("trading_script")
dummy_ts.load_latest_portfolio_state = lambda *a, **k: ([], 0.0)
dummy_ts.process_portfolio = lambda *a, **k: None
sys.modules.setdefault("trading_script", dummy_ts)
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "portfolio_app"))

import portfolio_app.app as app_module


def _bad_download(*args, **kwargs):
    raise JSONDecodeError("bad", "", 0)


def test_get_close_price_fallback(monkeypatch):
    monkeypatch.setattr(app_module.yf, "download", _bad_download)
    now = datetime(2024, 1, 5, tzinfo=ZoneInfo("UTC"))
    price, date_str, source = app_module.get_close_price("AZTR", "force", now, buy_price=1.23)
    assert price == 1.23
    assert source == "fallback_buy"
    assert date_str == now.astimezone(app_module.US_EASTERN).date().isoformat()


def test_api_process_portfolio_force(monkeypatch):
    monkeypatch.setattr(app_module.yf, "download", _bad_download)

    class Pos:
        ticker = "AZTR"
        shares = 10
        avg_price = 1.23

    def fake_get_positions(session):
        return [Pos()]

    def fake_get_cash_balance(session):
        return Decimal("0")

    def fake_begin_tx():
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield None
        return _cm()

    monkeypatch.setattr(app_module, "begin_tx", fake_begin_tx)
    monkeypatch.setattr(app_module, "get_positions", fake_get_positions)
    monkeypatch.setattr(app_module, "get_cash_balance", fake_get_cash_balance)
    monkeypatch.setattr(app_module, "upsert_equity", lambda *a, **k: None)

    token = jwt.encode({"id": 1, "exp": datetime.now(UTC) + timedelta(hours=1)}, app_module.app.config["SECRET_KEY"], algorithm="HS256")
    client = app_module.app.test_client()
    resp = client.post("/api/process-portfolio?force=true", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["positions"][0]["price_source"] == "fallback_buy"


def test_force_uses_current_trading_day(monkeypatch):
    # Simulate data that has prices for Thursday and Friday
    df = pd.DataFrame(
        {"Close": [150.0, 200.0]},
        index=pd.DatetimeIndex(
            ["2024-01-04 21:00", "2024-01-05 21:00"], tz=ZoneInfo("UTC")
        ),
    )
    monkeypatch.setattr(app_module, "_safe_download", lambda *a, **k: df)
    now = datetime(2024, 1, 5, 21, tzinfo=ZoneInfo("UTC"))  # Friday after close
    price, date_str, source = app_module.get_close_price("NVDA", "force", now)
    assert price == 200.0
    assert date_str == "2024-01-05"
    assert source == "close"
