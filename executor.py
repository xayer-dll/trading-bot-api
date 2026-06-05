# executor.py -- Testnet'te emir gonderir, islemleri loglar ve stop-loss uygular.
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import json
import logging
from datetime import datetime
from binance.client import Client
from colorama import init, Fore, Style
import config

init(autoreset=True)

# ─── LOG DOSYASI KURULUMU ────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
log_file = os.path.join("logs", f"trades_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s | %(levelname)s | %(message)s",
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
)
logger = logging.getLogger("executor")

# ─── DURUM TAKIBI (HER COIN ICIN AYRI POZISYON) ─────────────────────────────
# Onceki hali: tek _position dict'i vardi → tum coinler karisiyordu (BUG!)
# Simdi: her symbol icin ayri pozisyon tutuluyor

_positions = {}  # {"BTCUSDT": {active, entry_price, quantity}, ...}


def _get_pos(symbol: str) -> dict:
    """Belirli bir coin'in pozisyonunu al."""
    if symbol not in _positions:
        _positions[symbol] = {
            "active": False,
            "entry_price": 0.0,
            "quantity": 0.0,
        }
    return _positions[symbol]


def _log_trade(action: str, symbol: str, qty: float, price: float, detail: str = ""):
    msg = f"{action} | {symbol} | miktar={qty:.6f} | fiyat={price:.2f} | {detail}"
    logger.info(msg)
    color = Fore.GREEN if action == "BUY" else Fore.RED
    print(color + Style.BRIGHT + f"  >> {msg}" + Style.RESET_ALL)


def buy(client: Client, symbol: str = config.SYMBOL,
        usdt_amount: float = config.TRADE_AMOUNT) -> bool:
    """Market BUY emri gonderir."""
    pos = _get_pos(symbol)

    if pos["active"]:
        print(Fore.YELLOW + f"  [!] {symbol} zaten acik pozisyon var.")
        return False

    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        price  = float(ticker["price"])
        quantity = round(usdt_amount / price, 6)

        order = client.order_market_buy(symbol=symbol, quantity=quantity)

        pos["active"]      = True
        pos["entry_price"] = price
        pos["quantity"]    = quantity

        _log_trade("BUY", symbol, quantity, price, f"order_id={order['orderId']}")
        return True

    except Exception as e:
        print(Fore.RED + f"  [HATA] {symbol} BUY hatasi: {e}")
        logger.error(f"{symbol} BUY hatasi: {e}")
        return False


def sell(client: Client, symbol: str = config.SYMBOL, reason: str = "SIGNAL") -> bool:
    """Pozisyonu market SELL emriyle kapatir."""
    pos = _get_pos(symbol)

    if not pos["active"]:
        print(Fore.YELLOW + f"  [!] {symbol} satilacak pozisyon yok.")
        return False

    try:
        ticker   = client.get_symbol_ticker(symbol=symbol)
        price    = float(ticker["price"])
        quantity = pos["quantity"]

        order = client.order_market_sell(symbol=symbol, quantity=quantity)

        pnl = (price - pos["entry_price"]) * quantity
        _log_trade("SELL", symbol, quantity, price,
                   f"sebep={reason} | PnL={pnl:.4f} USDT | order_id={order['orderId']}")

        # Pozisyonu sifirla
        pos["active"]      = False
        pos["entry_price"] = 0.0
        pos["quantity"]    = 0.0
        return True

    except Exception as e:
        print(Fore.RED + f"  [HATA] {symbol} SELL hatasi: {e}")
        logger.error(f"{symbol} SELL hatasi: {e}")
        return False


def check_stop_loss(client: Client, current_price: float,
                    symbol: str = config.SYMBOL) -> bool:
    """Stop-loss kontrolu."""
    pos = _get_pos(symbol)
    if not pos["active"]:
        return False

    entry   = pos["entry_price"]
    drop_pct = (entry - current_price) / entry

    if drop_pct >= config.STOP_LOSS_PCT:
        print(Fore.RED + Style.BRIGHT
              + f"  [STOP-LOSS] {symbol} tetiklendi! "
              + f"Giris={entry:.2f}  Simdi={current_price:.2f}  "
              + f"Kayip=%{drop_pct*100:.2f}")
        sell(client, symbol, reason="STOP-LOSS")
        return True

    return False


def get_position(symbol: str = None) -> dict:
    """Pozisyon bilgisini dondurur."""
    if symbol:
        return _get_pos(symbol).copy()
    # Geriye uyumluluk: symbol verilmezse ilk aktif pozisyonu dondur
    for sym, pos in _positions.items():
        if pos["active"]:
            return pos.copy()
    return {"active": False, "entry_price": 0.0, "quantity": 0.0}
