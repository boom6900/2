# -*- coding: utf-8 -*-

import os
from datetime import datetime, timedelta

import pandas as pd
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ─────────────────────────────
# تحميل .env
# ─────────────────────────────

load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
SECRET  = os.getenv("APCA_API_SECRET_KEY")

if not API_KEY or not SECRET:
    raise ValueError("❌ API Keys غير موجودة في .env")

# ─────────────────────────────
# DATA
# ─────────────────────────────

class Data:
    def __init__(self):
        self.client = StockHistoricalDataClient(
            api_key=API_KEY,
            secret_key=SECRET
        )

    def fetch(self, symbol):
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=TimeFrame.Day,
                start=datetime.now() - timedelta(days=120)
            )

            bars = self.client.get_stock_bars(request)

            df = bars.df

            if df is None or df.empty:
                return None

            df = df.reset_index()
            df = df[df["symbol"] == symbol.upper()]

            return df

        except Exception as e:
            return None

# ─────────────────────────────
# RSI
# ─────────────────────────────

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# ─────────────────────────────
# ANALYSIS
# ─────────────────────────────

def analyze(symbol):
    data = Data()
    df = data.fetch(symbol)

    if df is None or len(df) < 30:
        return "❌ فشل في جلب البيانات"

    close = df["close"]

    ema9  = close.ewm(span=9).mean().iloc[-1]
    ema20 = close.ewm(span=20).mean().iloc[-1]
    ema50 = close.ewm(span=50).mean().iloc[-1]

    rsi = calculate_rsi(close).iloc[-1]
    price = close.iloc[-1]

    trend = "صاعد 📈" if ema9 > ema20 > ema50 else "هابط 📉"

    return f"""
📊 تحليل {symbol.upper()}

السعر: {price:.2f}
الاتجاه: {trend}

EMA 9/20/50:
{ema9:.2f} / {ema20:.2f} / {ema50:.2f}

RSI: {rsi:.1f}
"""

# ─────────────────────────────
# ENTRY
# ─────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print(analyze(sys.argv[1]))
    else:
        print("اكتب رمز سهم مثل: snap")