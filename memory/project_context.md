---
name: trading-bot-project
description: Binance testnet RSI trading bot project - Python, uv managed, Windows Turkish terminal
metadata:
  type: project
---

Binance Testnet üzerinde çalışan RSI trading botu projesi.

**Why:** Kullanıcı kripto trading botlarını öğrenmek istiyor, sıfır deneyim.

**How to apply:** Türkçe açıklamalar ekle, her adımı açıkla, özel Unicode semboller Windows cp1254 terminalinde çalışmıyor — ASCII semboller kullan ([OK], [HATA], [!] vb).

**Stack:**
- Python 3.14.3, uv paket yöneticisi
- Çalıştırmak için: `uv run python <dosya.py>` (C:\Users\FURKAN\Desktop\trade\trading-bot içinde)
- uv path: C:\Users\FURKAN\.local\bin\uv.exe

**Modüller:** config.py, connection.py, data.py, indicators.py, strategy.py, executor.py, bot.py, arbitrage.py

**İleride eklenecek:** Triangular arbitrage execution (şimdi sadece tespit var)
