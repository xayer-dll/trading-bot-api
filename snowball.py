# snowball.py -- Kartopu Etkisi + Kaldirac Sistemi
#
# KALDIRAC NASIL CALISIR?
#   Bakiye: $1,000 | Kaldirac: 5x
#   Marjin (cebinden cikan): $50 (%5 risk)
#   Pozisyon buyuklugu: $50 × 5 = $250
#
#   Fiyat %1 artarsa:
#     Kaldirac yok: $250 × 0.01 = $2.50 kar
#     5x kaldirac:  $250 × 0.01 = $2.50 kar (ama $50 marjinle)
#     → Marjin bazli ROI: $2.50 / $50 = %5 (5x daha fazla)
#
#   Fiyat %1 duserse:
#     5x kaldirac:  $250 × 0.01 = $2.50 zarar
#     → Marjin bazli ROI: -$2.50 / $50 = -%5
#
#   LIKIDASON: Fiyat -%20 duserse (100/5 = %20)
#     → Tum marjin gider, pozisyon zorla kapatilir
#
# ONEMLI: Kaldirac hem kari hem zarari buyutur!

import os
from datetime import datetime
from typing import Dict, Optional

# ─── SNOWBALL AYARLARI ───────────────────────────────────────────────────────

BASE_RISK_PCT = 0.05        # %5 - baslangic (marjin olarak)
WIN_STREAK_BOOST = 0.01     # Her ardisik kazancta +%1
LOSE_STREAK_PENALTY = 0.015 # Her ardisik kayipta -%1.5
MIN_RISK_PCT = 0.02         # Minimum %2
MAX_RISK_PCT = 0.12         # Maksimum %12
MIN_TRADE_AMOUNT = 5.0      # Minimum islem (marjin)
COMPOUND_ENABLED = True


class SnowballEngine:
    """
    Kartopu motoru + kaldirac destegi.

    Marjin = cebinden cikan para
    Pozisyon = marjin × kaldirac
    PnL = fiyat degisimi × pozisyon buyuklugu
    """

    def __init__(self, initial_balance: float = 100.0, leverage: int = 5):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.leverage = leverage

        # Seri takibi
        self.win_streak = 0
        self.lose_streak = 0
        self.total_wins = 0
        self.total_losses = 0
        self.total_trades = 0

        # PnL takibi
        self.total_pnl = 0.0
        self.best_trade = 0.0
        self.worst_trade = 0.0
        self.trade_history = []

        # Risk parametreleri
        self.current_risk_pct = BASE_RISK_PCT

        # Likidason koruma
        self.liquidation_pct = 1.0 / leverage  # 5x → %20 dususte likidasyon

        print(
            f"[SNOWBALL] Motor basladi | Bakiye: ${initial_balance:.2f} | "
            f"Kaldirac: {leverage}x | Risk: %{BASE_RISK_PCT*100:.1f} | "
            f"Likidasyon: %{self.liquidation_pct*100:.0f}"
        )

    def calculate_trade_amount(self) -> float:
        """
        Marjin miktarini hesapla (cebinden cikan).
        Gercek pozisyon = marjin × kaldirac
        """
        # Dinamik risk yuzdesi
        if self.win_streak > 0:
            boost = self.win_streak * WIN_STREAK_BOOST
            self.current_risk_pct = min(MAX_RISK_PCT, BASE_RISK_PCT + boost)
        elif self.lose_streak > 0:
            penalty = self.lose_streak * LOSE_STREAK_PENALTY
            self.current_risk_pct = max(MIN_RISK_PCT, BASE_RISK_PCT - penalty)
        else:
            self.current_risk_pct = BASE_RISK_PCT

        # Marjin = bakiye × risk yuzdesi
        margin = self.current_balance * self.current_risk_pct

        # Limitlere uydur
        margin = max(MIN_TRADE_AMOUNT, margin)
        margin = min(self.current_balance * 0.3, margin)  # Max %30 (kaldiracta daha dikkatli)

        return round(margin, 2)

    def calculate_position_size(self) -> float:
        """Kaldiracli pozisyon buyuklugu."""
        margin = self.calculate_trade_amount()
        return round(margin * self.leverage, 2)

    def calculate_leveraged_pnl(self, entry_price: float, exit_price: float, margin: float) -> float:
        """
        Kaldiracli PnL hesapla.

        entry_price: giris fiyati
        exit_price: cikis fiyati
        margin: kullanilan marjin (cebinden cikan)

        Formul:
          position_size = margin × leverage
          quantity = position_size / entry_price
          pnl = (exit_price - entry_price) × quantity
        """
        position_size = margin * self.leverage
        quantity = position_size / entry_price
        pnl = (exit_price - entry_price) * quantity
        return round(pnl, 4)

    def record_trade(self, pnl: float, symbol: str = "BTCUSDT", margin_used: float = 0):
        """Islem kaydet — PnL zaten kaldiracli hesaplanmis olmali."""
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

        # ROI hesapla (marjin bazli)
        roi = (pnl / margin_used * 100) if margin_used > 0 else 0

        # Islem gecmisi
        self.trade_history.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "symbol": symbol,
            "pnl": round(pnl, 4),
            "margin": round(margin_used, 2),
            "roi_pct": round(roi, 1),
            "leverage": self.leverage,
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
            f"[SNOWBALL] {symbol} | PnL: {pnl:+.4f} ({self.leverage}x) | "
            f"ROI: {roi:+.1f}% | "
            f"Bakiye: ${self.current_balance:.2f} ({growth:+.1f}%) | "
            f"Seri: {streak_info}"
        )

    def get_stats(self) -> Dict:
        """Dashboard icin istatistikler."""
        win_rate = (self.total_wins / self.total_trades * 100) if self.total_trades > 0 else 0
        growth = ((self.current_balance / self.initial_balance) - 1) * 100
        margin = self.calculate_trade_amount()
        position = self.calculate_position_size()

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
            "next_margin": margin,
            "next_position": position,
            "leverage": self.leverage,
            "liquidation_pct": round(self.liquidation_pct * 100, 1),
            "compound_enabled": COMPOUND_ENABLED,
        }

    def sync_balance(self, real_balance: float):
        """Binance'dan gercek bakiyeyi sync et."""
        self.current_balance = real_balance

    def set_leverage(self, leverage: int):
        """Kaldiraci degistir."""
        self.leverage = max(1, min(20, leverage))
        self.liquidation_pct = 1.0 / self.leverage
        print(f"[SNOWBALL] Kaldirac: {self.leverage}x | Likidasyon: %{self.liquidation_pct*100:.0f}")
