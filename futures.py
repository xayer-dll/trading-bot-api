# futures.py — Binance Futures Testnet işlemleri.
#
# SPOT vs FUTURES farkı:
#   Spot:    Gerçek coin alıp satarsın. 100$ → 100$'lık BTC.
#   Futures: Kağıt üzerinde kontrat alırsın. Kaldıraçla büyütülür.
#            100$ + 10x kaldıraç = 1000$'lık pozisyon.
#            Fiyat %1 değişirse: +%10 kâr VEYA -10% zarar.
#            Fiyat %10 düşerse: TÜM PARA SİLİNİR (liquidation).
#
# Long  → Fiyat YÜKSELİR diye bahse girersin
# Short → Fiyat DÜŞER   diye bahse girersin  (spot'ta yok!)
#
# KURULUM:
#   1. https://testnet.binancefuture.com adresine git
#   2. Sağ üstten "API Key" butonuna bas
#   3. Gelen key'leri config.py → FUTURES_API_KEY / FUTURES_API_SECRET'e gir
#   4. config.py → FUTURES_ENABLED = True yap

from binance.client import Client
from binance.exceptions import BinanceAPIException
import config


def get_futures_client() -> Client:
    """Binance Futures Demo istemcisi oluşturur."""
    client = Client(
        api_key    = config.FUTURES_API_KEY,
        api_secret = config.FUTURES_API_SECRET,
        testnet    = False,   # demo-fapi endpoint kullanıyor
    )
    # demo.binance.com Futures API endpoint
    client.FUTURES_URL = config.FUTURES_TESTNET_URL + "/fapi"
    return client


def is_configured() -> bool:
    return config.FUTURES_ENABLED and "BURAYA" not in config.FUTURES_API_KEY


def set_leverage(client: Client, symbol: str, leverage: int) -> dict:
    """
    Kaldıraç oranını ayarlar.
    leverage=5 → Her 1$ için 5$'lık pozisyon açılır.
    """
    try:
        result = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"[Futures] {symbol} kaldıraç {leverage}x olarak ayarlandı")
        return result
    except BinanceAPIException as e:
        print(f"[Futures HATA] Kaldıraç ayarlanamadı: {e}")
        return {}


def open_long(client: Client, symbol: str, usdt_amount: float,
              leverage: int = None) -> dict:
    """
    Long pozisyon aç: fiyat yükselir diye bahse gir.
    Verilen USDT miktarı kaldıraçla büyütülür.
    """
    if leverage is None:
        leverage = config.LEVERAGE

    set_leverage(client, symbol, leverage)

    # Güncel fiyatı al
    ticker = client.futures_symbol_ticker(symbol=symbol)
    price  = float(ticker["price"])

    # Nominal değer = usdt_amount × leverage
    nominal = usdt_amount * leverage
    qty     = round(nominal / price, 3)

    try:
        order = client.futures_create_order(
            symbol   = symbol,
            side     = "BUY",
            type     = "MARKET",
            quantity = qty,
        )
        print(f"[Futures] LONG aç: {symbol} {qty} @ ~{price:.2f} ({leverage}x)")
        return {"ok": True, "order": order, "price": price, "qty": qty, "leverage": leverage}
    except BinanceAPIException as e:
        print(f"[Futures HATA] Long açılamadı: {e}")
        return {"ok": False, "error": str(e)}


def open_short(client: Client, symbol: str, usdt_amount: float,
               leverage: int = None) -> dict:
    """
    Short pozisyon aç: fiyat düşer diye bahse gir.
    Spot'ta yapılamaz, Futures'a özgüdür.
    """
    if leverage is None:
        leverage = config.LEVERAGE

    set_leverage(client, symbol, leverage)

    ticker = client.futures_symbol_ticker(symbol=symbol)
    price  = float(ticker["price"])
    qty    = round((usdt_amount * leverage) / price, 3)

    try:
        order = client.futures_create_order(
            symbol   = symbol,
            side     = "SELL",
            type     = "MARKET",
            quantity = qty,
        )
        print(f"[Futures] SHORT aç: {symbol} {qty} @ ~{price:.2f} ({leverage}x)")
        return {"ok": True, "order": order, "price": price, "qty": qty, "leverage": leverage}
    except BinanceAPIException as e:
        print(f"[Futures HATA] Short açılamadı: {e}")
        return {"ok": False, "error": str(e)}


def close_position(client: Client, symbol: str) -> dict:
    """Açık pozisyonu kapatır (long veya short fark etmez)."""
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            amt = float(pos["positionAmt"])
            if amt == 0:
                continue
            side = "SELL" if amt > 0 else "BUY"   # Long → Sat, Short → Al
            order = client.futures_create_order(
                symbol         = symbol,
                side           = side,
                type           = "MARKET",
                quantity       = abs(amt),
                reduceOnly     = True,
            )
            print(f"[Futures] Pozisyon kapatıldı: {symbol}")
            return {"ok": True, "order": order}
        return {"ok": False, "error": "Açık pozisyon bulunamadı"}
    except BinanceAPIException as e:
        return {"ok": False, "error": str(e)}


def get_position_info(client: Client, symbol: str) -> dict:
    """
    Açık pozisyon bilgilerini döndürür.
    unrealizedProfit: anlık kâr/zarar
    liquidationPrice: bu fiyata düşerse para sıfırlanır
    """
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if float(pos["positionAmt"]) != 0:
                return {
                    "active":             True,
                    "symbol":             symbol,
                    "side":               "LONG" if float(pos["positionAmt"]) > 0 else "SHORT",
                    "quantity":           abs(float(pos["positionAmt"])),
                    "entry_price":        float(pos["entryPrice"]),
                    "mark_price":         float(pos.get("markPrice", 0)),
                    "unrealized_pnl":     float(pos["unRealizedProfit"]),
                    "liquidation_price":  float(pos.get("liquidationPrice", 0)),
                    "leverage":           int(pos.get("leverage", config.LEVERAGE)),
                    "margin":             float(pos.get("initialMargin", 0)),
                }
        return {"active": False}
    except Exception as e:
        return {"active": False, "error": str(e)}


def get_funding_rate(client: Client, symbol: str) -> float:
    """
    Funding rate: Futures tutmanın saatlik maliyeti/geliri.
    Pozitif → long tutanlar short tutanlara öder.
    Negatif → short tutanlar long tutanlara öder.
    """
    try:
        info = client.futures_funding_rate(symbol=symbol, limit=1)
        if info:
            return float(info[0]["fundingRate"]) * 100  # % cinsinden
    except Exception:
        pass
    return 0.0


def get_futures_balance(client: Client) -> float:
    """Futures hesap bakiyesini döndürür (USDT)."""
    try:
        balances = client.futures_account_balance()
        for b in balances:
            if b["asset"] == "USDT":
                return float(b["balance"])
    except Exception:
        pass
    return 0.0
