# connection.py — Binance Testnet'e bağlantı kurar ve bağlantıyı test eder.
#
# python-binance kütüphanesi, Binance'ın REST API'si ile kolayca konuşmamızı sağlar.
# "testnet=True" parametresi, tüm isteklerin gerçek sunucu yerine
# testnet.binance.vision adresine yönlendirilmesini garantiler.

import sys
sys.stdout.reconfigure(encoding="utf-8")

from binance.client import Client
from colorama import init, Fore, Style
import config

init(autoreset=True)  # colorama — her print sonrası rengi sıfırla


def get_client() -> Client:
    """API anahtarlarını kullanarak Binance Testnet istemcisi döndürür."""
    client = Client(
        api_key    = config.API_KEY,
        api_secret = config.API_SECRET,
        testnet    = True,          # ← Gerçek para tehlikesi YOK
    )
    # Testnet REST endpoint'ini açıkça belirt
    client.API_URL = config.TESTNET_URL + "/api"
    return client


def test_connection() -> bool:
    """
    Bağlantıyı test eder: bakiye sorgular.
    Başarılıysa True, hata varsa False döner.
    """
    try:
        client = get_client()
        account = client.get_account()

        print(Fore.GREEN + "[OK] Binance Testnet baglantisi BASARILI!")
        print(Fore.CYAN + "\n-- USDT / BTC Bakiyeleri ------------------")

        for asset in account["balances"]:
            free = float(asset["free"])
            locked = float(asset["locked"])
            # Sadece bakiyesi sıfırdan büyük olanları göster
            if free > 0 or locked > 0:
                print(
                    Fore.YELLOW + f"  {asset['asset']:8s}"
                    + Fore.WHITE  + f"  Serbest: {free:>15.6f}"
                    + Fore.MAGENTA + f"  Kilitli: {locked:>15.6f}"
                )

        print(Style.RESET_ALL)
        return True

    except Exception as e:
        print(Fore.RED + f"[HATA] Baglanti HATASI: {e}")
        print(Fore.YELLOW + "  -> config.py dosyasindaki API_KEY ve API_SECRET degerlerini kontrol et.")
        return False


if __name__ == "__main__":
    test_connection()
