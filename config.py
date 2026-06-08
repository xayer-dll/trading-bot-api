# config.py — Tüm ayarlar burada toplanır.

# ─── SPOT API (testnet.binance.vision) ──────────────────────────────────────
API_KEY    = "ppwVKGpl9VUcLcWADfuPK5YCbM6RXVR4VcSHbF2yFAqnEnxFj6ySOAnKWMyssSWv"
API_SECRET = "BBJ0eCFQMoX7htmliSW6nQPlkmac9D6Kde6Ln7BG4zbpfctrPWBgO9X0Fllv9Zrr"
TESTNET_URL = "https://testnet.binance.vision"

# ─── FUTURES API (testnet.binancefuture.com) ─────────────────────────────────
# Futures için AYRI API key lazım:
#   1. https://testnet.binancefuture.com adresine git
#   2. "API Key" butonuna bas, bir key oluştur
#   3. Aşağıdaki değerleri doldur
FUTURES_API_KEY    = "8uMOnXYpJPKFqjZxuUMqawPDij7hJvXTgYLz6Um8MsQ1g74hVmat3DDp856jMf78"
FUTURES_API_SECRET = "Pb4JPMUl2f9EKpoQEqAIpD8Cp46taukOyPV0wx4e0VyWXS11uMh9VQuyzwfn4seH"
FUTURES_TESTNET_URL = "https://demo-fapi.binance.com"
FUTURES_ENABLED    = True
LEVERAGE           = 5          # Varsayılan kaldıraç (1-20)

# ─── İŞLEM PARAMETRELERİ ────────────────────────────────────────────────────
SYMBOL          = "BTCUSDT"
TIMEFRAME       = "1m"
CANDLE_LIMIT    = 250       # EMA200 trend filtresi icin 200+ mum lazim
LOOP_INTERVAL   = 10        # Her kaç saniyede bir kontrol? (10-300 arası)

# ─── DURUSTLUK / GERCEKCILIK ────────────────────────────────────────────────
TRADING_MODE    = "spot"    # "spot" = kaldirac YOK (durust). "futures" = gercek kaldirac
FEE_RATE        = 0.001     # Binance spot taker komisyonu %0.1 (her islem)
                            # Gidis-donus = %0.2, PnL'den dusulur

# ─── STRATEJI FILTRELERI (akilli bot) ───────────────────────────────────────
USE_TREND_FILTER  = True    # EMA200 ustunde degilse ALMA (dusen bicagi tutma)
EMA_TREND_PERIOD  = 200     # Trend yonu icin EMA periyodu
USE_VOLUME_FILTER = True    # Hacim ortalamasinin altindaysa ALMA (likit olmayan)
VOLUME_SMA_PERIOD = 20      # Hacim ortalamasi periyodu
USE_ATR_STOPS     = True    # Sabit % yerine volatiliteye gore dinamik stop
ATR_PERIOD        = 14      # ATR periyodu
ATR_STOP_MULT     = 1.5     # Stop-loss = giris - 1.5 x ATR
ATR_TP_MULT       = 2.5     # Take-profit = giris + 2.5 x ATR

# ─── MACD ZORUNLULUGU ───────────────────────────────────────────────────────
# Learner verisi: MACD onaylı %75 kazanıyor, onsuz sadece %22.
# True = BUY sinyali icin MACD bullish OLMAK ZORUNDA (en kritik filtre)
REQUIRE_MACD_FOR_BUY = True

# ─── MINIMUM KAR ESIGI ──────────────────────────────────────────────────────
# RSI-SELL sinyalinde komisyonu GECEN bir kar olmadan satma (penny-scalping engelleyen)
# 2.0 = komisyonun en az 2 kati kadar kar olmadan cikma (daha az islem, daha kaliteli)
MIN_PROFIT_FEE_MULTIPLIER = 2.0

# ─── TARANACAK COINLER ──────────────────────────────────────────────────────
# Elle coin cikarmiyoruz — Learner otomatik karar verir:
#   Min 10 islem sonrasi win rate < %30  → gecici bypass (islem yapma)
#   Win rate > %50'ye cikinca            → otomatik geri al
# 2 ay sonra sistem hangi coinin karli oldugunu kendi ogrenir.
SYMBOLS = [
    # --- BUYUK PIYASA ---
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    # --- ORTA PIYASA ---
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "UNIUSDT", "ETCUSDT",
    # --- DeFi ---
    "AAVEUSDT", "GRTUSDT", "MKRUSDT", "COMPUSDT",
    # --- L2 / YENI NESIL ---
    "ARBUSDT", "OPUSDT", "NEARUSDT", "APTUSDT",
    # --- KANITMIS PERFORMERS ---
    "ZRXUSDT", "RUNEUSDT",
    # --- DIGER ---
    "ALGOUSDT", "CRVUSDT", "LDOUSDT", "SNXUSDT",
]

# RSI — daha kaliteli girisler icin dusuruldu (Learner onerisi)
RSI_PERIOD      = 14
RSI_OVERSOLD    = 30        # 35→30: Learner: RSI 15-20 zonu %43 win → daha derin asirisatis
RSI_OVERBOUGHT  = 68        # 65→68: Daha az erken cikis

# Risk yonetimi
TRADE_AMOUNT    = 10.0
STOP_LOSS_PCT   = 0.015      # %1.5 (daha siki koruma)
TAKE_PROFIT_PCT = 0.025      # %2.5 (daha hizli kar al)
TRAILING_STOP   = False      # Trailing stop-loss aktif mi?

# ─── TELEGRAM BİLDİRİMLERİ ──────────────────────────────────────────────────
# Kurulum:
#   1. Telegram'da @BotFather'a yaz: /newbot
#   2. Bot adını gir → TOKEN gelecek
#   3. Botuna /start at
#   4. https://api.telegram.org/bot{TOKEN}/getUpdates → chat_id bul
TELEGRAM_TOKEN   = "8975752141:AAFr8fgqDjmReOqJE-Ag9ins0639KqpRXLg"
TELEGRAM_CHAT_ID = "1510581063"
TELEGRAM_ENABLED = True
