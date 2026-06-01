# bot.py — Ana döngü: tüm modülleri bir araya getirir.
import sys
sys.stdout.reconfigure(encoding="utf-8")
#
# Her 60 saniyede bir şunu yapar:
#   1. Piyasa verisini çek  (data.py)
#   2. RSI hesapla          (indicators.py)
#   3. Sinyal üret          (strategy.py)
#   4. Stop-loss kontrol et (executor.py)
#   5. Gerekirse emir gönder (executor.py)
#   6. Terminale dashboard  yazdır

import time
import os
from datetime import datetime
from colorama import init, Fore, Back, Style

import config
from connection import get_client
from data import get_ohlcv
from indicators import add_rsi, get_latest_rsi
from strategy import get_signal, SIGNAL_BUY, SIGNAL_SELL
from executor import buy, sell, check_stop_loss, get_position

init(autoreset=True)

LOOP_INTERVAL = 60  # saniye


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_dashboard(price: float, rsi: float, signal: str,
                    balance_usdt: float, iteration: int):
    """Terminalde canlı durum paneli gösterir."""
    pos = get_position()
    now = datetime.now().strftime("%H:%M:%S")

    signal_color = {
        "BUY":  Fore.GREEN,
        "SELL": Fore.RED,
        "HOLD": Fore.YELLOW,
    }.get(signal, Fore.WHITE)

    rsi_color = Fore.GREEN if rsi < 30 else (Fore.RED if rsi > 70 else Fore.YELLOW)

    print(Back.BLACK + Fore.CYAN + Style.BRIGHT
          + "══════════════════════════════════════════════════")
    print(Fore.CYAN + Style.BRIGHT
          + f"   BINANCE TESTNET BOT  |  {now}  |  Döngü #{iteration}")
    print(Fore.CYAN + "══════════════════════════════════════════════════")

    print(Fore.WHITE  + f"  Sembol  : " + Fore.YELLOW + config.SYMBOL)
    print(Fore.WHITE  + f"  Fiyat   : " + Fore.WHITE  + Style.BRIGHT + f"{price:.2f} USDT")
    print(Fore.WHITE  + f"  RSI({config.RSI_PERIOD})  : " + rsi_color + f"{rsi:.2f}")
    print(Fore.WHITE  + f"  Sinyal  : " + signal_color + Style.BRIGHT + signal)
    print(Fore.WHITE  + f"  Bakiye  : " + Fore.GREEN   + f"{balance_usdt:.2f} USDT")

    if pos["active"]:
        entry = pos["entry_price"]
        pnl   = (price - entry) * pos["quantity"]
        pnl_color = Fore.GREEN if pnl >= 0 else Fore.RED
        print(Fore.WHITE + f"  Pozisyon: " + Fore.MAGENTA + Style.BRIGHT + "AÇIK")
        print(Fore.WHITE + f"  Giriş   : " + Fore.MAGENTA + f"{entry:.2f}")
        print(Fore.WHITE + f"  PnL≈    : " + pnl_color + f"{pnl:+.4f} USDT")
    else:
        print(Fore.WHITE + f"  Pozisyon: " + Fore.BLUE + "YOK")

    print(Fore.CYAN + "──────────────────────────────────────────────────")
    print(Fore.WHITE + f"  Sonraki döngü {LOOP_INTERVAL} saniye sonra... (Ctrl+C ile dur)")
    print(Fore.CYAN + "══════════════════════════════════════════════════\n")


def get_usdt_balance(client) -> float:
    """Hesaptaki serbest USDT miktarını döndürür."""
    try:
        account = client.get_account()
        for asset in account["balances"]:
            if asset["asset"] == "USDT":
                return float(asset["free"])
    except Exception:
        pass
    return 0.0


def run():
    print(Fore.CYAN + Style.BRIGHT + "\n  Binance Testnet Trading Bot başlatılıyor...\n")

    # Bağlantı kur
    client = get_client()

    # Bağlantı testi
    try:
        client.ping()
        print(Fore.GREEN + "  [OK] Sunucuya baglandi\n")
    except Exception as e:
        print(Fore.RED + f"  [HATA] Baglanti kurulamadi: {e}")
        return

    iteration = 0

    while True:
        iteration += 1
        clear_screen()

        print(Fore.WHITE + f"  [{datetime.now().strftime('%H:%M:%S')}] Veri çekiliyor...")

        try:
            # 1. Piyasa verisi
            df = get_ohlcv(client)

            # 2. RSI hesapla
            df = add_rsi(df)
            rsi = get_latest_rsi(df)

            # 3. Güncel fiyat (son kapanmış mumun Close değeri)
            current_price = float(df["close"].iloc[-2])

            # 4. Stop-loss kontrol
            check_stop_loss(client, current_price)

            # 5. Sinyal üret
            signal = get_signal(rsi, current_price)

            # 6. Emir gönder
            if signal == SIGNAL_BUY and not get_position()["active"]:
                buy(client)
            elif signal == SIGNAL_SELL and get_position()["active"]:
                sell(client, reason="SIGNAL")

            # 7. Dashboard
            usdt_bal = get_usdt_balance(client)
            print_dashboard(current_price, rsi, signal, usdt_bal, iteration)

        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n\n  Bot durduruldu (Ctrl+C). Güle güle!")
            break
        except Exception as e:
            print(Fore.RED + f"  [HATA] Dongu hatasi: {e}")

        # 60 saniye bekle; Ctrl+C bekleme sırasında da çalışır
        try:
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n\n  Bot durduruldu. Güle güle!")
            break


if __name__ == "__main__":
    run()
