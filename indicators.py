# indicators.py -- Teknik indikatorler: RSI + MACD + Bollinger Bands
#
# 3 INDIKATOR BIRLIKTE NASIL CALISIR?
#
# RSI (Momentum):
#   < 35 = asiri satilmis → AL firsati
#   > 65 = asiri alinmis → SAT firsati
#
# MACD (Trend):
#   MACD > Signal = yukselis trendi (bullish crossover)
#   MACD < Signal = dusus trendi (bearish crossover)
#
# BOLLINGER BANDS (Volatilite):
#   Fiyat < Alt bant = asiri ucuz → AL firsati
#   Fiyat > Ust bant = asiri pahali → SAT firsati
#   Bantlar daraliyor = buyuk hareket yakinda
#
# KOMBINASYON STRATEJISI:
#   GUCLU AL:  RSI<35 + MACD bullish + Fiyat<BB_alt  (3/3 sinyal)
#   NORMAL AL: RSI<35 + (MACD bullish VEYA Fiyat<BB_alt)  (2/3 sinyal)
#   GUCLU SAT: RSI>65 + MACD bearish + Fiyat>BB_ust  (3/3 sinyal)
#   HOLD:      Sinyaller uyusmuyor

import pandas as pd
import ta
import config


def add_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> pd.DataFrame:
    """RSI ekle."""
    rsi = ta.momentum.RSIIndicator(close=df["close"], window=period)
    df["rsi"] = rsi.rsi()
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD ekle: macd, macd_signal, macd_diff (histogram)."""
    macd = ta.trend.MACD(close=df["close"], window_fast=fast, window_slow=slow, window_sign=signal)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"]   = macd.macd_diff()  # histogram
    return df


def add_bollinger(df: pd.DataFrame, window: int = 20, std: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands ekle: bb_upper, bb_middle, bb_lower, bb_width."""
    bb = ta.volatility.BollingerBands(close=df["close"], window=window, window_dev=std)
    df["bb_upper"]  = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"]  = bb.bollinger_lband()
    df["bb_width"]  = bb.bollinger_wband()  # bant genisligi (volatilite)
    return df


def add_all_indicators(df: pd.DataFrame, rsi_period: int = config.RSI_PERIOD) -> pd.DataFrame:
    """Tum indikatorleri ekle."""
    df = add_rsi(df, period=rsi_period)
    df = add_macd(df)
    df = add_bollinger(df)
    return df


def get_latest_rsi(df: pd.DataFrame) -> float:
    """Son RSI degeri."""
    return float(df["rsi"].iloc[-2])


def get_latest_macd(df: pd.DataFrame) -> dict:
    """Son MACD degerleri."""
    i = -2  # son kapanmis mum
    return {
        "macd":       round(float(df["macd"].iloc[i]), 4) if not pd.isna(df["macd"].iloc[i]) else 0,
        "signal":     round(float(df["macd_signal"].iloc[i]), 4) if not pd.isna(df["macd_signal"].iloc[i]) else 0,
        "histogram":  round(float(df["macd_diff"].iloc[i]), 4) if not pd.isna(df["macd_diff"].iloc[i]) else 0,
        "bullish":    float(df["macd"].iloc[i]) > float(df["macd_signal"].iloc[i]) if not pd.isna(df["macd"].iloc[i]) else False,
    }


def get_latest_bollinger(df: pd.DataFrame) -> dict:
    """Son Bollinger Bands degerleri."""
    i = -2
    price = float(df["close"].iloc[i])
    upper = float(df["bb_upper"].iloc[i]) if not pd.isna(df["bb_upper"].iloc[i]) else price
    lower = float(df["bb_lower"].iloc[i]) if not pd.isna(df["bb_lower"].iloc[i]) else price
    middle = float(df["bb_middle"].iloc[i]) if not pd.isna(df["bb_middle"].iloc[i]) else price
    width = float(df["bb_width"].iloc[i]) if not pd.isna(df["bb_width"].iloc[i]) else 0

    return {
        "upper":      round(upper, 2),
        "middle":     round(middle, 2),
        "lower":      round(lower, 2),
        "width":      round(width, 4),
        "below_lower": price < lower,   # AL sinyali
        "above_upper": price > upper,   # SAT sinyali
        "squeeze":     width < 0.02,    # Bantlar daralmiyor = buyuk hareket yakinda
    }


def get_combined_signal(rsi: float, macd: dict, bb: dict,
                        oversold: float = 35, overbought: float = 65) -> dict:
    """
    3 indikatorun birlesik sinyali.

    Return:
      {
        "signal": "STRONG_BUY" | "BUY" | "SELL" | "STRONG_SELL" | "HOLD",
        "confidence": 0.0 - 1.0,
        "reasons": ["RSI oversold", "MACD bullish", ...]
      }
    """
    buy_signals = 0
    sell_signals = 0
    reasons = []

    # RSI
    if rsi < oversold:
        buy_signals += 1
        reasons.append(f"RSI={rsi:.1f} < {oversold}")
    elif rsi > overbought:
        sell_signals += 1
        reasons.append(f"RSI={rsi:.1f} > {overbought}")

    # MACD
    if macd.get("bullish"):
        buy_signals += 1
        reasons.append("MACD bullish crossover")
    else:
        sell_signals += 1
        reasons.append("MACD bearish")

    # Bollinger
    if bb.get("below_lower"):
        buy_signals += 1
        reasons.append("Fiyat < BB alt bant")
    elif bb.get("above_upper"):
        sell_signals += 1
        reasons.append("Fiyat > BB ust bant")

    # Karar
    if buy_signals >= 3:
        signal = "STRONG_BUY"
        confidence = 0.95
    elif buy_signals >= 2:
        signal = "BUY"
        confidence = 0.70
    elif sell_signals >= 3:
        signal = "STRONG_SELL"
        confidence = 0.95
    elif sell_signals >= 2:
        signal = "SELL"
        confidence = 0.70
    else:
        signal = "HOLD"
        confidence = 0.30

    return {
        "signal": signal,
        "confidence": confidence,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "reasons": reasons,
    }
