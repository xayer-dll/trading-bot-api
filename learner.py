# learner.py -- Gecmis islemlerden ogrenen ve OTOMATIK UYGULAYAN strateji motoru
#
# FELSEFE:
#   Elle coin cikarmiyoruz. Sistem kendi ogrenir, kendi karar verir.
#   2 ay sonra hangi coinin karli oldugunu sistem biliyor olmali.
#
# OTOMATIK KARARLAR (oneri degil, eylem):
#   1. COIN BYPASS: Min 10 islem + win rate < %30 → o coine islem yapma
#      Win rate > %50'ye cikinca → otomatik geri al (rehabilitasyon)
#   2. RSI ESIGI: En karli RSI bolgesini bulur, state'e uygular
#   3. SAAT FILTRESI: Kotu saatlerde yeni pozisyon acma
#   4. MACD ZORUNLULUGU: Veri MACD'siz daha iyiyse filtre kaldirilir
#
# MINIMUM VERI ESIGI:
#   10 islem olmadan hicbir karari uygulamaz — az veriyle yanlis karar vermez

import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# Otomatik karar esikleri
MIN_TRADES_FOR_DECISION  = 10   # En az bu kadar islem olmadan karar yok
BYPASS_WIN_RATE_THRESHOLD = 0.30  # %30 alti → bypass
RECOVER_WIN_RATE_THRESHOLD = 0.50  # %50 ustu → bypass kaldir
BAD_HOUR_THRESHOLD        = 0.25  # %25 alti win rate → o saat kotu
GOOD_HOUR_MIN_TRADES      = 3    # Saat karari icin minimum islem


class TradeLearner:
    """
    Gecmis islemlerden ogrenen VE otomatik uygulayan strateji motoru.
    """

    def __init__(self):
        self.trades = []
        self.lessons = []
        self.recommendations = {}

        # Analiz verileri
        self.rsi_performance   = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.symbol_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.hour_performance  = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.signal_type_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.macd_accuracy = {
            "with_macd":    {"wins": 0, "total": 0},
            "without_macd": {"wins": 0, "total": 0},
        }

        # ── OTOMATIK KARARLAR (bunlar gercekten uygulanir) ──────────────
        self._bypassed_coins: Dict[str, str] = {}   # symbol → bypass sebebi
        self._bad_hours: List[int] = []              # Yeni pozisyon acilamayan saatler
        self._applied_rsi_oversold: Optional[float] = None  # Uygulanan RSI esigi

        print("[LEARNER] Otomatik ogrenme + uygulama motoru basladi")
        print(f"[LEARNER] Esikler: bypass<{BYPASS_WIN_RATE_THRESHOLD*100:.0f}% | "
              f"rehabilite>{RECOVER_WIN_RATE_THRESHOLD*100:.0f}% | "
              f"min_islem={MIN_TRADES_FOR_DECISION}")

    # ─────────────────────────────────────────────────────────────────────
    def record_trade(self, trade: Dict):
        """Islem kaydet ve analiz et."""
        self.trades.append(trade)
        self.trades = self.trades[-1000:]  # Son 1000 islem

        if trade.get("action") != "SELL":
            return

        pnl = trade.get("pnl", 0)
        if pnl is None:
            return

        is_win  = pnl > 0
        symbol  = trade.get("symbol", "?")
        rsi_entry = trade.get("rsi_at_entry", 50)

        # 1. RSI performansi (5'er grupla)
        rsi_bucket = int(rsi_entry // 5) * 5
        p = self.rsi_performance[rsi_bucket]
        p["wins" if is_win else "losses"] += 1
        p["total_pnl"] += pnl

        # 2. Coin performansi
        sp = self.symbol_performance[symbol]
        sp["wins" if is_win else "losses"] += 1
        sp["total_pnl"] += pnl

        # 3. Saat performansi
        try:
            hour = datetime.fromisoformat(trade["timestamp"]).hour
        except Exception:
            hour = datetime.now().hour
        hp = self.hour_performance[hour]
        hp["wins" if is_win else "losses"] += 1
        hp["total_pnl"] += pnl

        # 4. Sinyal tipi
        sig_type = trade.get("signal_type", "BUY")
        stp = self.signal_type_performance[sig_type]
        stp["wins" if is_win else "losses"] += 1
        stp["total_pnl"] += pnl

        # 5. MACD onay performansi
        macd_bull = trade.get("macd_bullish")
        if macd_bull is not None:
            key = "with_macd" if macd_bull else "without_macd"
            self.macd_accuracy[key]["total"] += 1
            if is_win:
                self.macd_accuracy[key]["wins"] += 1

        # Her 5 islemde kararlari guncelle
        sell_count = sum(1 for t in self.trades if t.get("action") == "SELL")
        if sell_count > 0 and sell_count % 5 == 0:
            self._apply_decisions()

    # ─────────────────────────────────────────────────────────────────────
    def _apply_decisions(self):
        """
        Veriye bakarak KARARLAR UYGULA.
        Sadece oneri degil — gercekten bypass, saat filtresi, RSI degisikl.
        """
        self.lessons = []
        self.recommendations = {}
        changed = []

        # ── 1. COIN BYPASS / REHABILITASYON ─────────────────────────────
        for sym, perf in self.symbol_performance.items():
            total = perf["wins"] + perf["losses"]
            if total < MIN_TRADES_FOR_DECISION:
                continue  # Yeterli veri yok — karar verme

            wr = perf["wins"] / total

            if wr < BYPASS_WIN_RATE_THRESHOLD and sym not in self._bypassed_coins:
                # Yeni bypass
                reason = f"%{wr*100:.0f} win ({total} islem, pnl={perf['total_pnl']:+.2f})"
                self._bypassed_coins[sym] = reason
                changed.append(f"BYPASS: {sym} ({reason})")
                print(f"[LEARNER] OTOMATIK BYPASS: {sym} — {reason}")

            elif wr >= RECOVER_WIN_RATE_THRESHOLD and sym in self._bypassed_coins:
                # Rehabilitasyon — tekrar al
                del self._bypassed_coins[sym]
                changed.append(f"REHABILITE: {sym} (win rate %{wr*100:.0f}'e yukseldi)")
                print(f"[LEARNER] REHABILITASYON: {sym} — tekrar aktif, win=%{wr*100:.0f}")

        # ── 2. KOTU SAAT FILTRESI ────────────────────────────────────────
        bad_hours = []
        for hour, perf in self.hour_performance.items():
            total = perf["wins"] + perf["losses"]
            if total < GOOD_HOUR_MIN_TRADES:
                continue
            wr = perf["wins"] / total
            if wr <= BAD_HOUR_THRESHOLD:
                bad_hours.append(hour)

        if bad_hours != self._bad_hours:
            self._bad_hours = bad_hours
            if bad_hours:
                changed.append(f"KOTU SAATLER guncellendi: {sorted(bad_hours)}")
                print(f"[LEARNER] Kotu saatler: {sorted(bad_hours)} — bu saatlerde yeni pozisyon yok")

        # ── 3. RSI ESIGI ONERISI ─────────────────────────────────────────
        best_rsi = None
        best_wr  = 0
        for rsi_level, perf in self.rsi_performance.items():
            total = perf["wins"] + perf["losses"]
            if total >= 5:
                wr = perf["wins"] / total
                if wr > best_wr:
                    best_wr  = wr
                    best_rsi = rsi_level

        if best_rsi is not None:
            suggested = best_rsi + 5  # RSI 20 bolgesi → esik 25 olsun
            suggested = max(20, min(40, suggested))  # Guvenli aralik
            if suggested != self._applied_rsi_oversold:
                self._applied_rsi_oversold = suggested
                self.recommendations["rsi_oversold"] = suggested
                changed.append(f"RSI esigi onerisi: {suggested} (en iyi: {best_rsi}-{best_rsi+5} @ %{best_wr*100:.0f})")

        # ── 4. DERSLER (loglama icin) ────────────────────────────────────
        if self._bypassed_coins:
            self.lessons.append(
                f"Bypass'taki coinler ({len(self._bypassed_coins)}): "
                + ", ".join(self._bypassed_coins.keys())
            )
        if self._bad_hours:
            self.lessons.append(f"Kotu saatler: {sorted(self._bad_hours)}")

        profitable = [(s, p) for s, p in self.symbol_performance.items()
                      if p["wins"] + p["losses"] >= MIN_TRADES_FOR_DECISION
                      and p["wins"] / (p["wins"] + p["losses"]) >= 0.60]
        if profitable:
            best_str = ", ".join(
                f"{s}(%{p['wins']/(p['wins']+p['losses'])*100:.0f})" for s, p in
                sorted(profitable, key=lambda x: x[1]["wins"]/(x[1]["wins"]+x[1]["losses"]), reverse=True)[:5]
            )
            self.lessons.append(f"Karli coinler: {best_str}")

        macd_w = self.macd_accuracy["with_macd"]
        macd_wo = self.macd_accuracy["without_macd"]
        if macd_w["total"] >= 5 and macd_wo["total"] >= 3:
            wr_w  = macd_w["wins"] / macd_w["total"]
            wr_wo = macd_wo["wins"] / macd_wo["total"]
            self.lessons.append(
                f"MACD onayli: %{wr_w*100:.0f} win | MACD'siz: %{wr_wo*100:.0f} win"
            )
            self.recommendations["require_macd"] = wr_w > wr_wo

        if changed:
            print(f"[LEARNER] {len(changed)} karar uygulandi:")
            for c in changed:
                print(f"  → {c}")

    # ─────────────────────────────────────────────────────────────────────
    def should_trade(self, symbol: str) -> bool:
        """
        Bu coine islem yapilmali mi?

        False donerse:
          - Yeterli veri var VE win rate esigin altinda (bypass)
          - Simdi kotu saat (yeni pozisyon acma)
        """
        # Coin bypass kontrolu
        if symbol in self._bypassed_coins:
            perf = self.symbol_performance[symbol]
            total = perf["wins"] + perf["losses"]
            wr = perf["wins"] / total if total > 0 else 0
            print(f"  [{symbol}] BYPASS: {self._bypassed_coins[symbol]} — atliyor")
            return False

        # Kotu saat kontrolu
        current_hour = datetime.now().hour
        if current_hour in self._bad_hours:
            print(f"  [{symbol}] KOTU SAAT ({current_hour}:00) — yeni pozisyon yok")
            return False

        return True

    def get_bypassed_coins(self) -> Dict[str, str]:
        """Simdi bypass'ta olan coinler."""
        return dict(self._bypassed_coins)

    def get_bad_hours(self) -> List[int]:
        """Simdi kotu saat listesi."""
        return sorted(self._bad_hours)

    def get_recommendations(self) -> Dict:
        """API endpoint icin tam durum."""
        sym_data = {}
        for sym, perf in self.symbol_performance.items():
            total = perf["wins"] + perf["losses"]
            sym_data[sym] = {
                **perf,
                "total": total,
                "win_rate": round(perf["wins"] / total * 100, 1) if total > 0 else 0,
                "bypassed": sym in self._bypassed_coins,
            }

        return {
            "total_analyzed": sum(1 for t in self.trades if t.get("action") == "SELL"),
            "lessons": self.lessons,
            "recommendations": self.recommendations,
            "auto_decisions": {
                "bypassed_coins": self._bypassed_coins,
                "bad_hours":      self._bad_hours,
                "applied_rsi":    self._applied_rsi_oversold,
            },
            "data": {
                "rsi_performance":    dict(self.rsi_performance),
                "symbol_performance": sym_data,
                "macd_performance":   self.macd_accuracy,
                "hour_performance":   dict(self.hour_performance),
            },
        }
