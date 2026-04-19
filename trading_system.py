"""
╔══════════════════════════════════════════════════════════════╗
║         QUANT TRADING SYSTEM — نظام التداول الاحترافي        ║
║         Python 3.10+ | Alpaca API | Real-Time Data           ║
╚══════════════════════════════════════════════════════════════╝

الملفات المطلوبة:
  pip install alpaca-py yfinance pandas numpy requests python-dotenv
 # -*- coding: utf-8 -*-
chcp 65001
import sys
sys.stdout.reconfigure(encoding='utf-8')
متغيرات البيئة (.env):
  ALPACA_API_KEY=your_key_here
  ALPACA_SECRET_KEY=your_secret_here
  ALPACA_BASE_URL=https://paper-api.alpaca.markets   ← للتداول التجريبي
"""

# ──────────────────────────────────────────────────────────────
# 1. IMPORTS & CONFIGURATION
# ──────────────────────────────────────────────────────────────

import os
import json
import time
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

# Alpaca SDK
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("alpaca-py غير مثبت. سيتم استخدام yfinance")

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger("TradingSystem")

# ──────────────────────────────────────────────────────────────
# 2. CONFIGURATION
# ──────────────────────────────────────────────────────────────

class Config:
    # Alpaca credentials
    API_KEY    = os.getenv("ALPACA_API_KEY",    "DEMO_KEY")
    SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "DEMO_SECRET")
    BASE_URL   = os.getenv("ALPACA_BASE_URL",   "https://paper-api.alpaca.markets")

    # Risk management
    RISK_PER_TRADE   = 0.02   # 2% من رأس المال
    ATR_SL_MULT      = 1.5    # مضاعف ATR لوقف الخسارة
    RR_RATIO         = 2.5    # نسبة المخاطرة:المكافأة
    MIN_CONFIDENCE   = 55     # الحد الأدنى للثقة
    MIN_VOLUME_RATIO = 1.2    # الحد الأدنى لنسبة الفوليوم

    # Indicators periods
    EMA_FAST  = 9
    EMA_MED   = 20
    EMA_SLOW  = 50
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    BB_PERIOD  = 20
    MACD_FAST  = 12
    MACD_SLOW  = 26
    MACD_SIG   = 9
    LOOKBACK   = 100  # عدد الشموع المحملة

# ──────────────────────────────────────────────────────────────
# 3. DATA MODELS
# ──────────────────────────────────────────────────────────────

@dataclass
class TradeSignal:
    symbol:      str
    signal:      str          # BUY | SELL | NO TRADE
    confidence:  float        # 0-100
    strength:    str          # HIGH | MEDIUM | WEAK
    entry:       float
    stop_loss:   float
    take_profit: float
    rr_ratio:    float
    reason:      str
    pattern:     str
    regime:      str          # TRENDING_UP | TRENDING_DOWN | SIDEWAYS | HIGH_VOLATILITY
    price:       float
    change_pct:  float
    rsi:         float
    volume_ratio:float
    ema_fast:    float
    ema_med:     float
    ema_slow:    float
    support:     float
    resistance:  float
    atr:         float
    timestamp:   str

    def to_dict(self):
        return asdict(self)

    def print_report(self):
        """طباعة تقرير منسّق"""
        sig_icon = {"BUY": "🟢", "SELL": "🔴", "NO TRADE": "⚪"}.get(self.signal, "⚪")
        str_icon = {"HIGH": "◈", "MEDIUM": "◇", "WEAK": "○"}.get(self.strength, "○")
        regime_map = {
            "TRENDING_UP": "↗ صاعد", "TRENDING_DOWN": "↘ هابط",
            "SIDEWAYS": "→ عرضي", "HIGH_VOLATILITY": "⚡ متذبذب"
        }

        print("\n" + "═"*56)
        print(f"  {sig_icon}  {self.symbol}  —  {self.signal}")
        print("═"*56)
        print(f"  السعر الحالي   :  ${self.price:.2f}  ({self.change_pct:+.2f}%)")
        print(f"  الاتجاه        :  {regime_map.get(self.regime, self.regime)}")
        print(f"  النمط المكتشف  :  {self.pattern}")
        print(f"  السبب          :  {self.reason}")
        print(f"  الثقة          :  {str_icon} {self.confidence:.0f}%  [{self.strength}]")
        print("─"*56)
        if self.signal != "NO TRADE":
            print(f"  📌 دخول          :  ${self.entry:.2f}")
            print(f"  🛑 وقف الخسارة   :  ${self.stop_loss:.2f}")
            print(f"  🎯 هدف الربح     :  ${self.take_profit:.2f}")
            print(f"  📊 R:R Ratio     :  1:{self.rr_ratio:.1f}")
            print("─"*56)
        print(f"  RSI            :  {self.rsi:.1f}")
        print(f"  حجم التداول    :  {self.volume_ratio:.2f}x")
        print(f"  EMA {Config.EMA_FAST}/{Config.EMA_MED}/{Config.EMA_SLOW}     :  {self.ema_fast:.2f} / {self.ema_med:.2f} / {self.ema_slow:.2f}")
        print(f"  دعم / مقاومة   :  ${self.support:.2f} / ${self.resistance:.2f}")
        print(f"  ATR            :  ${self.atr:.2f}")
        print(f"  التوقيت        :  {self.timestamp}")
        print("═"*56 + "\n")


# ──────────────────────────────────────────────────────────────
# 4. DATA LAYER — جلب البيانات
# ──────────────────────────────────────────────────────────────

class MarketDataProvider:
    """
    طبقة البيانات — تدعم:
      1. Alpaca API (بيانات حقيقية مع مفاتيح)
      2. yfinance  (بديل مجاني)
    """

    def __init__(self):
        self.alpaca_client = None
        if ALPACA_AVAILABLE and Config.API_KEY != "DEMO_KEY":
            try:
                self.alpaca_client = StockHistoricalDataClient(
                    Config.API_KEY, Config.SECRET_KEY
                )
                log.info("✓ تم الاتصال بـ Alpaca API")
            except Exception as e:
                log.warning(f"Alpaca connection failed: {e}. Falling back to yfinance.")

    def fetch(self, symbol: str, bars: int = Config.LOOKBACK) -> Optional[pd.DataFrame]:
        """
        جلب بيانات OHLCV للسهم
        Returns: DataFrame بأعمدة [open, high, low, close, volume]
        """
        symbol = symbol.upper().strip()

        # ── محاولة Alpaca أولاً ──
        if self.alpaca_client:
            df = self._fetch_alpaca(symbol, bars)
            if df is not None and len(df) >= 30:
                log.info(f"✓ Alpaca: {len(df)} شمعة لـ {symbol}")
                return df

        # ── الرجوع لـ yfinance ──
        df = self._fetch_yfinance(symbol, bars)
        if df is not None:
            log.info(f"✓ yfinance: {len(df)} شمعة لـ {symbol}")
        return df

    def _fetch_alpaca(self, symbol: str, bars: int) -> Optional[pd.DataFrame]:
        """جلب بيانات Alpaca"""
        try:
            end   = datetime.now()
            start = end - timedelta(days=bars * 2)
            req   = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Hour,
                start=start, end=end,
                limit=bars
            )
            bars_data = self.alpaca_client.get_stock_bars(req)
            df = bars_data[symbol].df
            df = df[["open","high","low","close","volume"]].tail(bars)
            return df
        except Exception as e:
            log.debug(f"Alpaca fetch error: {e}")
            return None

    def _fetch_yfinance(self, symbol: str, bars: int) -> Optional[pd.DataFrame]:
        """جلب بيانات yfinance (مجاني)"""
        try:
            ticker = yf.Ticker(symbol)
            # جلب 1 ساعة — آخر 60 يوماً
            df = ticker.history(period="60d", interval="1h")
            if df.empty:
                # بيانات يومية إذا فشلت الساعية
                df = ticker.history(period="1y", interval="1d")
            if df.empty:
                return None
            df.columns = [c.lower() for c in df.columns]
            df = df[["open","high","low","close","volume"]].dropna().tail(bars)
            return df
        except Exception as e:
            log.error(f"yfinance error for {symbol}: {e}")
            return None

    def get_quote(self, symbol: str) -> dict:
        """جلب السعر الحالي فقط"""
        try:
            t = yf.Ticker(symbol.upper())
            info = t.fast_info
            return {
                "price":  round(info.last_price, 2),
                "change": round(info.last_price - info.previous_close, 2),
                "pct":    round((info.last_price - info.previous_close) / info.previous_close * 100, 2),
                "volume": int(info.last_volume),
                "name":   t.info.get("longName", symbol)
            }
        except:
            return {}


# ──────────────────────────────────────────────────────────────
# 5. TECHNICAL ANALYSIS ENGINE — محرك التحليل الفني
# ──────────────────────────────────────────────────────────────

class TechnicalAnalysis:

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta  = series.diff()
        gain   = delta.clip(lower=0)
        loss   = -delta.clip(upper=0)
        avg_g  = gain.ewm(com=period - 1, adjust=False).mean()
        avg_l  = loss.ewm(com=period - 1, adjust=False).mean()
        rs     = avg_g / avg_l.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series: pd.Series, fast=12, slow=26, signal=9) -> pd.DataFrame:
        ema_f  = TechnicalAnalysis.ema(series, fast)
        ema_s  = TechnicalAnalysis.ema(series, slow)
        line   = ema_f - ema_s
        sig    = TechnicalAnalysis.ema(line, signal)
        hist   = line - sig
        return pd.DataFrame({"macd": line, "signal": sig, "hist": hist})

    @staticmethod
    def bollinger(series: pd.Series, period=20, k=2) -> pd.DataFrame:
        mid   = series.rolling(period).mean()
        std   = series.rolling(period).std()
        return pd.DataFrame({
            "upper":  mid + k * std,
            "middle": mid,
            "lower":  mid - k * std,
            "width":  (mid + k*std - (mid - k*std)) / mid
        })

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"]  - df["close"].shift()).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(com=period - 1, adjust=False).mean()

    @staticmethod
    def pivot_levels(df: pd.DataFrame, lookback: int = 30) -> tuple:
        """اكتشاف الدعم والمقاومة من القمم والقيعان"""
        sl = df.tail(lookback)
        highs = sl["high"].values
        lows  = sl["low"].values

        swing_highs, swing_lows = [], []
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] \
               and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append(highs[i])
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] \
               and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append(lows[i])

        resistance = round(max(swing_highs) if swing_highs else highs.max(), 2)
        support    = round(min(swing_lows)  if swing_lows  else lows.min(),  2)
        return support, resistance

    @staticmethod
    def detect_regime(df: pd.DataFrame) -> str:
        """تحديد حالة السوق"""
        closes = df["close"]
        if len(closes) < 50:
            return "UNKNOWN"
        e20 = TechnicalAnalysis.ema(closes, 20).iloc[-1]
        e50 = TechnicalAnalysis.ema(closes, 50).iloc[-1]
        bb  = TechnicalAnalysis.bollinger(closes)
        bw  = bb["width"].iloc[-1]
        rng = (closes.tail(50).max() - closes.tail(50).min()) / closes.tail(50).iloc[0]

        if bw < 0.03:
            return "SIDEWAYS"
        if rng > 0.20:
            return "HIGH_VOLATILITY"
        if e20 > e50 * 1.005:
            return "TRENDING_UP"
        if e20 < e50 * 0.995:
            return "TRENDING_DOWN"
        return "SIDEWAYS"

    @staticmethod
    def compute_all(df: pd.DataFrame) -> dict:
        """حساب جميع المؤشرات دفعة واحدة"""
        c = df["close"]
        v = df["volume"]

        ema_f  = TechnicalAnalysis.ema(c, Config.EMA_FAST)
        ema_m  = TechnicalAnalysis.ema(c, Config.EMA_MED)
        ema_s  = TechnicalAnalysis.ema(c, Config.EMA_SLOW)
        rsi    = TechnicalAnalysis.rsi(c, Config.RSI_PERIOD)
        macd   = TechnicalAnalysis.macd(c, Config.MACD_FAST, Config.MACD_SLOW, Config.MACD_SIG)
        bb     = TechnicalAnalysis.bollinger(c, Config.BB_PERIOD)
        atr    = TechnicalAnalysis.atr(df, Config.ATR_PERIOD)
        sup, res = TechnicalAnalysis.pivot_levels(df)
        avg_v  = v.rolling(20).mean()
        vol_r  = (v / avg_v).fillna(1)
        regime = TechnicalAnalysis.detect_regime(df)

        return {
            "ema_fast":    round(ema_f.iloc[-1], 2),
            "ema_med":     round(ema_m.iloc[-1], 2),
            "ema_slow":    round(ema_s.iloc[-1], 2),
            "rsi":         round(rsi.iloc[-1], 2),
            "macd_line":   round(macd["macd"].iloc[-1], 4),
            "macd_signal": round(macd["signal"].iloc[-1], 4),
            "macd_hist":   round(macd["hist"].iloc[-1], 4),
            "bb_upper":    round(bb["upper"].iloc[-1], 2),
            "bb_lower":    round(bb["lower"].iloc[-1], 2),
            "atr":         round(atr.iloc[-1], 4),
            "support":     sup,
            "resistance":  res,
            "vol_ratio":   round(vol_r.iloc[-1], 2),
            "regime":      regime,
            # قيم الشمعة الأخيرة والسابقة
            "price":       round(c.iloc[-1], 2),
            "prev_close":  round(c.iloc[-2], 2),
            "prev_high":   round(df["high"].iloc[-2], 2),
            "prev_low":    round(df["low"].iloc[-2], 2),
            "high":        round(df["high"].iloc[-1], 2),
            "low":         round(df["low"].iloc[-1], 2),
        }


# ──────────────────────────────────────────────────────────────
# 6. SIGNAL ENGINE — محرك الإشارات
# ──────────────────────────────────────────────────────────────

class SignalEngine:

    @staticmethod
    def generate(symbol: str, ind: dict) -> TradeSignal:
        """
        خوارزمية اتخاذ القرار بنظام Confluence
        يشترط تحقق عدة شروط متزامنة قبل إعطاء أي إشارة
        """
        price      = ind["price"]
        prev_close = ind["prev_close"]
        support    = ind["support"]
        resistance = ind["resistance"]
        rsi        = ind["rsi"]
        vol_ratio  = ind["vol_ratio"]
        macd_hist  = ind["macd_hist"]
        atr        = ind["atr"]
        regime     = ind["regime"]
        ema_f      = ind["ema_fast"]
        ema_m      = ind["ema_med"]
        ema_s      = ind["ema_slow"]
        bb_upper   = ind["bb_upper"]
        bb_lower   = ind["bb_lower"]

        change_pct = round((price - prev_close) / prev_close * 100, 2)

        # ── قائمة الإشارات المحتملة ──
        candidates = []

        # ① BREAKOUT — كسر مقاومة
        broke_res = price > resistance and prev_close <= resistance * 1.002
        if broke_res:
            score  = 0
            score += 30 if vol_ratio > 1.5 else (20 if vol_ratio > 1.2 else 5)
            score += 20 if regime in ("TRENDING_UP",) else 0
            score += 15 if macd_hist > 0 else 0
            score += 15 if 50 < rsi < 72 else 0
            score += 10 if price > ema_m else 0
            candidates.append({
                "direction": "BUY", "score": score,
                "pattern": "BREAKOUT",
                "reason": f"كسر مقاومة ${resistance:.2f} بفوليوم {vol_ratio:.1f}x"
            })

        # ② PULLBACK to EMA20 — ارتداد على المتوسط
        pb_ema = (prev_close <= ema_m * 1.005 and price > ema_m
                  and regime in ("TRENDING_UP",) and rsi < 65)
        if pb_ema:
            score  = 0
            score += 25 if vol_ratio > 1.3 else (15 if vol_ratio > 1.0 else 5)
            score += 25 if 38 < rsi < 60 else 0
            score += 20 if macd_hist > 0 else 0
            score += 15 if price > support else 0
            candidates.append({
                "direction": "BUY", "score": score,
                "pattern": "PULLBACK_EMA20",
                "reason": f"ارتداد على EMA{Config.EMA_MED} مع زخم صاعد RSI={rsi:.0f}"
            })

        # ③ SUPPORT BOUNCE — ارتداد من الدعم
        bounce = (prev_close <= support * 1.005 and price > prev_close
                  and vol_ratio > 1.2 and rsi < 55)
        if bounce:
            score  = 0
            score += 30 if vol_ratio > 1.5 else 20
            score += 25 if rsi < 40 else (15 if rsi < 50 else 5)
            score += 15 if price > ema_m else 0
            score += 10 if macd_hist > 0 else 0
            candidates.append({
                "direction": "BUY", "score": score,
                "pattern": "SUPPORT_BOUNCE",
                "reason": f"ارتداد قوي من دعم ${support:.2f}"
            })

        # ④ BREAKDOWN — كسر الدعم للأسفل
        breakdown = (price < support and prev_close >= support * 0.998
                     and vol_ratio > 1.3)
        if breakdown:
            score  = 0
            score += 35 if vol_ratio > 1.6 else 20
            score += 25 if regime in ("TRENDING_DOWN",) else 0
            score += 20 if macd_hist < 0 else 0
            score += 15 if rsi < 50 else 0
            candidates.append({
                "direction": "SELL", "score": score,
                "pattern": "BREAKDOWN",
                "reason": f"كسر دعم ${support:.2f} هبوطي بفوليوم {vol_ratio:.1f}x"
            })

        # ⑤ OVERBOUGHT — تشبع شراء
        overbought = (rsi > 74 and price > bb_upper and vol_ratio > 1.3)
        if overbought:
            score  = 40 + (rsi - 70) * 2
            score += 15 if macd_hist < 0 else 0
            candidates.append({
                "direction": "SELL", "score": min(score, 80),
                "pattern": "OVERBOUGHT",
                "reason": f"تشبع شراء RSI={rsi:.0f} + فوق Bollinger العلوي"
            })

        # ⑥ OVERSOLD — تشبع بيع
        oversold = (rsi < 26 and price < bb_lower and vol_ratio > 1.2)
        if oversold:
            score  = 40 + (30 - rsi) * 2
            score += 15 if macd_hist > 0 else 0
            candidates.append({
                "direction": "BUY", "score": min(score, 80),
                "pattern": "OVERSOLD",
                "reason": f"تشبع بيع RSI={rsi:.0f} + تحت Bollinger السفلي"
            })

        # ── اختيار أفضل إشارة ──
        if not candidates or vol_ratio < Config.MIN_VOLUME_RATIO:
            return SignalEngine._no_trade(symbol, ind, change_pct)

        best = max(candidates, key=lambda x: x["score"])

        if best["score"] < Config.MIN_CONFIDENCE:
            return SignalEngine._no_trade(symbol, ind, change_pct)

        # ── حساب Entry / SL / TP ──
        atr_sl = atr * Config.ATR_SL_MULT
        direction = best["direction"]
        entry = price

        if direction == "BUY":
            stop_loss   = round(entry - atr_sl, 2)
            take_profit = round(entry + atr_sl * Config.RR_RATIO, 2)
        else:
            stop_loss   = round(entry + atr_sl, 2)
            take_profit = round(entry - atr_sl * Config.RR_RATIO, 2)

        rr = round(abs(take_profit - entry) / max(abs(entry - stop_loss), 0.001), 2)
        conf = float(min(best["score"], 95))
        strength = "HIGH" if conf >= 70 else ("MEDIUM" if conf >= 50 else "WEAK")

        return TradeSignal(
            symbol=symbol,
            signal=direction,
            confidence=conf,
            strength=strength,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            rr_ratio=rr,
            reason=best["reason"],
            pattern=best["pattern"],
            regime=regime,
            price=price,
            change_pct=change_pct,
            rsi=rsi,
            volume_ratio=vol_ratio,
            ema_fast=ind["ema_fast"],
            ema_med=ind["ema_med"],
            ema_slow=ind["ema_slow"],
            support=support,
            resistance=resistance,
            atr=round(atr, 2),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    @staticmethod
    def _no_trade(symbol, ind, change_pct) -> TradeSignal:
        return TradeSignal(
            symbol=symbol, signal="NO TRADE", confidence=0.0, strength="WEAK",
            entry=ind["price"], stop_loss=0.0, take_profit=0.0, rr_ratio=0.0,
            reason="لا توجد إشارة بتلاقي كافٍ للشروط — انتظر تأكيداً أقوى",
            pattern="NONE", regime=ind["regime"],
            price=ind["price"], change_pct=change_pct,
            rsi=ind["rsi"], volume_ratio=ind["vol_ratio"],
            ema_fast=ind["ema_fast"], ema_med=ind["ema_med"], ema_slow=ind["ema_slow"],
            support=ind["support"], resistance=ind["resistance"], atr=round(ind["atr"], 2),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )


# ──────────────────────────────────────────────────────────────
# 7. ORDER EXECUTION — تنفيذ الأوامر عبر Alpaca
# ──────────────────────────────────────────────────────────────

class OrderExecutor:
    """
    تنفيذ الأوامر عبر Alpaca Paper Trading
    ⚠ اضبط BASE_URL على live-api.alpaca.markets للتداول الحقيقي
    """

    def __init__(self):
        self.client = None
        if ALPACA_AVAILABLE and Config.API_KEY != "DEMO_KEY":
            try:
                self.client = TradingClient(
                    Config.API_KEY, Config.SECRET_KEY, paper=True
                )
                log.info("✓ Alpaca Trading Client متصل")
            except Exception as e:
                log.warning(f"Trading client error: {e}")

    def get_account(self) -> dict:
        """جلب معلومات الحساب"""
        if not self.client:
            return {"equity": 100000, "buying_power": 50000, "status": "DEMO"}
        try:
            acc = self.client.get_account()
            return {
                "equity":       float(acc.equity),
                "buying_power": float(acc.buying_power),
                "status":       acc.status
            }
        except Exception as e:
            log.error(f"Account error: {e}")
            return {}

    def place_order(self, signal: TradeSignal, account_equity: float) -> dict:
        """
        تنفيذ صفقة بناءً على الإشارة وإدارة المخاطر
        """
        if signal.signal == "NO TRADE":
            return {"status": "skipped", "reason": "NO TRADE signal"}

        if not self.client:
            risk_amt = account_equity * Config.RISK_PER_TRADE
            risk_per_share = abs(signal.entry - signal.stop_loss)
            qty = int(risk_amt / risk_per_share) if risk_per_share > 0 else 1
            log.info(f"[DEMO] {signal.signal} {qty} سهم {signal.symbol} "
                     f"@ ${signal.entry:.2f} | SL ${signal.stop_loss:.2f} | TP ${signal.take_profit:.2f}")
            return {
                "status": "demo",
                "symbol": signal.symbol,
                "side":   signal.signal,
                "qty":    qty,
                "entry":  signal.entry,
                "sl":     signal.stop_loss,
                "tp":     signal.take_profit,
            }

        # حساب الحجم
        risk_amt = account_equity * Config.RISK_PER_TRADE
        risk_per = abs(signal.entry - signal.stop_loss)
        qty = max(1, int(risk_amt / risk_per)) if risk_per > 0 else 1

        side = OrderSide.BUY if signal.signal == "BUY" else OrderSide.SELL

        try:
            order_data = MarketOrderRequest(
                symbol=signal.symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY
            )
            order = self.client.submit_order(order_data)
            log.info(f"✓ تم إرسال الأمر: {order.id}")
            return {
                "status": "submitted",
                "order_id": str(order.id),
                "symbol": signal.symbol,
                "qty": qty,
                "side": signal.signal
            }
        except Exception as e:
            log.error(f"Order error: {e}")
            return {"status": "error", "message": str(e)}


# ──────────────────────────────────────────────────────────────
# 8. MAIN TRADING SYSTEM — النظام الرئيسي
# ──────────────────────────────────────────────────────────────

class TradingSystem:
    """
    النظام الرئيسي — يجمع كل المكونات
    """

    def __init__(self):
        self.data     = MarketDataProvider()
        self.executor = OrderExecutor()
        log.info("✓ نظام التداول جاهز")

    def analyze(self, symbol: str, execute: bool = False) -> Optional[TradeSignal]:
        """
        تحليل سهم وإعطاء إشارة
        Args:
            symbol:  رمز السهم (مثل AAPL)
            execute: True لتنفيذ الصفقة تلقائياً
        Returns:
            TradeSignal object
        """
        log.info(f"⟳ تحليل {symbol}...")

        # 1. جلب البيانات
        df = self.data.fetch(symbol)
        if df is None or len(df) < 30:
            log.error(f"✗ فشل في جلب بيانات {symbol}")
            return None

        # 2. حساب المؤشرات
        indicators = TechnicalAnalysis.compute_all(df)

        # 3. توليد الإشارة
        signal = SignalEngine.generate(symbol, indicators)

        # 4. عرض التقرير
        signal.print_report()

        # 5. تنفيذ اختياري
        if execute and signal.signal != "NO TRADE" and signal.confidence >= Config.MIN_CONFIDENCE:
            account = self.executor.get_account()
            equity  = account.get("equity", 10000)
            result  = self.executor.place_order(signal, equity)
            log.info(f"نتيجة الأمر: {result}")

        return signal

    def scan_watchlist(self, symbols: list, execute: bool = False) -> list:
        """
        مسح قائمة أسهم واختيار أفضل الفرص
        """
        results = []
        for sym in symbols:
            sig = self.analyze(sym, execute=execute)
            if sig:
                results.append(sig)
            time.sleep(0.5)  # تجنب Rate Limiting

        # ترتيب حسب الثقة
        results.sort(key=lambda x: x.confidence, reverse=True)
        trades = [r for r in results if r.signal != "NO TRADE"]

        print(f"\n{'═'*56}")
        print(f"  ملخص المسح: {len(results)} سهم | {len(trades)} إشارة")
        print(f"{'═'*56}")
        for t in trades[:5]:
            icon = "🟢" if t.signal == "BUY" else "🔴"
            print(f"  {icon} {t.symbol:<6}  {t.signal:<5}  {t.confidence:.0f}%  |  {t.pattern}")
        print(f"{'═'*56}\n")

        return results

    def run_loop(self, symbols: list, interval: int = 300):
        """
        تشغيل مستمر — يحلل كل interval ثانية
        Args:
            symbols:  قائمة الأسهم
            interval: الفترة بالثواني (300 = 5 دقائق)
        """
        log.info(f"▶ بدء المسح المستمر لـ {len(symbols)} سهم كل {interval}s")
        while True:
            try:
                self.scan_watchlist(symbols, execute=False)
                log.info(f"✓ انتظار {interval}s للدورة القادمة...")
                time.sleep(interval)
            except KeyboardInterrupt:
                log.info("⛔ إيقاف النظام")
                break
            except Exception as e:
                log.error(f"Loop error: {e}")
                time.sleep(30)


# ──────────────────────────────────────────────────────────────
# 9. CLI — واجهة سطر الأوامر
# ──────────────────────────────────────────────────────────────

def interactive_mode():
    """وضع التفاعل المباشر مع المستخدم"""
    system = TradingSystem()
    print("\n" + "╔" + "═"*52 + "╗")
    print("║        QUANT TRADING SYSTEM — نظام التداول       ║")
    print("║        اكتب رمز السهم للتحليل الفوري             ║")
    print("╚" + "═"*52 + "╝")
    print("  أمثلة: AAPL | TSLA | NVDA | MSFT | AMZN")
    print("  scan  → مسح قائمة افتراضية")
    print("  loop  → مسح مستمر كل 5 دقائق")
    print("  quit  → خروج\n")

    DEFAULT_WATCHLIST = ["AAPL","NVDA","TSLA","MSFT","AMZN","META","GOOGL","AMD"]

    while True:
        try:
            user_input = input("  ← أدخل رمز السهم: ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            print("\n⛔ خروج.")
            break

        if not user_input:
            continue
        if user_input in ("QUIT", "EXIT", "Q"):
            print("⛔ وداعاً.")
            break
        elif user_input == "SCAN":
            system.scan_watchlist(DEFAULT_WATCHLIST)
        elif user_input == "LOOP":
            system.run_loop(DEFAULT_WATCHLIST, interval=300)
        else:
            system.analyze(user_input)


# ──────────────────────────────────────────────────────────────
# 10. ENTRY POINT
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    ticker = sys.argv[1]
    import sys
    print("تشغيل التحليل...")  
    if len(sys.argv) > 1:
        # استخدام من سطر الأوامر: python trading_system.py AAPL
        ts = TradingSystem()
        for sym in sys.argv[1:]:
            ts.analyze(sym.upper())
    else:
        # الوضع التفاعلي
        interactive_mode()
