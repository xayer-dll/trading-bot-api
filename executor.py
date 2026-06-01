# executor.py — Testnet'te emir gönderir, işlemleri loglar ve stop-loss uygular.
import sys
sys.stdout.reconfigure(encoding="utf-8")
#
# Market Order nedir?
#   "Şu anki piyasa fiyatından hemen al/sat" emridir.
#   Limit order'dan farkı: fiyat belirtmeden anında işlem gerçekleşir.
#
# Stop-Loss nedir?
#   Alış fiyatının %2 altına düşünce otomatik satış emri gönderir.
#   Böylece kayıp kontrol altında tutulur.

import os
import json
import logging
from datetime import datetime
from binance.client import Client
from colorama import init, Fore, Style
import config

init(autoreset=True)

# ─── LOG DOSYASI KURULUMU ────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)  # logs/ klasörü yoksa oluştur
log_file = os.path.join("logs", f"trades_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s | %(levelname)s | %(message)s",
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        # Terminale yazmak için ayrıca colorama kullanıyoruz
    ]
)
logger = logging.getLogger("executor")

# ─── DURUM TAKIBI (basit in-memory; ileride DB'ye taşınabilir) ───────────────
_position = {
    "active":      False,   # Şu an açık pozisyon var mı?
    "entry_price": 0.0,     # Alış fiyatı
    "quantity":    0.0,     # Alınan miktar (coin cinsinden)
}


def _log_trade(action: str, symbol: str, qty: float, price: float, detail: str = ""):
    """İşlemi hem dosyaya hem terminale yazar."""
    msg = f"{action} | {symbol} | miktar={qty:.6f} | fiyat={price:.2f} | {detail}"
    logger.info(msg)

    color = Fore.GREEN if action == "BUY" else Fore.RED
    print(color + Style.BRIGHT + f"  >> {msg}" + Style.RESET_ALL)


def buy(client: Client, symbol: str = config.SYMBOL,
        usdt_amount: float = config.TRADE_AMOUNT) -> bool:
    """
    Market BUY emri gönderir.
    usdt_amount kadar USDT harcayarak coin alır.
    """
    if _position["active"]:
        print(Fore.YELLOW + "  [!] Zaten acik pozisyon var, yeni alim yapilmiyor.")
        return False

    try:
        # Güncel fiyatı al
        ticker = client.get_symbol_ticker(symbol=symbol)
        price  = float(ticker["price"])

        # Kaç coin alabileceğimizi hesapla; Binance küsuratlara hassastır
        quantity = round(usdt_amount / price, 6)

        order = client.order_market_buy(symbol=symbol, quantity=quantity)

        _position["active"]      = True
        _position["entry_price"] = price
        _position["quantity"]    = quantity

        _log_trade("BUY", symbol, quantity, price, f"order_id={order['orderId']}")
        return True

    except Exception as e:
        print(Fore.RED + f"  [HATA] BUY hatasi: {e}")
        logger.error(f"BUY hatasi: {e}")
        return False


def sell(client: Client, symbol: str = config.SYMBOL, reason: str = "SIGNAL") -> bool:
    """
    Elimizdeki pozisyonu market SELL emriyle kapatır.
    """
    if not _position["active"]:
        print(Fore.YELLOW + "  [!] Satilacak acik pozisyon yok.")
        return False

    try:
        ticker   = client.get_symbol_ticker(symbol=symbol)
        price    = float(ticker["price"])
        quantity = _position["quantity"]

        order = client.order_market_sell(symbol=symbol, quantity=quantity)

        pnl = (price - _position["entry_price"]) * quantity
        _log_trade("SELL", symbol, quantity, price,
                   f"sebep={reason} | PnL≈{pnl:.4f} USDT | order_id={order['orderId']}")

        # Pozisyonu sıfırla
        _position["active"]      = False
        _position["entry_price"] = 0.0
        _position["quantity"]    = 0.0
        return True

    except Exception as e:
        print(Fore.RED + f"  [HATA] SELL hatasi: {e}")
        logger.error(f"SELL hatasi: {e}")
        return False


def check_stop_loss(client: Client, current_price: float,
                    symbol: str = config.SYMBOL) -> bool:
    """
    Mevcut fiyat alış fiyatının %STOP_LOSS_PCT altına düştüyse otomatik sat.
    Döndürdüğü değer: stop-loss tetiklendiyse True
    """
    if not _position["active"]:
        return False

    entry   = _position["entry_price"]
    drop_pct = (entry - current_price) / entry  # Pozitif = fiyat düştü

    if drop_pct >= config.STOP_LOSS_PCT:
        print(Fore.RED + Style.BRIGHT
              + f"  [STOP-LOSS] STOP-LOSS tetiklendi! "
              + f"Giriş={entry:.2f}  Şimdi={current_price:.2f}  "
              + f"Kayıp=%{drop_pct*100:.2f}")
        sell(client, symbol, reason="STOP-LOSS")
        return True

    return False


def get_position() -> dict:
    """Mevcut pozisyon bilgisini döndürür (bot.py dashboard için)."""
    return _position.copy()
