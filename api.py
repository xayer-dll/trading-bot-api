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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from connection import get_client
from data import get_ohlcv
from indicators import (add_rsi, add_all_indicators, get_latest_rsi, get_latest_macd,
                        get_latest_bollinger, get_latest_trend, get_latest_atr, get_latest_volume)
from strategy import get_signal, SIGNAL_BUY, SIGNAL_SELL, SIGNAL_STRONG_BUY, SIGNAL_STRONG_SELL
from executor import buy, sell, check_stop_loss, get_position, load_positions_from_db
from notifications import (notify_start, notify_stop, notify_buy,
                            notify_sell, notify_stop_loss, notify_take_profit, notify_error)
from backtest import run_backtest
import futures as fut
from polymarket import PolymarketBot, PolymarketClient
from news_analyzer import NewsAnalyzer
from snowball import SnowballEngine
from database import init_db, save_trade, save_stats, save_equity, load_trades, load_stats, load_equity, get_db_summary
from auditor import TradeAuditor
from learner import TradeLearner

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
    "balance_usdt":     0.0,    # Serbest USDT (coine donusmemis)
    "equity_usdt":      0.0,    # GERCEK portfoy = serbest USDT + acik pozisyon degeri
    "active_symbol":    config.SYMBOLS[0],
    "active_symbols":   list(config.SYMBOLS),   # Tum ciftler aktif: BTC, ETH, SOL
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

    # Polymarket tahmin pazarları
    "polymarket_enabled": True,
    "polymarket_markets": [],
    "polymarket_positions": {},

    # Haber sentiment analizi
    "news_sentiment": 0.5,  # -1 to +1 (0.5 = neutral)
    "news_headlines": [],
    "news_last_update": None,
}

stop_event = threading.Event()
bot_thread = None
active_ws: List[WebSocket] = []
_pair_executors = {}   # symbol → {"_position": ...} (executor state izolasyonu)
polymarket_bot: Optional[PolymarketBot] = None
news_analyzer: Optional[NewsAnalyzer] = None
snowball: Optional[SnowballEngine] = None
auditor: Optional[TradeAuditor] = None
learner: Optional[TradeLearner] = None

# SQLite veritabanini baslat
init_db()


# ─── POLYMARKET YARDIMCILARı ────────────────────────────────────────────────────
async def _init_polymarket():
    """Polymarket bot'u başlat."""
    global polymarket_bot
    try:
        polymarket_bot = PolymarketBot()
        await polymarket_bot.initialize()

        # Crypto pazarlarını bul ve cache'le
        markets = await polymarket_bot.find_crypto_prediction_markets()
        state["polymarket_markets"] = [
            {
                "id": m.get("id"),
                "title": m.get("title"),
                "volume": m.get("volume"),
                "liquidity": m.get("liquidity")
            }
            for m in markets
        ]
        print(f"[POLY] {len(state['polymarket_markets'])} tahmin pazarı bulundu")
        return True
    except Exception as e:
        print(f"[POLY HATA] Başlama hatası: {e}")
        state["polymarket_enabled"] = False
        return False


async def _update_news_sentiment():
    """Haber sentiment'ini güncelle (her 5 dakika)."""
    global news_analyzer
    if not news_analyzer:
        return

    try:
        sentiment_data = await news_analyzer.get_latest_sentiment(hours=24)

        # Sentiment skoru normalize et (-1 to +1)
        # very_bullish: +0.9, bullish: +0.6, neutral: 0, bearish: -0.6, very_bearish: -0.9
        sentiment_map = {
            "very_bullish": 0.9,
            "bullish": 0.6,
            "neutral": 0.0,
            "bearish": -0.6,
            "very_bearish": -0.9,
        }

        sentiment_score = sentiment_map.get(sentiment_data["sentiment"], 0.0)
        state["news_sentiment"] = sentiment_score
        state["news_headlines"] = sentiment_data.get("top_headlines", [])
        state["news_last_update"] = datetime.now().strftime("%H:%M:%S")

        print(
            f"[NEWS] Sentiment: {sentiment_data['sentiment']} "
            f"({sentiment_data['count']} haber, "
            f"{sentiment_data['bullish_count']} bullish, "
            f"{sentiment_data['bearish_count']} bearish)"
        )
    except Exception as e:
        print(f"[NEWS] Update hatası: {e}")


async def _process_polymarket_signal(symbol: str, rsi: float, signal: str):
    """RSI + Haber Sentiment ile Polymarket'e işlem yap."""
    if not polymarket_bot or not state["polymarket_markets"]:
        return

    try:
        # İlk crypto pazarına işlem yap
        if state["polymarket_markets"]:
            market = state["polymarket_markets"][0]
            market_id = market.get("id")

            # Haber sentiment'ini ekle
            result = await polymarket_bot.execute_trade(
                market_id=market_id,
                rsi=rsi,
                symbol=symbol,
                news_sentiment=state["news_sentiment"]  # -1 to +1
            )

            if result.get("success"):
                print(
                    f"[POLY] {symbol} | RSI={rsi:.1f} + News={state['news_sentiment']:+.2f} "
                    f"→ {result['side']} ({result['final_confidence']:.0%})"
                )
                state["polymarket_positions"][market_id] = result
            else:
                print(f"[POLY] Hata: {result.get('error', 'Bilinmeyen')}")
    except Exception as e:
        print(f"[POLY] İşlem hatası: {e}")


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


def _compute_equity() -> float:
    """
    GERCEK portfoy degeri = serbest USDT + acik pozisyonlardaki coinlerin degeri.

    Neden lazim? Bot spot coin alinca serbest USDT duser ama para kaybolmaz —
    coine donusur. Sadece serbest USDT'ye bakmak yaniltici. Toplam deger sabit
    kalmali (komisyon/kar haric).
    """
    free = state["balance_usdt"]
    holdings = 0.0
    for sym in list(state["active_symbols"]):
        pos = get_position(sym)
        if pos.get("active"):
            # Eldeki coin degeri = miktar x guncel fiyat
            price = state["pairs"].get(sym, {}).get("price", 0) or pos["entry_price"]
            holdings += pos["quantity"] * price
    return round(free + holdings, 2)


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
def _handle_sell(client, symbol: str, pair: dict, price: float, rsi: float, reason: str):
    """Ortak satis islemi: snowball + kaldirac + denetim + ogrenme + db + bildirim."""
    pos = get_position(symbol)
    entry_p = pos["entry_price"]
    qty = pos["quantity"]
    margin_used = pos.get("margin_used", state.get("trade_amount", 10))  # BUG FIX #2: Alis anindaki gercek marjin

    sell_result = sell(client, symbol=symbol, reason=reason)
    if sell_result.get("ok"):
        # BUG FIX #3: Gercek execution fiyatini kullan (candle close degil)
        exec_price = sell_result.get("exec_price", price)

        # ─── DURUST SPOT PnL (kaldirac YOK, komisyon DAHIL) ──────────────
        # ESKI BUG: pnl = spot_pnl x 5 (sahte kaldirac, $19k bug'inin kardesi)
        # SIMDI: gercek spot kar - alis/satis komisyonu
        gross_pnl = (exec_price - entry_p) * qty
        fee = (entry_p * qty + exec_price * qty) * config.FEE_RATE  # gidis+donus komisyon
        pnl = round(gross_pnl - fee, 4)

        _update_stats(pair, pnl)

        # SNOWBALL: Kaldiracli PnL kaydet
        if snowball:
            snowball.record_trade(pnl, symbol, margin_used=margin_used)
            state["trade_amount"] = snowball.calculate_trade_amount()

        # AUDITOR: Islemi denetle (her 5 islemde otomatik tarama)
        if auditor:
            audit_result = auditor.add_trade({
                "symbol": symbol,
                "action": "SELL",
                "entry_price": entry_p,
                "exit_price": exec_price,  # BUG FIX #3: Gercek execution fiyati
                "quantity": qty,
                "pnl": pnl,
                "fee": round(fee, 4),      # Komisyon (auditor PnL dogrulamasi icin)
                "margin": margin_used,     # BUG FIX #2: Gercek marjin
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            })
            if audit_result and audit_result.get("issues"):
                print(f"[AUDIT] {symbol} ANOMALI: {len(audit_result['issues'])} sorun!")
                for issue in audit_result.get("issues", []):
                    if isinstance(issue, dict):
                        print(f"  [!] {issue.get('message', str(issue))}")
                    else:
                        print(f"  [!] {issue}")

        # LEARNER: Islemden ders cikar
        if learner:
            macd_data = pair.get("macd", {})
            learner.record_trade({
                "symbol": symbol,
                "action": "SELL",
                "entry_price": entry_p,
                "exit_price": exec_price,  # BUG FIX #3: Gercek execution fiyati
                "pnl": pnl,
                "rsi_at_entry": pair.get("_entry_rsi", 50),
                "rsi_at_exit": rsi,
                "macd_bullish": macd_data.get("bullish"),
                "signal_type": pair.get("_entry_signal", "BUY"),
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
            })

        # DATABASE: Islemi kaydet (gercek execution fiyatiyla)
        save_trade(symbol, "SELL", exec_price, rsi, pnl=pnl, reason=reason)
        save_stats(symbol, pair["stats"])

        pair["trades"].insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "action": "SELL", "price": exec_price, "rsi": round(rsi, 2),
            "pnl": pnl, "reason": reason})
        pair["_watching"] = False

        # Bildirimler
        if reason == "STOP-LOSS":
            drop = (entry_p - exec_price) / entry_p
            notify_stop_loss(symbol, exec_price, drop * 100)
        elif reason == "TAKE-PROFIT":
            gain = (exec_price - entry_p) / entry_p
            notify_take_profit(symbol, exec_price, gain * 100)
        else:
            notify_sell(symbol, exec_price, rsi, pnl, reason)

        return True
    return False


def _process_pair(client, symbol: str):
    """Tek bir cifti isler. Her dongude tum semboller icin cagrilir."""
    pair = state["pairs"][symbol]

    try:
        df    = get_ohlcv(client, symbol=symbol)
        df    = add_all_indicators(df, rsi_period=state["rsi_period"])
        rsi   = float(df["rsi"].iloc[-2]) if not pd.isna(df["rsi"].iloc[-2]) else 50.0
        price = float(df["close"].iloc[-2])

        # MACD, Bollinger, Trend(EMA200), ATR, Hacim verilerini al
        macd_data = get_latest_macd(df)
        bb_data   = get_latest_bollinger(df)
        trend_data = get_latest_trend(df)
        atr_val    = get_latest_atr(df)
        vol_data   = get_latest_volume(df)

        # Pair state'e indikator verilerini ekle (dashboard icin)
        pair["macd"] = macd_data
        pair["bollinger"] = bb_data
        pair["trend"] = trend_data
        pair["atr"] = atr_val
        pair["volume_info"] = vol_data

        # Stop-loss kontrolu (ATR dinamik veya sabit %)
        pos = get_position(symbol)
        if pos["active"] and pair.get("_watching", False):
            entry = pos["entry_price"]
            # Dinamik stop: giristeki ATR'ye gore. Yoksa sabit %.
            entry_atr = pair.get("_entry_atr", 0)
            if config.USE_ATR_STOPS and entry_atr > 0:
                stop_price = entry - config.ATR_STOP_MULT * entry_atr
                if price <= stop_price:
                    _handle_sell(client, symbol, pair, price, rsi, "STOP-LOSS")
            else:
                drop = (entry - price) / entry
                if drop >= state["stop_loss_pct"]:
                    _handle_sell(client, symbol, pair, price, rsi, "STOP-LOSS")

        # Take-profit kontrolu (ATR dinamik veya sabit %)
        pos = get_position(symbol)
        if pos["active"] and pair.get("_watching", False):
            entry = pos["entry_price"]
            entry_atr = pair.get("_entry_atr", 0)
            if config.USE_ATR_STOPS and entry_atr > 0:
                tp_price = entry + config.ATR_TP_MULT * entry_atr
                if price >= tp_price:
                    _handle_sell(client, symbol, pair, price, rsi, "TAKE-PROFIT")
            else:
                gain = (price - entry) / entry
                if gain >= state["take_profit_pct"]:
                    _handle_sell(client, symbol, pair, price, rsi, "TAKE-PROFIT")

        # BIRLESIK SINYAL: RSI + MACD + BB + Trend filtresi + Hacim filtresi
        signal = get_signal(rsi, price,
                            oversold=state["rsi_oversold"],
                            overbought=state["rsi_overbought"],
                            symbol=symbol,
                            macd=macd_data,
                            bb=bb_data,
                            trend=trend_data,
                            volume=vol_data)
        pos    = get_position(symbol)

        # STRONG_BUY ve BUY ikisi de alim sinyali
        if signal in (SIGNAL_BUY, SIGNAL_STRONG_BUY) and not pos["active"]:
            # SNOWBALL: Dinamik islem miktari
            # STRONG_BUY: Learner=%0 win rate → KUCUK pozisyon (1.5x değil 0.7x)
            # BUY: Normal pozisyon
            trade_amt = state["trade_amount"]
            if signal == SIGNAL_STRONG_BUY:
                # ESKI: trade_amt * 1.5 → buyuk pozisyon (%0 win ratede FELAKET)
                # YENI: trade_amt * 0.7 → kucuk pozisyon (daha ihtiyatli)
                trade_amt = round(trade_amt * 0.7, 2)
                print(f"  [STRONG_BUY UYARI] {symbol}: Learner=%0 win → kucuk pozisyon ${trade_amt}")

            # LEARNER: Bu coinde islem yapmali mi?
            if learner and not learner.should_trade(symbol):
                pass  # Ogrenme motoru bu coini onaylamamis — atla
            elif buy(client, symbol=symbol, usdt_amount=trade_amt):
                pair["trades"].insert(0, {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "action": "BUY", "price": price, "rsi": round(rsi, 2), "pnl": None})
                pair["_watching"] = True
                pair["_entry_rsi"] = round(rsi, 2)      # Learner icin giris RSI
                pair["_entry_signal"] = signal            # Learner icin sinyal tipi
                pair["_entry_margin"] = trade_amt         # BUG FIX #2: Gercek marjin kaydi
                pair["_entry_atr"] = atr_val              # ATR dinamik stop icin

                # DB'ye pozisyon RSI/signal/ATR bilgisini de kaydet (restart icin)
                from database import save_position as _db_save_pos
                try:
                    pos_now = get_position(symbol)
                    _db_save_pos(symbol, pos_now["entry_price"], pos_now["quantity"],
                                 trade_amt, round(rsi, 2), signal, atr_val)
                except Exception:
                    pass

                # AUDITOR: Alim islemini kaydet
                if auditor:
                    auditor.add_trade({
                        "symbol": symbol, "action": "BUY",
                        "entry_price": price, "exit_price": 0,
                        "quantity": 0, "pnl": None,
                        "margin": trade_amt,
                        "timestamp": datetime.now().isoformat(),
                    })

                # DATABASE
                save_trade(symbol, "BUY", price, rsi)

                notify_buy(symbol, price, rsi, trade_amt)

        elif signal in (SIGNAL_SELL, SIGNAL_STRONG_SELL) and pos["active"]:
            # MINIMUM KAR ESIGI: Komisyonun belli katini gecmeden penny-satma
            # Eski davranis: +0.24 USDT kazanci icin bile satti → komisyona para yaktı
            # Yeni davranis: RSI-SELL sinyalinde yeterli kar yoksa bekle
            # NOT: STOP-LOSS ve TAKE-PROFIT bu kontrolden muaf (zarar durdurma gecmez)
            entry_p  = pos["entry_price"]
            qty      = pos["quantity"]
            gross    = (price - entry_p) * qty
            est_fee  = (entry_p + price) * qty * config.FEE_RATE
            min_profit = est_fee * config.MIN_PROFIT_FEE_MULTIPLIER
            if gross < min_profit:
                # Yeterli kar yok — bekle, RSI sinyalini atla
                print(f"  [{symbol}] RSI-SELL ATLIYOR: kar=${gross:.3f} < esik=${min_profit:.3f} (komisyon={est_fee:.3f})")
            else:
                _handle_sell(client, symbol, pair, price, rsi, "RSI-SELL")

        pair["trades"] = pair["trades"][:50]

        # Pozisyon PnL (DURUST spot — kaldirac yok, komisyon dahil)
        pos  = get_position(symbol)
        if pos["active"]:
            gross = (price - pos["entry_price"]) * pos["quantity"]
            est_fee = (pos["entry_price"] + price) * pos["quantity"] * config.FEE_RATE
            pnl = round(gross - est_fee, 4)
        else:
            pnl = 0.0

        # Price history
        new_hist = _build_history(df)
        if new_hist: new_hist[-1]["signal"] = signal
        pair["price_history"] = new_hist

        # Pair state guncelle
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
    global polymarket_bot, news_analyzer, snowball, auditor, learner
    client = get_client()

    # Async event loop kur
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # SNOWBALL + AUDITOR + LEARNER baslat
    try:
        _update_balance(client)
        # SPOT MODU: kaldirac=1 (durust muhasebe). Futures modunda gercek kaldirac.
        effective_leverage = 1 if config.TRADING_MODE == "spot" else state["leverage"]
        snowball = SnowballEngine(initial_balance=state["balance_usdt"], leverage=effective_leverage)
        auditor = TradeAuditor(leverage=effective_leverage)
        learner = TradeLearner()
        print("[AUDIT] Denetim motoru aktif — her 5 islemde otomatik tarama")
        print("[LEARNER] Ogrenme motoru aktif — islemlerden ders cikaracak")
        state["trade_amount"] = snowball.calculate_trade_amount()
        print(f"[SNOWBALL] Baslangic bakiye: ${state['balance_usdt']:.2f}")
        print(f"[SNOWBALL] Ilk islem miktari: ${state['trade_amount']:.2f}")

        # BUG FIX #1: Restart sonrasi acik pozisyonlari DB'den yukle
        restored_positions = load_positions_from_db()
        for rp in restored_positions:
            sym = rp["symbol"]
            pair = state["pairs"].get(sym)
            if pair:
                pair["_watching"] = True
                pair["_entry_rsi"] = rp.get("entry_rsi", 50)
                pair["_entry_signal"] = rp.get("entry_signal", "BUY")
                pair["_entry_margin"] = rp.get("margin_used", state["trade_amount"])
                pair["_entry_atr"] = rp.get("entry_atr", 0)
                print(f"[RESTORE] {sym} pozisyon aktif: giris=${rp['entry_price']:.2f}")

        # Pozisyonlar yuklendikten sonra GERCEK portfoy degerini hesapla
        # (serbest USDT + eldeki coinler) ve snowball baslangicini buna ayarla
        init_equity = _compute_equity()
        state["equity_usdt"] = init_equity
        snowball.initial_balance = init_equity
        snowball.current_balance = init_equity
        state["trade_amount"] = snowball.calculate_trade_amount()
        print(f"[SNOWBALL] Gercek portfoy degeri: ${init_equity:.2f}")

        # Onceki istatistikleri DB'den yukle
        for sym in config.SYMBOLS:
            db_stats = load_stats(sym)
            if db_stats and db_stats["total_trades"] > 0:
                state["pairs"][sym]["stats"] = db_stats
                print(f"[DB] {sym} istatistikleri yuklendi: {db_stats['total_trades']} islem")
    except Exception as e:
        print(f"[SNOWBALL/DB HATA] {e}")

    # Haber Analyzer baslat
    try:
        news_analyzer = NewsAnalyzer()
        try:
            loop.run_until_complete(news_analyzer.__aenter__())
            loop.run_until_complete(_update_news_sentiment())
        except Exception as e:
            print(f"[NEWS HATA] {e}")
    except Exception as e:
        print(f"[NEWS] Baslatilamadi: {e}")

    # Polymarket baslat
    if state["polymarket_enabled"]:
        try:
            loop.run_until_complete(_init_polymarket())
        except Exception as e:
            print(f"[POLY HATA] Baslatilamadi: {e}")
            state["polymarket_enabled"] = False

    # Ilk yukleme — testnet'te olmayan ciftleri otomatik cikar
    valid_symbols = []
    for s in list(state["active_symbols"]):
        try:
            df = get_ohlcv(client, symbol=s)
            df = add_rsi(df, period=state["rsi_period"])
            state["pairs"][s]["price_history"] = _build_history(df)
            valid_symbols.append(s)
        except Exception as e:
            print(f"[SKIP] {s} testnet'te yok veya hata: {e}")
            # Pair'i state'den temizle
            if s in state["pairs"]:
                del state["pairs"][s]

    state["active_symbols"] = valid_symbols
    print(f"[COINS] {len(valid_symbols)} coin aktif: {', '.join(valid_symbols)}")

    try:
        state["equity_history"].append({
            "t": datetime.now().strftime("%H:%M"),
            "balance": state["balance_usdt"]})
    except Exception as e:
        print(f"[Baslangic HATA] {e}")

    notify_start(state["active_symbols"])

    while not stop_event.is_set():
        state["iteration"] += 1
        _update_balance(client)

        for symbol in list(state["active_symbols"]):
            _process_pair(client, symbol)

        # Haber sentiment'ini 5 dakikada bir güncelle
        if state["iteration"] % 300 == 0:  # 300 saniyede bir
            try:
                loop.run_until_complete(_update_news_sentiment())
            except Exception as e:
                print(f"[NEWS] Döngü update hatası: {e}")

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

        # GERCEK portfoy degeri = serbest USDT + acik coinlerin degeri
        equity = _compute_equity()
        state["equity_usdt"] = equity

        # Bakiye gecmisi + DB kaydi (toplam portfoy degeri uzerinden)
        state["equity_history"].append({
            "t": datetime.now().strftime("%H:%M"),
            "balance": equity})
        state["equity_history"] = state["equity_history"][-200:]
        save_equity(equity)

        # SNOWBALL: Gercek portfoy degerini sync et (serbest USDT degil!)
        if snowball:
            snowball.sync_balance(equity)

        # Ayarlanabilir bekleme süresi (1'er saniyelik adımlarla kontrol eder)
        for _ in range(state["loop_interval"]):
            if stop_event.is_set(): break
            time.sleep(1)

    state["running"] = False
    notify_stop()

    # Polymarket'i kapat
    if polymarket_bot:
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(polymarket_bot.shutdown())
        except Exception as e:
            print(f"[POLY] Kapanış hatası: {e}")


# ─── FASTAPI ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Trading Bot API v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    """Keep-alive endpoint — Render'in uyumasini onler."""
    return {"ok": True, "running": state["running"]}


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


# ─── POLYMARKET ENDPOİNTLERİ ───────────────────────────────────────────────────

@app.get("/polymarket/markets")
def get_polymarket_markets():
    """Bulunan crypto tahmin pazarlarını listele."""
    return {
        "enabled": state["polymarket_enabled"],
        "markets": state["polymarket_markets"],
        "count": len(state["polymarket_markets"])
    }


@app.get("/polymarket/positions")
def get_polymarket_positions():
    """Aktif Polymarket pozisyonlarını göster."""
    return {
        "positions": state["polymarket_positions"],
        "count": len(state["polymarket_positions"])
    }


@app.get("/polymarket/status")
def get_polymarket_status():
    """Polymarket bot durumunu göster."""
    return {
        "enabled": state["polymarket_enabled"],
        "bot_initialized": polymarket_bot is not None,
        "markets_found": len(state["polymarket_markets"]),
        "active_positions": len(state["polymarket_positions"])
    }


# ─── HABER SENTIMENT ENDPOİNTLERİ ────────────────────────────────────────────

@app.get("/news/sentiment")
def get_news_sentiment():
    """Genel kripto haber sentiment'ini göster."""
    # Score'u label'a çevir
    score = state["news_sentiment"]
    if score >= 0.65:
        sentiment_label = "very_bullish"
    elif score >= 0.55:
        sentiment_label = "bullish"
    elif score <= 0.35:
        sentiment_label = "very_bearish"
    elif score <= 0.45:
        sentiment_label = "bearish"
    else:
        sentiment_label = "neutral"

    return {
        "sentiment": sentiment_label,
        "score": round(state["news_sentiment"], 2),  # -1 to +1
        "headlines": state["news_headlines"],
        "last_update": state["news_last_update"],
    }


@app.get("/news/headlines")
def get_news_headlines():
    """Top haberler listesi."""
    return {
        "headlines": state["news_headlines"],
        "count": len(state["news_headlines"]),
        "updated": state["news_last_update"],
    }


# ─── SNOWBALL ENDPOINTLERi ──────────────────────────────────────────────────

@app.get("/snowball")
def get_snowball_stats():
    """Kartopu motoru istatistikleri."""
    if not snowball:
        return {"enabled": False, "message": "Bot henuz baslamadi"}
    return {"enabled": True, **snowball.get_stats()}


@app.get("/indicators/{symbol}")
def get_indicators(symbol: str):
    """Coin icin tum indikator verilerini dondur."""
    pair = state["pairs"].get(symbol)
    if not pair:
        return {"error": f"{symbol} bulunamadi"}
    return {
        "symbol": symbol,
        "price": pair.get("price", 0),
        "rsi": pair.get("rsi", 0),
        "signal": pair.get("signal", "HOLD"),
        "macd": pair.get("macd", {}),
        "bollinger": pair.get("bollinger", {}),
    }


# ─── TRADINGVIEW WEBHOOK ─────────────────────────────────────────────────────
# TradingView'da alarm olustur → Webhook URL: https://furkan.fly.dev/webhook/tradingview
# Mesaj formati (JSON):
#   {"symbol": "BTCUSDT", "action": "BUY", "price": 62000, "source": "tradingview"}
#   {"symbol": "BTCUSDT", "action": "SELL", "price": 63000, "source": "tradingview"}

class WebhookSignal(BaseModel):
    symbol: str = "BTCUSDT"
    action: str = "BUY"       # BUY veya SELL
    price: float = 0
    source: str = "tradingview"
    message: str = ""


@app.post("/webhook/tradingview")
async def tradingview_webhook(signal: WebhookSignal):
    """
    TradingView alarm webhook'u.

    TradingView'da:
    1. Grafik ac → Alarm ekle
    2. Bildirimler → Webhook URL: https://furkan.fly.dev/webhook/tradingview
    3. Mesaj:
       {"symbol": "BTCUSDT", "action": "BUY", "price": {{close}}, "source": "tradingview"}
    """
    print(f"[TRADINGVIEW] Sinyal geldi: {signal.action} {signal.symbol} @ ${signal.price}")

    if not state["running"]:
        return {"ok": False, "error": "Bot calismyor"}

    symbol = signal.symbol.upper()
    if symbol not in state["pairs"]:
        return {"ok": False, "error": f"{symbol} takip edilmiyor"}

    client = get_client()
    pair = state["pairs"][symbol]

    if signal.action.upper() == "BUY":
        pos = get_position(symbol)
        if pos["active"]:
            return {"ok": False, "error": f"{symbol} zaten acik pozisyon var"}

        trade_amt = state["trade_amount"]
        if buy(client, symbol=symbol, usdt_amount=trade_amt):
            rsi = pair.get("rsi", 50)
            pair["trades"].insert(0, {
                "time": datetime.now().strftime("%H:%M:%S"),
                "action": "BUY", "price": signal.price or pair.get("price", 0),
                "rsi": rsi, "pnl": None, "reason": "TV-WEBHOOK"})
            pair["_watching"] = True
            save_trade(symbol, "BUY", signal.price or pair.get("price", 0), rsi)
            return {"ok": True, "action": "BUY", "symbol": symbol}

    elif signal.action.upper() == "SELL":
        pos = get_position(symbol)
        if not pos["active"]:
            return {"ok": False, "error": f"{symbol} acik pozisyon yok"}

        rsi = pair.get("rsi", 50)
        price = signal.price or pair.get("price", 0)
        if _handle_sell(client, symbol, pair, price, rsi, "TV-WEBHOOK"):
            return {"ok": True, "action": "SELL", "symbol": symbol}

    return {"ok": False, "error": "Gecersiz islem"}


@app.get("/audit")
def get_audit_status():
    """Denetim motoru durumu."""
    if not auditor:
        return {"enabled": False}
    return {"enabled": True, **auditor.get_status()}


@app.get("/learner")
def get_learner_status():
    """Ogrenme motoru durumu ve oneriler."""
    if not learner:
        return {"enabled": False}
    return {"enabled": True, **learner.get_recommendations()}


@app.get("/db/summary")
def get_database_summary():
    """Veritabani ozet istatistikleri."""
    return get_db_summary()


@app.get("/db/trades")
def get_database_trades(symbol: Optional[str] = None, limit: int = 50):
    """Veritabanindan islem gecmisi."""
    return {"trades": load_trades(symbol=symbol, limit=limit)}


@app.get("/db/equity")
def get_database_equity(limit: int = 120):
    """Veritabanindan bakiye gecmisi."""
    return {"equity": load_equity(limit=limit)}


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


# ─── OTOMATIK BASLAT ────────────────────────────────────────────────────────
# Sunucu acilinca bot otomatik calissin.
# AUTO_START=true env variable ile kontrol edilir.
# Fly.io / Render'da her zaman true olacak.

@app.on_event("startup")
async def on_startup():
    """Sunucu acilinca bot'u otomatik baslat."""
    auto = os.environ.get("AUTO_START", "false").lower()
    if auto == "true":
        print("[AUTO-START] Bot otomatik baslatiliyor...")
        start_bot()
    else:
        print("[READY] Bot hazir — /start ile baslatabilirsin")
        print("[TIP]   Otomatik baslatmak icin: AUTO_START=true")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[OK] API: http://localhost:{port}  |  Dashboard: http://localhost:3000")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
