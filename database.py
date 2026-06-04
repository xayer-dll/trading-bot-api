# database.py — SQLite ile kalıcı veri depolama.
#
# Neden SQLite?
#   • Sunucu restart olunca RAM'deki tüm veriler gider
#   • SQLite dosyaya yazar → restart'tan sonra da veri kalır
#   • Kurulum gerektirmez, Python ile birlikte gelir
#
# Saklanan veriler:
#   trades       → Her BUY/SELL işlemi
#   stats        → Çift başına istatistikler
#   equity       → Bakiye geçmişi (equity curve)

import sqlite3
import os
from datetime import datetime
from typing import Optional

# Veritabanı dosya yolu
# Render'da /tmp kalıcı değil ama local'de proje klasöründe kalır
DB_PATH = os.environ.get("DB_PATH", "trading_bot.db")


def _connect():
    """Bağlantı kur, yabancı anahtar desteğini aç."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tablolar yoksa oluştur. Uygulama başlangıcında çağrılır."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol     TEXT    NOT NULL,
            action     TEXT    NOT NULL,   -- BUY / SELL
            price      REAL    NOT NULL,
            rsi        REAL,
            pnl        REAL,               -- sadece SELL için
            reason     TEXT,               -- RSI-SELL, STOP-LOSS, TAKE-PROFIT
            timestamp  TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS stats (
            symbol        TEXT PRIMARY KEY,
            total_trades  INTEGER DEFAULT 0,
            win_trades    INTEGER DEFAULT 0,
            total_pnl     REAL    DEFAULT 0,
            win_rate      REAL    DEFAULT 0,
            best_trade    REAL    DEFAULT 0,
            worst_trade   REAL    DEFAULT 0,
            updated_at    TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS equity (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            balance    REAL    NOT NULL,
            timestamp  TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
        CREATE INDEX IF NOT EXISTS idx_equity_created ON equity(created_at);
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Veritabani hazir: {DB_PATH}")


# ─── TRADE İŞLEMLERİ ─────────────────────────────────────────────────────────

def save_trade(symbol: str, action: str, price: float, rsi: float,
               pnl: Optional[float] = None, reason: str = ""):
    """Bir işlemi veritabanına yazar."""
    conn = _connect()
    conn.execute(
        """INSERT INTO trades (symbol, action, price, rsi, pnl, reason, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (symbol, action, round(price, 2), round(rsi, 2),
         round(pnl, 4) if pnl is not None else None,
         reason, datetime.now().strftime("%H:%M:%S"))
    )
    conn.commit()
    conn.close()


def load_trades(symbol: Optional[str] = None, limit: int = 50) -> list:
    """Son N işlemi yükler."""
    conn = _connect()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM trades WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
            (symbol, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── İSTATİSTİK İŞLEMLERİ ────────────────────────────────────────────────────

def save_stats(symbol: str, stats: dict):
    """Çift istatistiklerini günceller (UPSERT)."""
    conn = _connect()
    conn.execute("""
        INSERT INTO stats (symbol, total_trades, win_trades, total_pnl,
                           win_rate, best_trade, worst_trade, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(symbol) DO UPDATE SET
            total_trades = excluded.total_trades,
            win_trades   = excluded.win_trades,
            total_pnl    = excluded.total_pnl,
            win_rate     = excluded.win_rate,
            best_trade   = excluded.best_trade,
            worst_trade  = excluded.worst_trade,
            updated_at   = excluded.updated_at
    """, (
        symbol,
        stats.get("total_trades", 0),
        stats.get("win_trades",   0),
        stats.get("total_pnl",    0.0),
        stats.get("win_rate",     0.0),
        stats.get("best_trade",   0.0),
        stats.get("worst_trade",  0.0),
    ))
    conn.commit()
    conn.close()


def load_stats(symbol: str) -> dict:
    """Çiftin kayıtlı istatistiklerini yükler."""
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM stats WHERE symbol=?", (symbol,)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "total_trades": 0, "win_trades": 0, "total_pnl": 0.0,
        "win_rate": 0.0, "best_trade": 0.0, "worst_trade": 0.0
    }


# ─── BAKİYE EĞRİSİ ───────────────────────────────────────────────────────────

def save_equity(balance: float):
    """Bakiye snapshot'ı kaydeder."""
    conn = _connect()
    conn.execute(
        "INSERT INTO equity (balance, timestamp) VALUES (?, ?)",
        (round(balance, 2), datetime.now().strftime("%H:%M"))
    )
    # 200'den fazla kayıt varsa eskilerini sil
    conn.execute(
        "DELETE FROM equity WHERE id NOT IN (SELECT id FROM equity ORDER BY id DESC LIMIT 200)"
    )
    conn.commit()
    conn.close()


def load_equity(limit: int = 120) -> list:
    """Son N bakiye kaydını yükler."""
    conn = _connect()
    rows = conn.execute(
        "SELECT balance, timestamp as t FROM equity ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    # Grafikte kronolojik sıra lazım
    return [dict(r) for r in reversed(rows)]


# ─── GENEL İSTATİSTİK ────────────────────────────────────────────────────────

def get_db_summary() -> dict:
    """Veritabanı özet istatistikleri."""
    conn = _connect()
    total  = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    sells  = conn.execute("SELECT COUNT(*) FROM trades WHERE action='SELL'").fetchone()[0]
    equity = conn.execute("SELECT COUNT(*) FROM equity").fetchone()[0]
    size   = os.path.getsize(DB_PATH) / 1024 if os.path.exists(DB_PATH) else 0
    conn.close()
    return {
        "total_trades":    total,
        "sell_trades":     sells,
        "equity_records":  equity,
        "db_size_kb":      round(size, 1),
    }
