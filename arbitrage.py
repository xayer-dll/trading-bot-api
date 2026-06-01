# arbitrage.py — Triangular Arbitraj (Üçgen Arbitraj) Modülü
#
# ─── KAVRAM AÇIKLAMASI ────────────────────────────────────────────────────────
#
# Triangular Arbitraj nedir?
#   Aynı borsa içinde üç farklı kuru kullanarak kâr etme stratejisidir.
#   Temel fikir: A → B → C → A zincirinde, başladığından fazla A ile bitirmek.
#
# Örnek zincir (BTC → ETH → USDT → BTC):
#   1. USDT ile BTC satın al   (BTCUSDT çifti)
#   2. BTC ile ETH satın al    (ETHBTC çifti)
#   3. ETH'yi USDT'ye çevir    (ETHUSDT çifti)
#   Sonuçta elimizde daha fazla USDT varsa → ARBİTRAJ KÂRI!
#
# Neden her zaman çalışmaz?
#   • İşlem ücretleri kârı siler (Binance ~%0.1 komisyon)
#   • Fiyatlar milisaniyeler içinde değişir
#   • Binance aynı anda gelen emirleri sıraya alır → slippage
#
# Bu modül şimdilik SADECE TESPİT eder, emir GÖNDERMEZ.
# Kâr fırsatı varsa log'a yazar. Gerçek işlem için execute=True geçilebilir.
#
# ─────────────────────────────────────────────────────────────────────────────

import logging
from binance.client import Client
from colorama import init, Fore, Style

init(autoreset=True)
logger = logging.getLogger("arbitrage")

# İşlem ücreti varsayımı (%0.1 = 0.001)
FEE = 0.001

# Taranan üçgen zincirler
TRIANGLES = [
    # (adım1_çift, yön1, adım2_çift, yön2, adım3_çift, yön3)
    # yön: "BUY" = quote ile base al, "SELL" = base sat quote al
    ("BTCUSDT",  "BUY",  "ETHBTC",  "BUY",  "ETHUSDT", "SELL"),
    ("BNBBTC",   "BUY",  "BNBUSDT", "SELL", "BTCUSDT", "SELL"),
]


def _get_price(client: Client, symbol: str, side: str) -> float:
    """
    BUY tarafı için ask (satıcının fiyatı), SELL için bid (alıcının fiyatı) döndürür.
    Spread'i hesaba katmak için orderbook'tan 1. seviyeye bakıyoruz.
    """
    ob = client.get_order_book(symbol=symbol, limit=5)
    if side == "BUY":
        return float(ob["asks"][0][0])  # En düşük satış fiyatı
    else:
        return float(ob["bids"][0][0])  # En yüksek alış fiyatı


def scan_triangles(client: Client) -> list[dict]:
    """
    Tanımlı tüm üçgenleri tara; kârlı olanları döndür.
    Her sonuç dict'i: {triangle, profit_pct, detail}
    """
    opportunities = []

    for tri in TRIANGLES:
        sym1, side1, sym2, side2, sym3, side3 = tri
        try:
            p1 = _get_price(client, sym1, side1)
            p2 = _get_price(client, sym2, side2)
            p3 = _get_price(client, sym3, side3)

            # 1 USDT ile başlayalım ve zinciri simüle edelim
            # BUY  → 1 / fiyat   (USDT verip BTC alıyoruz)
            # SELL → 1 * fiyat   (BTC satıp USDT alıyoruz)
            def step(amount: float, price: float, side: str) -> float:
                raw = (amount / price) if side == "BUY" else (amount * price)
                return raw * (1 - FEE)   # Komisyon düş

            after1 = step(1.0,   p1, side1)
            after2 = step(after1, p2, side2)
            after3 = step(after2, p3, side3)

            profit_pct = (after3 - 1.0) * 100  # % kâr/zarar

            label = f"{sym1}→{sym2}→{sym3}"

            if profit_pct > 0:
                # Kâr fırsatı bulundu
                msg = (f"ARBİTRAJ FIRSATI: {label}  "
                       f"kâr=%{profit_pct:.4f}  "
                       f"fiyatlar=({p1},{p2},{p3})")
                logger.info(msg)
                print(Fore.CYAN + Style.BRIGHT + f"  [ARB] {msg}")
                opportunities.append({
                    "triangle":   label,
                    "profit_pct": profit_pct,
                    "prices":     (p1, p2, p3),
                })
            else:
                print(Fore.WHITE + f"  · {label}  kâr=%{profit_pct:.4f}  (negatif, atlandı)")

        except Exception as e:
            print(Fore.RED + f"  [HATA] Arbitraj tarama hatasi [{sym1}]: {e}")

    return opportunities


if __name__ == "__main__":
    from connection import get_client
    client = get_client()
    print(Fore.MAGENTA + "\n─── Triangular Arbitraj Taraması ───────────────")
    opps = scan_triangles(client)
    if not opps:
        print(Fore.YELLOW + "  Şu an kârlı fırsat yok.")
    print()
