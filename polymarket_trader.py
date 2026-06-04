# polymarket_trader.py -- Gercek Polymarket islem modulu
#
# py-clob-client SDK kullanarak gercek islem yapar.
# OKX dogrulama gelip USDC yuklendikten sonra aktif edilecek.
#
# KULLANIM:
#   1. MetaMask private key'i .env'ye ekle: POLY_PRIVATE_KEY=0x...
#   2. USDC bakiye yukle (Polygon agi)
#   3. Bot otomatik islem yapar
#
# ONEMLI: Bu modul GERCEK PARA ile calisir!

import os
import logging
from typing import Optional, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Polymarket API
POLYMARKET_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

# Ayarlar
POLY_ENABLED = os.environ.get("POLY_ENABLED", "false").lower() == "true"
POLY_PRIVATE_KEY = os.environ.get("POLY_PRIVATE_KEY", "")
POLY_MAX_BET = float(os.environ.get("POLY_MAX_BET", "10"))  # Max $10 per trade


class PolymarketTrader:
    """
    Gercek Polymarket islem yapici.
    py-clob-client SDK ile calisiyor.
    """

    def __init__(self):
        self.client = None
        self.initialized = False
        self.positions: List[Dict] = []
        self.total_pnl = 0.0
        self.trade_count = 0

    def initialize(self) -> bool:
        """Polymarket client baslat."""
        if not POLY_ENABLED:
            logger.info("[POLY-TRADE] Devre disi (POLY_ENABLED=false)")
            return False

        if not POLY_PRIVATE_KEY:
            logger.error("[POLY-TRADE] Private key yok! POLY_PRIVATE_KEY env variable ekle")
            return False

        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds

            self.client = ClobClient(
                host=POLYMARKET_HOST,
                key=POLY_PRIVATE_KEY,
                chain_id=CHAIN_ID,
            )

            # API credentials olustur
            self.client.set_api_creds(self.client.create_or_derive_api_creds())

            self.initialized = True
            logger.info("[POLY-TRADE] Basarili! Gercek islem hazir.")
            return True

        except ImportError:
            logger.error("[POLY-TRADE] py-clob-client yuklu degil: pip install py-clob-client")
            return False
        except Exception as e:
            logger.error(f"[POLY-TRADE] Baslama hatasi: {e}")
            return False

    def get_balance(self) -> float:
        """USDC bakiyesini al."""
        if not self.initialized:
            return 0.0
        try:
            # Polymarket USDC bakiye
            return 0.0  # TODO: wallet balance check
        except Exception as e:
            logger.error(f"[POLY-TRADE] Bakiye hatasi: {e}")
            return 0.0

    def buy_yes(self, token_id: str, amount: float) -> Optional[Dict]:
        """
        YES tokeni satin al.

        token_id: Polymarket market token ID
        amount: USDC miktari ($)
        """
        if not self.initialized:
            return {"success": False, "error": "Client baslamadi"}

        if amount > POLY_MAX_BET:
            amount = POLY_MAX_BET
            logger.warning(f"[POLY-TRADE] Miktar limite dusuruldu: ${amount}")

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY

            order_args = OrderArgs(
                price=0.50,  # Limit fiyat (0.01-0.99)
                size=amount,
                side=BUY,
                token_id=token_id,
            )

            signed_order = self.client.create_order(order_args)
            result = self.client.post_order(signed_order, OrderType.GTC)

            self.trade_count += 1
            logger.info(f"[POLY-TRADE] YES ALIM | ${amount} | token={token_id[:12]}...")

            return {
                "success": True,
                "side": "YES",
                "amount": amount,
                "order": result,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"[POLY-TRADE] YES alim hatasi: {e}")
            return {"success": False, "error": str(e)}

    def buy_no(self, token_id: str, amount: float) -> Optional[Dict]:
        """NO tokeni satin al."""
        if not self.initialized:
            return {"success": False, "error": "Client baslamadi"}

        if amount > POLY_MAX_BET:
            amount = POLY_MAX_BET

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY

            # NO token = karsi token
            order_args = OrderArgs(
                price=0.50,
                size=amount,
                side=BUY,
                token_id=token_id,
            )

            signed_order = self.client.create_order(order_args)
            result = self.client.post_order(signed_order, OrderType.GTC)

            self.trade_count += 1
            logger.info(f"[POLY-TRADE] NO ALIM | ${amount} | token={token_id[:12]}...")

            return {
                "success": True,
                "side": "NO",
                "amount": amount,
                "order": result,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"[POLY-TRADE] NO alim hatasi: {e}")
            return {"success": False, "error": str(e)}

    def get_open_orders(self) -> List[Dict]:
        """Acik emirleri listele."""
        if not self.initialized:
            return []
        try:
            orders = self.client.get_orders()
            return orders if orders else []
        except Exception as e:
            logger.error(f"[POLY-TRADE] Emir listesi hatasi: {e}")
            return []

    def cancel_all(self) -> bool:
        """Tum acik emirleri iptal et."""
        if not self.initialized:
            return False
        try:
            self.client.cancel_all()
            logger.info("[POLY-TRADE] Tum emirler iptal edildi")
            return True
        except Exception as e:
            logger.error(f"[POLY-TRADE] Iptal hatasi: {e}")
            return False

    def get_status(self) -> Dict:
        """Trader durumu."""
        return {
            "enabled": POLY_ENABLED,
            "initialized": self.initialized,
            "trade_count": self.trade_count,
            "total_pnl": self.total_pnl,
            "max_bet": POLY_MAX_BET,
        }


# Tekil instance
trader = PolymarketTrader()
