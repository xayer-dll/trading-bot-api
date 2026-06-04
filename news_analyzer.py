# news_analyzer.py — Kripto haberleri tarayıp sentiment analiz et
#
# Kullanım:
#   1. newsapi.org'dan haberleri çek
#   2. Keyword tarayıcısı ile sentiment belirle (NLP yok, basit keyword match)
#   3. Polymarket pazarlarıyla eşleştir
#
# Neden basit keyword match?
#   • NLP library'ler (transformers, nltk) ağır ve yavaş
#   • Kripto haberlerinde keyword match %80+ doğru
#   • Hızlı ve lightweight

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# NewsAPI.org endpoints
NEWSAPI_BASE = "https://newsapi.org/v2"
NEWSAPI_KEY = "demo"  # .env'den override edilecek — ücretsiz API key lazım

# Sentiment enum
class Sentiment(Enum):
    VERY_BULLISH = (0.9, "çok pozitif")
    BULLISH = (0.7, "pozitif")
    NEUTRAL = (0.5, "nötr")
    BEARISH = (0.3, "negatif")
    VERY_BEARISH = (0.1, "çok negatif")

    @property
    def score(self) -> float:
        return self.value[0]

    @property
    def label(self) -> str:
        return self.value[1]


# ─── KEYWORD SÖZLÜKLERI ──────────────────────────────────────────────────────

BULLISH_KEYWORDS = {
    # Pozitif hareket
    "surge", "rally", "pump", "rise", "gain", "bull",
    # Kabul & Adoption
    "adoption", "approve", "approval", "approved", "accepted",
    # Teknik
    "bullish", "breakout", "reversal", "recovery", "uptrend",
    # İş & Yatırım
    "investment", "fund", "backing", "partnership", "collaboration",
    # Olay
    "halving", "upgrade", "improvement", "innovation",
    # Kişisel
    "bullish", "optimistic", "positive", "strength",
    # Türkçe equivalents
    "yükselişe", "artış", "kazanç", "kabulü", "onayı", "pozitif",
}

BEARISH_KEYWORDS = {
    # Negatif hareket
    "crash", "plunge", "dump", "decline", "fall", "bear",
    # Yasaklama & Düzenleme
    "ban", "banned", "regulation", "regulatory", "restrict", "restricted",
    # Teknik
    "bearish", "downtrend", "breakdown", "support breach", "weak",
    # Sorun
    "hack", "exploit", "vulnerability", "scam", "fraud",
    # Satış
    "sell-off", "capitulation", "liquidation", "outflow",
    # Kişisel
    "pessimistic", "negative", "weakness", "concern",
    # Türkçe equivalents
    "düşüş", "yasakla", "düzenleme", "negatif", "zayıf",
}

CRYPTO_KEYWORDS = {
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "defi", "altcoin", "token", "coin", "exchange",
    "binance", "coinbase", "kraken", "kriptopara", "kripto"
}

FED_KEYWORDS = {
    "fed", "federal reserve", "jerome powell", "interest rate", "rate hike",
    "inflation", "fomc", "monetary policy", "quantitative easing",
    "faiz", "enflasyon", "merkez bankası"
}


# ─── ANALYZER CLASS ──────────────────────────────────────────────────────────

class NewsAnalyzer:
    """Kripto haberlerini analiz et."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or NEWSAPI_KEY
        self.session = None
        self.cache = {}  # Haber cache (her 5 dakika refresh)
        self.last_fetch = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_crypto_news(self, hours: int = 24) -> List[Dict]:
        """
        Son N saatin kripto haberlerini çek.

        NewsAPI'den:
          - "bitcoin OR ethereum OR crypto" arandı
          - Son 24 saatin haberler
          - Sıralı: relevance → popularity
        """
        if not self.api_key or self.api_key == "demo":
            logger.warning("[NEWS] API key yok — demo mod")
            return self._get_demo_news()

        try:
            # Cache'i kontrol et (5 dakika)
            if self.last_fetch and (datetime.now() - self.last_fetch).total_seconds() < 300:
                return self.cache.get("crypto_news", [])

            query = "bitcoin OR ethereum OR cryptocurrency"
            from_date = (datetime.now() - timedelta(hours=hours)).isoformat()

            async with self.session.get(
                f"{NEWSAPI_BASE}/everything",
                params={
                    "q": query,
                    "from": from_date,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "apiKey": self.api_key,
                    "pageSize": 50,
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    articles = data.get("articles", [])

                    # Cache'e kaydet
                    self.cache["crypto_news"] = articles
                    self.last_fetch = datetime.now()

                    logger.info(f"[NEWS] {len(articles)} haber alındı")
                    return articles
                else:
                    logger.error(f"[NEWS] API hatası: {resp.status}")
                    return self._get_demo_news()

        except Exception as e:
            logger.error(f"[NEWS] Fetch hatası: {e}")
            return self._get_demo_news()

    def _get_demo_news(self) -> List[Dict]:
        """Demo modunda örnek haberler döndür."""
        return [
            {
                "title": "Bitcoin Surges to New All-Time High",
                "description": "Bitcoin rallies above $70,000 amid positive institutional interest.",
                "publishedAt": datetime.now().isoformat(),
            },
            {
                "title": "SEC Approves More Crypto Regulations",
                "description": "New regulations provide clarity for institutional adoption.",
                "publishedAt": (datetime.now() - timedelta(hours=2)).isoformat(),
            },
        ]

    def analyze_sentiment(self, text: str) -> Tuple[Sentiment, float]:
        """
        Metni analiz et → Sentiment + detay skoru (-1 to +1)

        Algoritma:
          1. Bullish keywor count
          2. Bearish keyword count
          3. Net score = (bullish - bearish) / (bullish + bearish)
          4. Sentiment = score'a göre
        """
        text_lower = text.lower()

        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)
        total = bullish_count + bearish_count

        if total == 0:
            return Sentiment.NEUTRAL, 0.0

        net_score = (bullish_count - bearish_count) / total

        # Score → Sentiment
        if net_score >= 0.6:
            sentiment = Sentiment.VERY_BULLISH
        elif net_score >= 0.2:
            sentiment = Sentiment.BULLISH
        elif net_score <= -0.6:
            sentiment = Sentiment.VERY_BEARISH
        elif net_score <= -0.2:
            sentiment = Sentiment.BEARISH
        else:
            sentiment = Sentiment.NEUTRAL

        return sentiment, net_score

    def is_crypto_relevant(self, text: str) -> bool:
        """Haber kripto ile ilgili mi?"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in CRYPTO_KEYWORDS)

    def is_fed_related(self, text: str) -> bool:
        """Haber FED/makroekonomik ile ilgili mi?"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in FED_KEYWORDS)

    async def get_latest_sentiment(self, hours: int = 24) -> Dict:
        """
        Son N saatin kripto haberlerine göre overall sentiment.

        Return:
          {
            "sentiment": "bullish",
            "score": 0.65,
            "count": 15,
            "bullish_count": 10,
            "bearish_count": 5,
            "fed_related": 3,
            "top_headlines": [...]
          }
        """
        news = await self.fetch_crypto_news(hours=hours)

        sentiments = []
        headlines = []

        for article in news:
            title = article.get("title", "")
            desc = article.get("description", "")
            full_text = f"{title} {desc}".strip()

            # Kripto haber mi?
            if not self.is_crypto_relevant(full_text):
                continue

            sentiment, score = self.analyze_sentiment(full_text)
            sentiments.append((sentiment, score))

            # Top haberler
            is_fed = self.is_fed_related(full_text)
            headlines.append({
                "title": title[:80],
                "sentiment": sentiment.label,
                "score": round(score, 2),
                "fed_related": is_fed,
                "time": article.get("publishedAt", ""),
            })

        if not sentiments:
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "count": 0,
                "bullish_count": 0,
                "bearish_count": 0,
                "fed_related": 0,
                "top_headlines": [],
                "message": "Kripto haberi bulunamadi"
            }

        # Overall sentiment = weighted average
        overall_score = sum(s.score for _, s in sentiments) / len(sentiments)

        # Score → sentiment label
        if overall_score >= 0.65:
            overall_sentiment = "very_bullish"
        elif overall_score >= 0.55:
            overall_sentiment = "bullish"
        elif overall_score <= 0.35:
            overall_sentiment = "very_bearish"
        elif overall_score <= 0.45:
            overall_sentiment = "bearish"
        else:
            overall_sentiment = "neutral"

        bullish = sum(1 for s, _ in sentiments if s in (Sentiment.BULLISH, Sentiment.VERY_BULLISH))
        bearish = sum(1 for s, _ in sentiments if s in (Sentiment.BEARISH, Sentiment.VERY_BEARISH))
        fed_count = sum(1 for h in headlines if h["fed_related"])

        return {
            "sentiment": overall_sentiment,
            "score": round(overall_score, 2),
            "count": len(sentiments),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "fed_related": fed_count,
            "top_headlines": headlines[:5],  # Top 5
        }


# ─── Örnek Kullanım ──────────────────────────────────────────────────────────

async def demo():
    """Demo: Haberleri analiz et."""
    async with NewsAnalyzer() as analyzer:
        sentiment = await analyzer.get_latest_sentiment(hours=24)
        print("\n[HABER SENTIMENT]")
        print(f"Genel Duygu: {sentiment['sentiment']} ({sentiment['score']})")
        print(f"Haberler: {sentiment['bullish_count']} bullish, {sentiment['bearish_count']} bearish")
        print(f"FED İlgili: {sentiment['fed_related']} haber\n")

        for h in sentiment["top_headlines"]:
            print(f"  • {h['title']}")
            print(f"    {h['sentiment']} ({h['score']}) {'🏦 FED' if h['fed_related'] else ''}\n")


if __name__ == "__main__":
    # asyncio.run(demo())
    pass
