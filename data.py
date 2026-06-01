# data.py — Binance'tan piyasa verisi (OHLCV) çeker ve Pandas DataFrame'e dönüştürür.
#
# OHLCV nedir?
#   O = Open  (mumun açılış fiyatı)
#   H = High  (mumun en yüksek fiyatı)
#   L = Low   (mumun en düşük fiyatı)
#   C = Close (mumun kapanış fiyatı)  ← RSI bu kolonu kullanır
#   V = Volume (o sürede işlem gören miktar)

import pandas as pd
from binance.client import Client
import config


def get_ohlcv(client: Client, symbol: str = config.SYMBOL,
              interval: str = config.TIMEFRAME,
              limit: int = config.CANDLE_LIMIT) -> pd.DataFrame:
    """
    Belirtilen sembol için geçmiş mum verilerini çeker.
    Örnek: get_ohlcv(client) → son 100 dakikalık BTCUSDT mumları
    """
    # Binance API'den ham veri al; her eleman bir mum = liste içinde liste
    raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)

    # Ham veriyi anlamlı sütun adlarıyla DataFrame'e çevir
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])

    # Fiyat kolonlarını sayıya çevir (Binance string olarak gönderir)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])

    # Zaman damgasını okunabilir formata çevir
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")

    # Sadece gerekli kolonları tut
    df = df[["open_time", "open", "high", "low", "close", "volume"]]
    df.set_index("open_time", inplace=True)

    return df


if __name__ == "__main__":
    from connection import get_client
    client = get_client()
    df = get_ohlcv(client)
    print(f"Çekilen mum sayısı: {len(df)}")
    print(df.tail(3))  # Son 3 mumu göster
