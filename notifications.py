# notifications.py — Telegram bildirimleri.
#
# Bir işlem gerçekleşince, stop-loss/take-profit tetiklenince
# veya hata olunca telefonuna mesaj gelir.
#
# KURULUM:
#   1. Telegram'da @BotFather'a yaz: /newbot
#   2. Bot adı ve kullanıcı adı gir
#   3. Gelen TOKEN'ı config.py → TELEGRAM_TOKEN'a yapıştır
#   4. Botuna /start mesajı at
#   5. https://api.telegram.org/bot{TOKEN}/getUpdates adresini ziyaret et
#   6. "chat":{"id": XXXXX} değerini TELEGRAM_CHAT_ID'ye gir
#   7. config.py → TELEGRAM_ENABLED = True yap

import requests
import config


def _send(text: str):
    """Ham Telegram mesajı gönderir. Konfigürasyon yoksa sessizce atlar."""
    if not config.TELEGRAM_ENABLED:
        return
    if "BURAYA" in config.TELEGRAM_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id":    config.TELEGRAM_CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception as e:
        print(f"[Telegram HATA] {e}")


def notify_start(symbols: list):
    _send(f"🤖 <b>Bot Başlatıldı</b>\nTakip edilen çiftler: {', '.join(symbols)}")


def notify_stop():
    _send("⏹ <b>Bot Durduruldu</b>")


def notify_buy(symbol: str, price: float, rsi: float, amount: float):
    _send(
        f"🟢 <b>ALIŞ — {symbol}</b>\n"
        f"Fiyat: <b>${price:,.2f}</b>\n"
        f"RSI: {rsi:.2f} (aşırı satılmış)\n"
        f"Miktar: ~{amount:.2f} USDT"
    )


def notify_sell(symbol: str, price: float, rsi: float, pnl: float, reason: str):
    emoji = "🟡" if pnl >= 0 else "🔴"
    sign  = "+" if pnl >= 0 else ""
    _send(
        f"{emoji} <b>SATIŞ — {symbol}</b>\n"
        f"Fiyat: <b>${price:,.2f}</b>\n"
        f"RSI: {rsi:.2f}\n"
        f"P&L: <b>{sign}{pnl:.4f} USDT</b>\n"
        f"Sebep: {reason}"
    )


def notify_stop_loss(symbol: str, price: float, loss_pct: float):
    _send(
        f"🛑 <b>STOP-LOSS — {symbol}</b>\n"
        f"Fiyat: ${price:,.2f}\n"
        f"Kayıp: %{loss_pct:.2f}"
    )


def notify_take_profit(symbol: str, price: float, gain_pct: float):
    _send(
        f"💰 <b>TAKE-PROFIT — {symbol}</b>\n"
        f"Fiyat: ${price:,.2f}\n"
        f"Kâr: %{gain_pct:.2f}"
    )


def notify_error(symbol: str, error: str):
    _send(f"⚠️ <b>HATA — {symbol}</b>\n{error[:200]}")
