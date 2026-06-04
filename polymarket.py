# polymarket.py — Polymarket API integrationu
#
# Polymarket nedir?
#   • Tahmin pazarları (prediction markets) platformu
#   • Cryptocurrency ile işlem yapılır (USDC)
#   • Gerçek para ile ticaret → yüksek getiri potansiyeli
#   • API aracılığıyla programatik işlem mümkün
#
# Kullanım senaryosu:
#   • Bot RSI sinyali alıyor → Polymarket'te tahmin pozisyonu aç
#   • Prediction market volatilitesi + kripto volatilitesi = yüksek getiri

import asyncio
import aiohttp
import json
from typing import Optional, List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Polymarket API endpoint'leri
POLYMARKET_CLOB = "https://clob.polymarket.com"
POLYMARKET_GAMMA = "https://gamma-api.polymarket.com"


class PolymarketClient:
    """Polymarket REST API client."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        API anahtarları isteğe bağlı.
        İlk başta public endpoint'lerden veri çekeceğiz (anahtarsız).
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_markets(self, tag: Optional[str] = None) -> List[Dict]:
        """Polymarket'teki tüm piyasaları listele."""
        try:
            async with self.session.get(f"{POLYMARKET_GAMMA}/markets") as resp:
                if resp.status == 200:
                    markets = await resp.json()
                    # Tag filtrele (opsiyonel)
                    if tag:
                        markets = [m for m in markets if tag.lower() in str(m.get("tags", [])).lower()]
                    return markets
        except Exception as e:
            logger.error(f"[POLY] Piyasalar alınamadı: {e}")
        return []

    async def get_market(self, market_id: str) -> Optional[Dict]:
        """Belirli bir piyasanın detaylarını al."""
        try:
            async with self.session.get(f"{POLYMARKET_GAMMA}/markets/{market_id}") as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[POLY] Piyasa {market_id} alınamadı: {e}")
        return None

    async def get_prices(self, market_id: str) -> Optional[Dict]:
        """Piyasa fiyatlarını (YES/NO) al."""
        try:
            async with self.session.get(f"{POLYMARKET_CLOB}/prices?market_id={market_id}") as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[POLY] Fiyatlar alınamadı: {e}")
        return None

    async def search_markets(self, query: str) -> List[Dict]:
        """Piyasaları ara."""
        all_markets = await self.get_markets()
        results = []
        query_lower = query.lower()

        for market in all_markets:
            title = market.get("title", "").lower()
            question = market.get("question", "").lower()

            if query_lower in title or query_lower in question:
                results.append(market)

        return results[:20]  # Top 20 sonuç

    async def get_market_price(self, market_id: str) -> Optional[Dict]:
        """
        Piyasa YES fiyatını al.
        YES fiyatı yüksek = pazar YES tarafını fark ediyor
        """
        try:
            async with self.session.get(
                f"{POLYMARKET_CLOB}/prices",
                params={"market_id": market_id}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("prices"):
                        return {
                            "yes_price": float(data["prices"][0]),  # YES tarafı
                            "no_price": float(data["prices"][1]),   # NO tarafı
                            "timestamp": datetime.now().isoformat()
                        }
        except Exception as e:
            logger.error(f"[POLY] Fiyat hatası: {e}")
        return None


class PolymarketBot:
    """
    RSI sinyalini Polymarket tahmin pazarlarına bağla.

    Strateji:
      1. RSI < 30 (Oversold) → Piyasada "Evet" (YES) tarafına para koy
      2. RSI > 70 (Overbought) → Piyasada "Hayır" (NO) tarafına para koy
      3. Belirli bir kar veya zararı tetikle → pozisyondan çık
    """

    def __init__(self):
        self.client = None
        self.positions = {}  # market_id → pozisyon bilgisi
        self.watched_markets = {}  # market_id → piyasa özeti

    async def initialize(self):
        """Bot'u başlat."""
        self.client = PolymarketClient()
        await self.client.__aenter__()
        logger.info("[POLY-BOT] Hazır!")

    async def shutdown(self):
        """Bot'u kapat."""
        if self.client:
            await self.client.__aexit__(None, None, None)

    async def find_crypto_prediction_markets(self) -> List[Dict]:
        """Kripto ile ilgili tahmin pazarlarını bul."""
        keywords = ["bitcoin", "ethereum", "crypto", "btc", "eth", "price", "bull", "bear"]
        all_markets = await self.client.get_markets()

        crypto_markets = []
        for market in all_markets:
            title = market.get("title", "").lower()
            question = market.get("question", "").lower()

            if any(kw in title or kw in question for kw in keywords):
                crypto_markets.append({
                    "id": market.get("id"),
                    "title": market.get("title"),
                    "question": market.get("question"),
                    "volume": market.get("volume", 0),
                    "liquidity": market.get("liquidity", 0)
                })

        # Likidite sırasına göre sırala
        crypto_markets.sort(key=lambda x: x.get("liquidity", 0), reverse=True)
        return crypto_markets[:10]  # Top 10

    async def execute_trade(
        self,
        market_id: str,
        rsi: float,
        symbol: str,
        news_sentiment: float = 0.5  # -1 to +1, default neutral
    ) -> Dict:
        """
        RSI + Haber Sentiment ile Polymarket'te işlem yap.

        Girdiler:
          - market_id: Polymarket pazar ID'si
          - rsi: RSI değeri (0-100)
          - symbol: İşlem çifti (BTCUSDT vb.)
          - news_sentiment: Haber sentiment skoru (-1=çok negatif, +1=çok pozitif)

        Algoritma:
          1. RSI sinyali → base confidence
          2. Haber sentiment → confidence multiplier
          3. Final confidence & bet size hesapla
        """
        market = await self.client.get_market(market_id)
        if not market:
            return {"success": False, "error": "Piyasa bulunamadı"}

        price = await self.client.get_market_price(market_id)
        if not price:
            return {"success": False, "error": "Fiyat alınamadı"}

        yes_price = price["yes_price"]

        # ─── RSI Base Signal ───────────────────────────────────────────
        if rsi < 30:  # Oversold = bullish
            side = "YES"
            rsi_confidence = (30 - rsi) / 30  # 0-1
        elif rsi > 70:  # Overbought = bearish
            side = "NO"
            rsi_confidence = (rsi - 70) / 30  # 0-1
        else:
            return {"success": False, "reason": "RSI nötr bölgede"}

        # ─── Haber Sentiment Boost ────────────────────────────────────
        # news_sentiment: -1 to +1
        # Side = "YES" ise, news_sentiment > 0 → boost
        # Side = "NO" ise, news_sentiment < 0 → boost

        if side == "YES":
            # Positive news = stronger YES signal
            if news_sentiment > 0:
                sentiment_boost = news_sentiment * 0.3  # max +30% boost
            else:
                sentiment_boost = news_sentiment * 0.2  # -20% penalty
        else:  # side = "NO"
            # Negative news = stronger NO signal
            if news_sentiment < 0:
                sentiment_boost = abs(news_sentiment) * 0.3
            else:
                sentiment_boost = news_sentiment * -0.2

        # ─── Final Confidence ─────────────────────────────────────────
        final_confidence = min(1.0, max(0.1, rsi_confidence + sentiment_boost))

        # ─── Bet Size (linear scaling) ─────────────────────────────────
        # 10% confidence → $10 USDC
        # 90% confidence → $90 USDC
        bet_size = 10 + (final_confidence * 80)

        logger.info(
            f"[POLY] {symbol} | RSI={rsi:.1f} + News={news_sentiment:+.2f} "
            f"→ {side} ({final_confidence:.1%} confidence, ${bet_size:.2f})"
        )

        return {
            "success": True,
            "market_id": market_id,
            "symbol": symbol,
            "rsi": rsi,
            "news_sentiment": news_sentiment,
            "side": side,
            "yes_price": yes_price,
            "bet_size": round(bet_size, 2),
            "rsi_confidence": round(rsi_confidence, 2),
            "final_confidence": round(final_confidence, 2),
            "sentiment_boost": round(sentiment_boost, 2),
            "timestamp": datetime.now().isoformat()
        }

    async def get_position_status(self, market_id: str) -> Optional[Dict]:
        """Bir pozisyonun durumunu kontrol et."""
        return self.positions.get(market_id)

    async def close_position(self, market_id: str) -> Dict:
        """Pozisyonu kapat."""
        if market_id not in self.positions:
            return {"success": False, "error": "Pozisyon bulunamadı"}

        pos = self.positions.pop(market_id)
        return {
            "success": True,
            "closed_position": pos,
            "timestamp": datetime.now().isoformat()
        }


# ─── Örnek kullanım ─────────────────────────────────────────────────────────

async def demo():
    """Demo: Polymarket pazarlarını listele."""
    async with PolymarketClient() as client:
        markets = await client.search_markets("bitcoin")

        print(f"\n[POLYMARKET] Bitcoin tahmin pazarları:\n")
        for i, m in enumerate(markets[:5], 1):
            print(f"  {i}. {m.get('title', 'N/A')[:60]}")
            print(f"     Likidite: ${m.get('liquidity', 0):,.0f}")
            print()


if __name__ == "__main__":
    # asyncio.run(demo())
    pass
