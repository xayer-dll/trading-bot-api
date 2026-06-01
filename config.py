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
CANDLE_LIMIT    = 100
LOOP_INTERVAL   = 10        # Her kaç saniyede bir kontrol? (10-300 arası)

# Takip edilecek çiftler (multi-pair)
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

# RSI
RSI_PERIOD      = 14
RSI_OVERSOLD    = 30
RSI_OVERBOUGHT  = 70

# Risk yönetimi
TRADE_AMOUNT    = 10.0
STOP_LOSS_PCT   = 0.02       # %2
TAKE_PROFIT_PCT = 0.03       # %3
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
