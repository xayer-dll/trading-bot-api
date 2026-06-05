# auditor.py -- Otomatik islem denetcisi
#
# HER 5 ISLEMDE:
#   1. PnL hesaplamalarini dogrula
#   2. Cross-symbol karisma kontrolu (eski bug)
#   3. Mantik disi kar/zarar tespiti
#   4. Bakiye tutarliligi kontrolu
#   5. Anomali raporu olustur
#
# NEDEN LAZIM?
#   %400 kar sanip bug oldugunu ogrendik.
#   Bir daha olmasin diye her islemi dogruluyoruz.

import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Anomali esikleri
MAX_SINGLE_TRADE_PNL_PCT = 0.10    # Tek islemde bakiyenin max %10'u kadar PnL beklenir
MAX_PNL_PER_PRICE_MOVE = 2.0       # Fiyat degisimi × miktar × kaldirac × 2'den fazla PnL su anomali
MIN_PRICE_FOR_TRADE = 0.001        # $0'dan buyuk fiyat olmali


class TradeAuditor:
    """
    Islem denetcisi — her 5 islemde otomatik tarama yapar.
    """

    def __init__(self, leverage: int = 5):
        self.leverage = leverage
        self.audit_interval = 5  # Her 5 islemde denetle
        self.trade_buffer = []   # Denetlenmemis islemler
        self.audit_reports = []  # Gecmis denetim raporlari
        self.total_audited = 0
        self.bugs_found = 0

    def add_trade(self, trade: Dict) -> Optional[Dict]:
        """
        Islem ekle. Her 5 islemde otomatik denetim yapar.

        trade: {
            symbol, action, entry_price, exit_price,
            quantity, pnl, reason, margin, timestamp
        }

        Return: Anomali varsa rapor dict, yoksa None
        """
        self.trade_buffer.append(trade)

        # Aninda tek islem kontrolu
        instant_check = self._check_single_trade(trade)
        if instant_check:
            logger.warning(f"[AUDIT] ANOMALI: {instant_check['message']}")

        # Her 5 islemde toplu denetim
        if len(self.trade_buffer) >= self.audit_interval:
            report = self.run_audit()
            self.trade_buffer = []
            return report

        return instant_check

    def _check_single_trade(self, trade: Dict) -> Optional[Dict]:
        """Tek islemi aninda kontrol et."""
        issues = []

        symbol = trade.get("symbol", "?")
        action = trade.get("action", "?")
        entry = trade.get("entry_price", 0)
        exit_p = trade.get("exit_price", 0)
        qty = trade.get("quantity", 0)
        pnl = trade.get("pnl", 0)
        margin = trade.get("margin", 0)

        # Sadece SELL islemlerini denetle (PnL olan)
        if action != "SELL" or pnl is None:
            return None

        # 1. Fiyat kontrolu
        if entry <= MIN_PRICE_FOR_TRADE or exit_p <= MIN_PRICE_FOR_TRADE:
            issues.append(f"Gecersiz fiyat: giris=${entry} cikis=${exit_p}")

        # 2. PnL hesap dogrulama
        if entry > 0 and qty > 0:
            expected_pnl = round((exit_p - entry) * qty * self.leverage, 4)
            pnl_diff = abs(pnl - expected_pnl)

            if pnl_diff > 1.0:  # $1'den fazla fark varsa
                issues.append(
                    f"PnL UYUMSUZ: raporlanan={pnl:.4f} beklenen={expected_pnl:.4f} "
                    f"fark={pnl_diff:.4f}"
                )

        # 3. Cross-symbol kontrolu (eski bug)
        # Eger fiyat farki %50'den fazlaysa, muhtemelen yanlis coin
        if entry > 0 and exit_p > 0:
            price_ratio = max(entry, exit_p) / min(entry, exit_p)
            if price_ratio > 1.5:  # %50'den fazla fark
                issues.append(
                    f"CROSS-SYMBOL SUPHESI: giris=${entry:.2f} cikis=${exit_p:.2f} "
                    f"oran={price_ratio:.1f}x — farkli coinler karismiyi olabilir!"
                )

        # 4. Asiri buyuk PnL kontrolu
        if margin > 0 and abs(pnl) > 0:
            roi = abs(pnl) / margin
            if roi > 0.5:  # %50'den fazla ROI tek islemde supheeli
                issues.append(
                    f"ASIRI PnL: ${pnl:+.4f} marjin=${margin:.2f} ROI=%{roi*100:.0f} "
                    f"— tek islemde %50+ ROI su supheeli"
                )

        if issues:
            self.bugs_found += 1
            return {
                "type": "ANOMALY",
                "symbol": symbol,
                "trade": trade,
                "issues": issues,
                "message": f"{symbol}: {len(issues)} sorun bulundu",
                "timestamp": datetime.now().isoformat(),
            }

        return None

    def run_audit(self) -> Dict:
        """5 islemlik toplu denetim."""
        self.total_audited += len(self.trade_buffer)

        report = {
            "audit_id": len(self.audit_reports) + 1,
            "trades_checked": len(self.trade_buffer),
            "total_audited": self.total_audited,
            "issues": [],
            "summary": {},
            "timestamp": datetime.now().isoformat(),
        }

        # Her islemi kontrol et
        symbols_seen = {}
        pnl_list = []

        for t in self.trade_buffer:
            sym = t.get("symbol", "?")
            action = t.get("action", "?")
            pnl = t.get("pnl")

            # Symbol bazli islem sayisi
            if sym not in symbols_seen:
                symbols_seen[sym] = {"buys": 0, "sells": 0, "pnl": 0}
            if action == "BUY":
                symbols_seen[sym]["buys"] += 1
            elif action == "SELL":
                symbols_seen[sym]["sells"] += 1
                if pnl is not None:
                    symbols_seen[sym]["pnl"] += pnl
                    pnl_list.append(pnl)

            # Tek islem kontrolu
            check = self._check_single_trade(t)
            if check:
                report["issues"].append(check)

        # 5. Seri kontrolu — arka arkaya ayni yonde islem supheeli
        buy_streak = 0
        sell_streak = 0
        for t in self.trade_buffer:
            if t.get("action") == "BUY":
                buy_streak += 1
                sell_streak = 0
            elif t.get("action") == "SELL":
                sell_streak += 1
                buy_streak = 0

        if buy_streak >= 4:
            report["issues"].append({
                "type": "WARNING",
                "message": f"4+ ardisik BUY — pozisyon birikiyor olabilir"
            })
        if sell_streak >= 4:
            report["issues"].append({
                "type": "WARNING",
                "message": f"4+ ardisik SELL — panik satis olabilir"
            })

        # Ozet
        wins = sum(1 for p in pnl_list if p > 0)
        losses = sum(1 for p in pnl_list if p < 0)
        total_pnl = sum(pnl_list)

        report["summary"] = {
            "symbols": symbols_seen,
            "wins": wins,
            "losses": losses,
            "total_pnl": round(total_pnl, 4),
            "avg_pnl": round(total_pnl / len(pnl_list), 4) if pnl_list else 0,
            "clean": len(report["issues"]) == 0,
        }

        # Raporu kaydet
        self.audit_reports.append(report)
        self.audit_reports = self.audit_reports[-20:]  # Son 20 rapor

        status = "TEMIZ" if report["summary"]["clean"] else f"{len(report['issues'])} SORUN"
        logger.info(f"[AUDIT] Denetim #{report['audit_id']}: {status}")
        print(f"[AUDIT] Denetim #{report['audit_id']}: {len(self.trade_buffer)} islem → {status}")

        return report

    def get_status(self) -> Dict:
        """Denetim durumu."""
        return {
            "total_audited": self.total_audited,
            "bugs_found": self.bugs_found,
            "pending": len(self.trade_buffer),
            "next_audit_in": self.audit_interval - len(self.trade_buffer),
            "last_report": self.audit_reports[-1] if self.audit_reports else None,
        }
