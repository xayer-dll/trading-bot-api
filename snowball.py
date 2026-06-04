# snowball.py -- Kartopu Etkisi: Kazanci geri yatir, parayi buyut.
#
# NEDEN BU DOSYA?
#   executor.py her seferinde sabit $10 aliyor.
#   Ama kartopu etkisi icin:
#     - Kazanc varsa → islem miktarini artir
#     - Kayip varsa → islem miktarini azalt (risk koruma)
#     - Bakiye buyudukce → daha buyuk islemler
#
# FORMUL (Kelly Criterion - basitlestirilmis):
#   risk_per_trade = bakiye * risk_yuzdesi
#   risk_yuzdesi = base_risk * (1 + kazanc_serisi * 0.1)
#
# ORNEK:
#   Baslangic: $100 bakiye, %5 risk = $5 islem
#   1. kazanc: $100 → $103 (PnL +$3)
#   2. kazanc: $103 → $106.5, risk artik %5.5 = $5.86 islem
#   3. kazanc: $106.5 → $113, risk %6 = $6.78 islem
#   ... kartopu buyuyor!

import os
from datetime import datetime
from typing import Dict, Optional

# ─── SNOWBALL AYARLARI ───────────────────────────────────────────────────────

# Base risk: bakiyenin yuzde kaci ile islem yap
BASE_RISK_PCT = 0.05        # %5 - baslangic

# Kazanc serisinde risk artisi
WIN_STREAK_BOOST = 0.01     # Her ardisik kazancta +%1 risk ekle

# Kayip serisinde risk azalisi
LOSE_STREAK_PENALTY = 0.015 # Her ardisik kayipta -%1.5 risk azalt

# Min/Max risk limitleri (bakiyenin yuzde kaci)
MIN_RISK_PCT = 0.02         # Minimum %2 — cok kucuk islem yapma
MAX_RISK_PCT = 0.15         # Maksimum %15 — cok buyuk risk alma

# Minimum islem miktari (USDT)
MIN_TRADE_AMOUNT = 5.0      # Binance minimum

# Compound modu: kazanci geri yatir
COMPOUND_ENABLED = True


class SnowballEngine:
    """
    Kartopu motoru: kazanci buyut, kayipda koru.

    Her islem sonrasi:
      1. Bakiyeye bak
      2. Kazanc/kayip serisine bak
      3. Risk yuzdesini ayarla
      4. Sonraki islem miktarini hesapla
    """

    def __init__(self, initial_balance: float = 100.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # Seri takibi
        self.win_streak = 0       # Ardisik kazanc sayisi
        self.lose_streak = 0      # Ardisik kayip sayisi
        self.total_wins = 0
        self.total_losses = 0
        self.total_trades = 0

        # PnL takibi
        self.total_pnl = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.trade_history = []   # Son 100 islem

        # Risk parametreleri
        self.current_risk_pct = BASE_RISK_PCT

        print(f"[SNOWBALL] Motor basladi | Bakiye: ${initial_balance:.2f} | Risk: %{BASE_RISK_PCT*100:.1f}")

    def calculate_trade_amount(self) -> float:
        """
        Sonraki islem icin ne kadar USDT kullanilacagini hesapla.

        Mantik:
          1. Base risk = bakiye * risk_pct
          2. Kazanc serisinde risk biraz artar (cesaret)
          3. Kayip serisinde risk azalir (koruma)
          4. Min/Max limitlere uydur
        """
        # Dinamik risk yuzdesi
        if self.win_streak > 0:
            # Kazaniyoruz → biraz daha cesur ol
            boost = self.win_streak * WIN_STREAK_BOOST
            self.current_risk_pct = min(MAX_RISK_PCT, BASE_RISK_PCT + boost)
        elif self.lose_streak > 0:
            # Kaybediyoruz → geri cekil
            penalty = self.lose_streak * LOSE_STREAK_PENALTY
            self.current_risk_pct = max(MIN_RISK_PCT, BASE_RISK_PCT - penalty)
        else:
            self.current_risk_pct = BASE_RISK_PCT

        # Islem miktari = bakiye * risk yuzdesi
        amount = self.current_balance * self.current_risk_pct

        # Limitlere uydur
        amount = max(MIN_TRADE_AMOUNT, amount)
        amount = min(self.current_balance * 0.5, amount)  # Bakiyenin max %50'si

        return round(amount, 2)

    def record_trade(self, pnl: float, symbol: str = "BTCUSDT"):
        """
        Bir islem tamamlandiginda cagir.

        pnl > 0: kazanc
        pnl < 0: kayip
        pnl = 0: break-even
        """
        self.total_trades += 1
        self.total_pnl += pnl

        # Bakiyeyi guncelle
        if COMPOUND_ENABLED:
            self.current_balance += pnl

        # Seri takibi
        if pnl > 0:
            self.total_wins += 1
            self.win_streak += 1
            self.lose_streak = 0
            self.best_trade = max(self.best_trade, pnl)
        elif pnl < 0:
            self.total_losses += 1
            self.lose_streak += 1
            self.win_streak = 0
            self.worst_trade = min(self.worst_trade, pnl)

        # Islem gecmisi
        self.trade_history.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "symbol": symbol,
            "pnl": round(pnl, 4),
            "balance_after": round(self.current_balance, 2),
            "risk_pct": round(self.current_risk_pct * 100, 1),
            "win_streak": self.win_streak,
            "lose_streak": self.lose_streak,
        })
        self.trade_history = self.trade_history[-100:]

        # Log
        growth = ((self.current_balance / self.initial_balance) - 1) * 100
        streak_info = f"W{self.win_streak}" if self.win_streak > 0 else f"L{self.lose_streak}"
        print(
            f"[SNOWBALL] {symbol} | PnL: {pnl:+.4f} | "
            f"Bakiye: ${self.current_balance:.2f} ({growth:+.1f}%) | "
            f"Seri: {streak_info} | "
            f"Risk: %{self.current_risk_pct*100:.1f}"
        )

    def get_stats(self) -> Dict:
        """Dashboard icin istatistikler."""
        win_rate = (self.total_wins / self.total_trades * 100) if self.total_trades > 0 else 0
        growth = ((self.current_balance / self.initial_balance) - 1) * 100

        return {
            "initial_balance": self.initial_balance,
            "current_balance": round(self.current_balance, 2),
            "total_pnl": round(self.total_pnl, 4),
            "growth_pct": round(growth, 2),
            "total_trades": self.total_trades,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "win_rate": round(win_rate, 1),
            "win_streak": self.win_streak,
            "lose_streak": self.lose_streak,
            "best_trade": round(self.best_trade, 4),
            "worst_trade": round(self.worst_trade, 4),
            "current_risk_pct": round(self.current_risk_pct * 100, 1),
            "next_trade_amount": self.calculate_trade_amount(),
            "compound_enabled": COMPOUND_ENABLED,
        }

    def sync_balance(self, real_balance: float):
        """Binance'dan gercek bakiyeyi sync et."""
        self.current_balance = real_balance
