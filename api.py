# api.py — Ana API: tüm modülleri birleştirir.
import sys; sys.stdout.reconfigure(encoding="utf-8")

import asyncio, threading, time, copy, os
from datetime import datetime
from typing import List, Optional
import pandas as pd

# Railway / cloud ortamında env variable'lardan config override
def _env(key, default): return os.environ.get(key, default)
# Bu satırlar api.py başlarken config değerlerini env'den günceller
import config as _cfg
if os.environ.get("API_KEY"):         _cfg.API_KEY         = os.environ["API_KEY"]
if os.environ.get("API_SECRET"):      _cfg.API_SECRET      = os.environ["API_SECRET"]
if os.environ.get("FUTURES_API_KEY"): _cfg.FUTURES_API_KEY = os.environ["FUTURES_API_KEY"]
if os.environ.get("FUTURES_API_SECRET"): _cfg.FUTURES_API_SECRET = os.environ["FUTURES_API_SECRET"]
if os.environ.get("FUTURES_ENABLED"): _cfg.FUTURES_ENABLED = os.environ["FUTURES_ENABLED"].lower() == "true"
if os.environ.get("TELEGRAM_TOKEN"):  _cfg.TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
if os.environ.get("TELEGRAM_CHAT_ID"):_cfg.TELEGRAM_CHAT_ID= os.environ["TELEGRAM_CHAT_ID"]
if os.environ.get("TELEGRAM_ENABLED"):_cfg.TELEGRAM_ENABLED= os.environ["TELEGRAM_ENABLED"].lower() == "true"

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

import config
from connection import get_client
from data import get_ohlcv
from indicators import add_rsi, get_latest_rsi
from strategy import get_signal, SIGNAL_BUY, SIGNAL_SELL
from executor import buy, sell, check_stop_loss, get_position
from notifications import (notify_start, notify_stop, notify_buy,
                            notify_sell, notify_stop_loss, notify_take_profit, notify_error)
from backtest import run_backtest
import futures as fut

# ─── GLOBAL DURUM ────────────────────────────────────────────────────────────
def _default_pair():
    return {
        "price": 0.0, "rsi": 0.0, "signal": "HOLD",
        "position": {"active": False, "entry_price": 0.0, "quantity": 0.0, "pnl": 0.0},
        "price_history": [], "trades": [],
        "last_update": None, "error": None,
        "stats": {"total_trades": 0, "win_trades": 0, "total_pnl": 0.0,
                  "win_rate": 0.0, "best_trade": 0.0, "worst_trade": 0.0},
    }

state = {
    "running":          False,
    "balance_usdt":     0.0,
    "active_symbol":    config.SYMBOLS[0],
    "active_symbols":   config.SYMBOLS[:1],   # Başlangıçta sadece 1. çift
    "pairs":            {s: _default_pair() for s in config.SYMBOLS},
    "equity_history":   [],
    "iteration":        0,
    "last_backtest":    None,
    "backtest_running": False,

    # Ayarlar
    "rsi_period":        config.RSI_PERIOD,
    "rsi_oversold":      config.RSI_OVERSOLD,
    "rsi_overbought":    config.RSI_OVERBOUGHT,
    "take_profit_pct":   config.TAKE_PROFIT_PCT,
    "stop_loss_pct":     config.STOP_LOSS_PCT,
    "trade_amount":      config.TRADE_AMOUNT,
    "leverage":          config.LEVERAGE,
    "loop_interval":     config.LOOP_INTERVAL,   # saniye
    "futures_enabled":   fut.is_configured(),
    "telegram_enabled":  config.TELEGRAM_ENABLED,

    # Futures (aktifse)
    "futures_position":  {"active": False},
    "funding_rate":      0.0,
}

stop_event = threading.Event()
bot_thread = None
active_ws: List[WebSocket] = []
_pair_executors = {}   # symbol → {"_position": ...} (executor state izolasyonu)


# ─── YARDIMCILAR ─────────────────────────────────────────────────────────────
def _build_history(df: pd.DataFrame) -> list:
    h = []
    for idx, row in df.iterrows():
        rsi_val = float(row["rsi"]) if not pd.isna(row["rsi"]) else 50.0
        h.append({"t": idx.strftime("%H:%M"), "price": round(float(row["close"]), 2),
                   "rsi": round(rsi_val, 2), "signal": None})
    return h


def _update_balance(client) -> float:
    account = client.get_account()
    for a in account["balances"]:
        if a["asset"] == "USDT":
            state["balance_usdt"] = float(a["free"])
            return float(a["free"])
    return 0.0


def _update_stats(pair_state: dict, pnl: float):
    st = pair_state["stats"]
    st["total_trades"] += 1
    st["total_pnl"]    = round(st["total_pnl"] + pnl, 4)
    if pnl > 0:
        st["win_trades"] += 1
        st["best_trade"]  = round(max(st["best_trade"], pnl), 4)
    else:
        st["worst_trade"] = round(min(st["worst_trade"], pnl), 4)
    if st["total_trades"] > 0:
        st["win_rate"] = round(st["win_trades"] / st["total_trades"] * 100, 1)


# ─── ÇIFT İŞLEMCİSİ ──────────────────────────────────────────────────────────
def _process_pair(client, symbol: str):
    """Tek bir çifti işler. Her döngüde tüm semboller için çağrılır."""
    pair = state["pairs"][symbol]

    try:
        df    = get_ohlcv(client, symbol=symbol)
        df    = add_rsi(df, period=state["rsi_period"])
        rsi   = float(df["rsi"].iloc[-2]) if not pd.isna(df["rsi"].iloc[-2]) else 50.0
        price = float(df["close"].iloc[-2])

        # Stop-loss
        pos = get_position()
        if pos["active"] and pair.get("_watching", False):
            drop = (pos["entry_price"] - price) / pos["entry_price"]
            if drop >= state["stop_loss_pct"]:
                sell(client, symbol=symbol, reason="STOP-LOSS")
                pnl = round((price - pos["entry_price"]) * pos["quantity"], 4)
                _update_stats(pair, pnl)
                notify_stop_loss(symbol, price, drop * 100)
                pair["trades"].insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "SELL", "price": price, "rsi": round(rsi, 2),
                    "pnl": pnl, "reason": "STOP-LOSS"})
                pair["_watching"] = False

        # Take-profit
        pos = get_position()
        if pos["active"] and pair.get("_watching", False):
            gain = (price - pos["entry_price"]) / pos["entry_price"]
            if gain >= state["take_profit_pct"]:
                sell(client, symbol=symbol, reason="TAKE-PROFIT")
                pnl = round((price - pos["entry_price"]) * pos["quantity"], 4)
                _update_stats(pair, pnl)
                notify_take_profit(symbol, price, gain * 100)
                pair["trades"].insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "SELL", "price": price, "rsi": round(rsi, 2),
                    "pnl": pnl, "reason": "TAKE-PROFIT"})
                pair["_watching"] = False

        # RSI sinyali
        signal = get_signal(rsi, price)
        pos    = get_position()

        if signal == SIGNAL_BUY and not pos["active"]:
            if buy(client, symbol=symbol, usdt_amount=state["trade_amount"]):
                pair["trades"].insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "BUY", "price": price, "rsi": round(rsi, 2), "pnl": None})
                pair["_watching"] = True
                notify_buy(symbol, price, rsi, state["trade_amount"])

        elif signal == SIGNAL_SELL and pos["active"]:
            entry_p = pos["entry_price"]
            qty     = pos["quantity"]
            if sell(client, symbol=symbol, reason="RSI-SELL"):
                pnl = round((price - entry_p) * qty, 4)
                _update_stats(pair, pnl)
                pair["trades"].insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "SELL", "price": price, "rsi": round(rsi, 2),
                    "pnl": pnl, "reason": "RSI-SELL"})
                pair["_watching"] = False
                notify_sell(symbol, price, rsi, pnl, "RSI-SELL")

        pair["trades"] = pair["trades"][:50]

        # Pozisyon PnL
        pos  = get_position()
        pnl  = round((price - pos["entry_price"]) * pos["quantity"], 4) if pos["active"] else 0.0

        # Price history
        new_hist = _build_history(df)
        if new_hist: new_hist[-1]["signal"] = signal
        pair["price_history"] = new_hist

        # Pair state güncelle
        pair.update({
            "price": price, "rsi": round(rsi, 2), "signal": signal,
            "position": {**pos, "pnl": pnl},
            "last_update": datetime.now().strftime("%H:%M:%S"),
            "error": None,
        })

    except Exception as e:
        pair["error"] = str(e)
        notify_error(symbol, str(e))


# ─── BOT DÖNGÜSÜ ─────────────────────────────────────────────────────────────
def bot_loop():
    client = get_client()

    # İlk yükleme
    try:
        _update_balance(client)
        for s in state["active_symbols"]:
            df = get_ohlcv(client, symbol=s)
            df = add_rsi(df, period=state["rsi_period"])
            state["pairs"][s]["price_history"] = _build_history(df)
        state["equity_history"].append({
            "t": datetime.now().strftime("%H:%M"),
            "balance": state["balance_usdt"]})
    except Exception as e:
        print(f"[Başlangıç HATA] {e}")

    notify_start(state["active_symbols"])

    while not stop_event.is_set():
        state["iteration"] += 1
        _update_balance(client)

        for symbol in list(state["active_symbols"]):
            _process_pair(client, symbol)

        # Futures pozisyon güncelle
        if state["futures_enabled"]:
            try:
                fc = fut.get_futures_client()
                state["futures_position"] = fut.get_position_info(
                    fc, state["active_symbol"])
                state["funding_rate"] = fut.get_funding_rate(
                    fc, state["active_symbol"])
            except Exception:
                pass

        state["equity_history"].append({
            "t": datetime.now().strftime("%H:%M"),
            "balance": state["balance_usdt"]})
        state["equity_history"] = state["equity_history"][-200:]

        # Ayarlanabilir bekleme süresi (1'er saniyelik adımlarla kontrol eder)
        for _ in range(state["loop_interval"]):
            if stop_event.is_set(): break
            time.sleep(1)

    state["running"] = False
    notify_stop()


# ─── FASTAPI ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Trading Bot API v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/status")
def get_status():
    # Aktif çiftin verilerini üst seviyeye taşı (dashboard uyumluluğu)
    sym   = state["active_symbol"]
    pair  = state["pairs"].get(sym, _default_pair())
    return {**state, **pair, "symbol": sym}


@app.post("/start")
def start_bot():
    global bot_thread
    if state["running"]:
        return {"ok": False, "message": "Zaten çalışıyor"}
    stop_event.clear()
    state["running"] = True
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    return {"ok": True}


@app.post("/stop")
def stop_bot():
    stop_event.set()
    state["running"] = False
    return {"ok": True}


@app.post("/symbol")
def set_symbol(symbol: str):
    """Aktif çifti değiştir."""
    if symbol in state["pairs"]:
        state["active_symbol"] = symbol
    return {"ok": True, "active_symbol": state["active_symbol"]}


@app.post("/symbols/add")
def add_symbol(symbol: str):
    """Yeni çift ekle."""
    if symbol not in state["pairs"]:
        state["pairs"][symbol] = _default_pair()
    if symbol not in state["active_symbols"]:
        state["active_symbols"].append(symbol)
    return {"ok": True, "active_symbols": state["active_symbols"]}


@app.post("/symbols/remove")
def remove_symbol(symbol: str):
    """Çifti kaldır (ana çift kaldırılamaz)."""
    if symbol == state["active_symbols"][0]:
        return {"ok": False, "message": "Ana çift kaldırılamaz"}
    if symbol in state["active_symbols"]:
        state["active_symbols"].remove(symbol)
    return {"ok": True}


@app.post("/settings")
def update_settings(
    rsi_period:      Optional[int]   = None,
    rsi_oversold:    Optional[float] = None,
    rsi_overbought:  Optional[float] = None,
    take_profit_pct: Optional[float] = None,
    stop_loss_pct:   Optional[float] = None,
    trade_amount:    Optional[float] = None,
    leverage:        Optional[int]   = None,
    loop_interval:   Optional[int]   = None,
):
    """Dashboard'dan risk parametrelerini günceller."""
    if rsi_period      is not None: state["rsi_period"]      = int(max(5, min(50, rsi_period)))
    if rsi_oversold    is not None: state["rsi_oversold"]    = max(10, min(45, rsi_oversold))
    if rsi_overbought  is not None: state["rsi_overbought"]  = max(55, min(90, rsi_overbought))
    if take_profit_pct is not None: state["take_profit_pct"] = max(0.005, min(0.20, take_profit_pct))
    if stop_loss_pct   is not None: state["stop_loss_pct"]   = max(0.005, min(0.20, stop_loss_pct))
    if trade_amount    is not None: state["trade_amount"]    = max(1.0, trade_amount)
    if leverage        is not None: state["leverage"]        = int(max(1, min(20, leverage)))
    if loop_interval   is not None: state["loop_interval"]   = int(max(5, min(300, loop_interval)))
    return {"ok": True, **{k: state[k] for k in
        ["rsi_period","rsi_oversold","rsi_overbought",
         "take_profit_pct","stop_loss_pct","trade_amount","leverage","loop_interval"]}}


@app.post("/backtest")
async def backtest_endpoint(
    background_tasks: BackgroundTasks,
    symbol:           str   = "BTCUSDT",
    days:             int   = 30,
    interval:         str   = "1h",
):
    """Backtest'i arka planda çalıştırır."""
    if state["backtest_running"]:
        return {"ok": False, "message": "Backtest zaten çalışıyor"}

    def _run():
        state["backtest_running"] = True
        try:
            state["last_backtest"] = run_backtest(
                symbol=symbol, interval=interval, days=days,
                rsi_period=state["rsi_period"],
                rsi_oversold=state["rsi_oversold"],
                rsi_overbought=state["rsi_overbought"],
                stop_loss_pct=state["stop_loss_pct"],
                take_profit_pct=state["take_profit_pct"],
                trade_amount=state["trade_amount"],
            )
        except Exception as e:
            state["last_backtest"] = {"error": str(e)}
        finally:
            state["backtest_running"] = False

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Backtest başlatıldı"}


@app.get("/backtest/result")
def backtest_result():
    return {
        "running": state["backtest_running"],
        "result":  state["last_backtest"],
    }


# Futures endpoints
@app.post("/futures/long")
def futures_long(symbol: str = "BTCUSDT", usdt: float = 10.0):
    if not state["futures_enabled"]:
        return {"ok": False, "error": "Futures aktif değil"}
    fc = fut.get_futures_client()
    return fut.open_long(fc, symbol, usdt, state["leverage"])


@app.post("/futures/short")
def futures_short(symbol: str = "BTCUSDT", usdt: float = 10.0):
    if not state["futures_enabled"]:
        return {"ok": False, "error": "Futures aktif değil"}
    fc = fut.get_futures_client()
    return fut.open_short(fc, symbol, usdt, state["leverage"])


@app.post("/futures/close")
def futures_close(symbol: str = "BTCUSDT"):
    if not state["futures_enabled"]:
        return {"ok": False, "error": "Futures aktif değil"}
    fc = fut.get_futures_client()
    return fut.close_position(fc, symbol)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_ws.append(websocket)
    try:
        while True:
            sym  = state["active_symbol"]
            pair = state["pairs"].get(sym, _default_pair())
            payload = {**state, **pair, "symbol": sym}
            await websocket.send_json(payload)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_ws:
            active_ws.remove(websocket)


if __name__ == "__main__":
    print("[OK] API: http://localhost:8000  |  Dashboard: http://localhost:3000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
