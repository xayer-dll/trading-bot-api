# learner.py -- Gecmis islemlerden ogrenen strateji motoru
#
# NE YAPIYOR?
#   1. Her islemi kaydeder ve analiz eder
#   2. Hangi RSI seviyesinde alim karli?
#   3. Hangi saatlerde islem daha basarili?
#   4. Hangi coinler daha karli?
#   5. MACD/BB sinyalleri ne kadar dogu?
#   6. Bu bilgilerle strateji parametrelerini OTOMATIK ayarlar
#
# ORNEK OGRENME:
#   "RSI 28'de alim yaptigimda %80 kazandim ama RSI 34'te aldigimda %40 kazandim"
#   → Sonuc: RSI esigini 30'a dusur (daha az ama daha kaliteli sinyal)
#
#   "MACD onayiyla yapilan islemler %70 kazandi, MACD'siz %45 kazandi"
#   → Sonuc: MACD onayini zorunlu tut

import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class TradeLearner:
    """
    Gecmis islemlerden ogrenen strateji optimizasyonu.
    """

    def __init__(self):
        self.trades = []               # Tum islem gecmisi
        self.lessons = []              # Ogrenilen dersler
        self.recommendations = {}      # Aktif oneriler

        # Analiz verileri
        self.rsi_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.symbol_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0, "trades": 0})
        self.hour_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.signal_type_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})
        self.macd_accuracy = {"with_macd": {"wins": 0, "total": 0}, "without_macd": {"wins": 0, "total": 0}}

        print("[LEARNER] Ogrenme motoru basladi")

    def record_trade(self, trade: Dict):
        """
        Islem kaydet ve analiz et.

        trade: {
            symbol, action, entry_price, exit_price,
            pnl, rsi_at_entry, rsi_at_exit,
            macd_bullish, bb_signal, signal_type,
            timestamp, reason
        }
        """
        self.trades.append(trade)
        self.trades = self.trades[-500:]  # Son 500 islem

        # Sadece kapanmis islemleri analiz et (SELL)
        if trade.get("action") != "SELL":
            return

        pnl = trade.get("pnl", 0)
        if pnl is None:
            return

        is_win = pnl > 0
        symbol = trade.get("symbol", "?")
        rsi_entry = trade.get("rsi_at_entry", 50)

        # 1. RSI seviye performansi
        # RSI'yi 5'er grupla: 0-5, 5-10, ..., 95-100
        rsi_bucket = int(rsi_entry // 5) * 5
        perf = self.rsi_performance[rsi_bucket]
        if is_win:
            perf["wins"] += 1
        else:
            perf["losses"] += 1
        perf["total_pnl"] += pnl

        # 2. Coin performansi
        sp = self.symbol_performance[symbol]
        sp["trades"] += 1
        sp["total_pnl"] += pnl
        if is_win:
            sp["wins"] += 1
        else:
            sp["losses"] += 1

        # 3. Saat performansi
        try:
            hour = datetime.now().hour
            hp = self.hour_performance[hour]
            if is_win:
                hp["wins"] += 1
            else:
                hp["losses"] += 1
            hp["total_pnl"] += pnl
        except Exception:
            pass

        # 4. Sinyal tipi performansi
        sig_type = trade.get("signal_type", "BUY")
        stp = self.signal_type_performance[sig_type]
        if is_win:
            stp["wins"] += 1
        else:
            stp["losses"] += 1
        stp["total_pnl"] += pnl

        # 5. MACD onay performansi
        macd_bull = trade.get("macd_bullish")
        if macd_bull is not None:
            key = "with_macd" if macd_bull else "without_macd"
            self.macd_accuracy[key]["total"] += 1
            if is_win:
                self.macd_accuracy[key]["wins"] += 1

        # Her 10 islemde oneriler guncelle
        sell_count = sum(1 for t in self.trades if t.get("action") == "SELL")
        if sell_count > 0 and sell_count % 10 == 0:
            self._generate_recommendations()

    def _generate_recommendations(self):
        """Verilerden strateji onerileri olustur."""
        self.lessons = []
        self.recommendations = {}

        # 1. En iyi RSI alim seviyeleri
        best_rsi = None
        best_rsi_winrate = 0
        for rsi_level, perf in self.rsi_performance.items():
            total = perf["wins"] + perf["losses"]
            if total >= 3:  # En az 3 islem
                wr = perf["wins"] / total
                if wr > best_rsi_winrate:
                    best_rsi_winrate = wr
                    best_rsi = rsi_level

        if best_rsi is not None:
            self.lessons.append(
                f"En basarili alim RSI={best_rsi}-{best_rsi+5} bolgesinde "
                f"(kazanma orani: %{best_rsi_winrate*100:.0f})"
            )
            # RSI esigi onerisi
            if best_rsi < 30:
                self.recommendations["rsi_oversold"] = best_rsi + 5
                self.lessons.append(f"ONERI: RSI esigini {best_rsi+5}'e dusur — daha kaliteli sinyal")
            elif best_rsi > 35:
                self.recommendations["rsi_oversold"] = best_rsi
                self.lessons.append(f"ONERI: RSI esigini {best_rsi}'e cikar — daha fazla firsat")

        # 2. En karli coinler
        profitable_coins = []
        losing_coins = []
        for sym, perf in self.symbol_performance.items():
            if perf["trades"] >= 3:
                wr = perf["wins"] / perf["trades"] if perf["trades"] > 0 else 0
                if wr >= 0.6:
                    profitable_coins.append((sym, wr, perf["total_pnl"]))
                elif wr < 0.4:
                    losing_coins.append((sym, wr, perf["total_pnl"]))

        if profitable_coins:
            coins_str = ", ".join(f"{s} (%{w*100:.0f})" for s, w, _ in profitable_coins)
            self.lessons.append(f"Karli coinler: {coins_str}")

        if losing_coins:
            coins_str = ", ".join(f"{s} (%{w*100:.0f})" for s, w, _ in losing_coins)
            self.lessons.append(f"Zarari coinler: {coins_str} — azalt veya cikar")
            self.recommendations["avoid_symbols"] = [s for s, _, _ in losing_coins]

        # 3. MACD etkinligi
        with_macd = self.macd_accuracy["with_macd"]
        without_macd = self.macd_accuracy["without_macd"]

        if with_macd["total"] >= 3 and without_macd["total"] >= 3:
            wr_with = with_macd["wins"] / with_macd["total"]
            wr_without = without_macd["wins"] / without_macd["total"]

            if wr_with > wr_without + 0.1:
                self.lessons.append(
                    f"MACD onayli islemler daha basarili: "
                    f"%{wr_with*100:.0f} vs %{wr_without*100:.0f}"
                )
                self.recommendations["require_macd"] = True
            elif wr_without > wr_with + 0.1:
                self.lessons.append(
                    f"MACD onayi OLUMSUZ etki yapiyor: "
                    f"%{wr_with*100:.0f} vs %{wr_without*100:.0f}"
                )
                self.recommendations["require_macd"] = False

        # 4. En iyi saatler
        best_hours = []
        worst_hours = []
        for hour, perf in self.hour_performance.items():
            total = perf["wins"] + perf["losses"]
            if total >= 2:
                wr = perf["wins"] / total
                if wr >= 0.7:
                    best_hours.append((hour, wr))
                elif wr <= 0.3:
                    worst_hours.append((hour, wr))

        if best_hours:
            hours_str = ", ".join(f"{h}:00 (%{w*100:.0f})" for h, w in best_hours)
            self.lessons.append(f"En iyi saatler: {hours_str}")

        if worst_hours:
            hours_str = ", ".join(f"{h}:00 (%{w*100:.0f})" for h, w in worst_hours)
            self.lessons.append(f"Kotu saatler: {hours_str} — bu saatlerde dikkatli ol")

        # 5. STRONG vs NORMAL sinyal karsilastirmasi
        strong = self.signal_type_performance.get("STRONG_BUY", {"wins": 0, "losses": 0})
        normal = self.signal_type_performance.get("BUY", {"wins": 0, "losses": 0})
        s_total = strong["wins"] + strong["losses"]
        n_total = normal["wins"] + normal["losses"]

        if s_total >= 2 and n_total >= 2:
            s_wr = strong["wins"] / s_total
            n_wr = normal["wins"] / n_total
            self.lessons.append(
                f"STRONG_BUY kazanma: %{s_wr*100:.0f} vs Normal BUY: %{n_wr*100:.0f}"
            )

        if self.lessons:
            print(f"[LEARNER] {len(self.lessons)} ders ogrendi:")
            for l in self.lessons:
                print(f"  → {l}")

    def get_recommendations(self) -> Dict:
        """Mevcut oneriler."""
        return {
            "lessons": self.lessons,
            "recommendations": self.recommendations,
            "data": {
                "rsi_performance": dict(self.rsi_performance),
                "symbol_performance": dict(self.symbol_performance),
                "macd_accuracy": self.macd_accuracy,
                "total_trades_analyzed": len(self.trades),
            }
        }

    def should_trade(self, symbol: str) -> bool:
        """Bu coine islem yapilmali mi? (ogrenme bazli)"""
        avoid = self.recommendations.get("avoid_symbols", [])
        if symbol in avoid:
            logger.info(f"[LEARNER] {symbol} kacinilacak listede — islem yapma")
            return False
        return True
