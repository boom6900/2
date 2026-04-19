import { useState, useRef, useCallback } from "react";

// ─── Simulated market data engine (mirrors Python logic exactly) ───────────

function generateRealisticData(symbol, bars = 120) {
  // Deterministic seed based on symbol
  const seed = symbol.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const rng = (n) => {
    const x = Math.sin(n * seed * 9301 + 49297) * 233280;
    return x - Math.floor(x);
  };

  const basePrice = 50 + (seed % 450);
  const candles = [];
  let price = basePrice;
  let regime = rng(0) > 0.5 ? 1 : -1;
  let vol = 0.008 + rng(1) * 0.012;

  for (let i = 0; i < bars; i++) {
    if (rng(i * 7) < 0.06) regime = -regime;
    const drift = regime * 0.0007;
    const noise = (rng(i * 3) - 0.5) * vol;
    const chg   = drift + noise;
    const open  = price;
    const close = +(open * (1 + chg)).toFixed(2);
    const wick  = vol * (0.4 + rng(i * 5));
    const high  = +(Math.max(open, close) * (1 + rng(i * 2) * wick)).toFixed(2);
    const low   = +(Math.min(open, close) * (1 - rng(i * 4) * wick)).toFixed(2);
    const bv    = 500000 + rng(i * 6) * 5000000;
    const volume = Math.floor(bv * (1 + Math.abs(chg) * 40));
    candles.push({ open, close, high, low, volume, i });
    price = close;
  }
  return candles;
}

// ─── Technical indicators (mirrors Python TA class) ───────────────────────

function ema(arr, period) {
  if (arr.length < period) return arr[arr.length - 1];
  const k = 2 / (period + 1);
  let e = arr.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < arr.length; i++) e = arr[i] * k + e * (1 - k);
  return +e.toFixed(4);
}

function rsi(closes, period = 14) {
  if (closes.length < period + 1) return 50;
  let g = 0, l = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    if (d > 0) g += d; else l += -d;
  }
  if (l === 0) return 100;
  return +(100 - 100 / (1 + (g / period) / (l / period))).toFixed(2);
}

function macdCalc(closes) {
  if (closes.length < 26) return { macd: 0, signal: 0, hist: 0 };
  const e12 = ema(closes, 12), e26 = ema(closes, 26);
  const line = e12 - e26;
  const macdArr = [];
  for (let i = 26; i <= closes.length; i++) {
    const a = ema(closes.slice(0, i), 12);
    const b = ema(closes.slice(0, i), 26);
    macdArr.push(a - b);
  }
  const sig = ema(macdArr, 9);
  return { macd: +line.toFixed(4), signal: +sig.toFixed(4), hist: +(line - sig).toFixed(4) };
}

function bollinger(closes, n = 20) {
  if (closes.length < n) return null;
  const sl = closes.slice(-n);
  const mean = sl.reduce((s, v) => s + v, 0) / n;
  const std = Math.sqrt(sl.reduce((s, v) => s + (v - mean) ** 2, 0) / n);
  return { upper: +(mean + 2 * std).toFixed(2), lower: +(mean - 2 * std).toFixed(2), middle: +mean.toFixed(2) };
}

function atr(candles, period = 14) {
  const trs = [];
  for (let i = 1; i < candles.length; i++) {
    const { high, low } = candles[i];
    const pc = candles[i - 1].close;
    trs.push(Math.max(high - low, Math.abs(high - pc), Math.abs(low - pc)));
  }
  return trs.slice(-period).reduce((s, v) => s + v, 0) / period;
}

function pivots(candles, lb = 30) {
  const sl = candles.slice(-lb);
  const sh = [], sv = [];
  for (let i = 2; i < sl.length - 2; i++) {
    if (sl[i].high > sl[i-1].high && sl[i].high > sl[i-2].high &&
        sl[i].high > sl[i+1].high && sl[i].high > sl[i+2].high)
      sh.push(sl[i].high);
    if (sl[i].low < sl[i-1].low && sl[i].low < sl[i-2].low &&
        sl[i].low < sl[i+1].low && sl[i].low < sl[i+2].low)
      sv.push(sl[i].low);
  }
  const resistance = sh.length ? Math.max(...sh) : Math.max(...sl.map(c => c.high));
  const support    = sv.length ? Math.min(...sv) : Math.min(...sl.map(c => c.low));
  return { resistance: +resistance.toFixed(2), support: +support.toFixed(2) };
}

function detectRegime(candles) {
  if (candles.length < 50) return "UNKNOWN";
  const cl = candles.slice(-50).map(c => c.close);
  const e20 = ema(cl, 20), e50 = ema(cl, 50);
  const b   = bollinger(cl);
  const bw  = b ? (b.upper - b.lower) / b.middle : 0.05;
  const rng = (Math.max(...cl) - Math.min(...cl)) / cl[0];
  if (bw < 0.03) return "SIDEWAYS";
  if (rng > 0.2)  return "HIGH_VOLATILITY";
  if (e20 > e50 * 1.005) return "TRENDING_UP";
  if (e20 < e50 * 0.995) return "TRENDING_DOWN";
  return "SIDEWAYS";
}

function computeIndicators(candles) {
  const closes = candles.map(c => c.close);
  const last   = candles.at(-1), prev = candles.at(-2);
  const vols   = candles.map(c => c.volume);
  const avgVol = vols.slice(-20).reduce((s, v) => s + v, 0) / 20;
  const { resistance, support } = pivots(candles);
  const bb = bollinger(closes);
  const m  = macdCalc(closes);
  return {
    price:      +last.close.toFixed(2),
    prev_close: +prev.close.toFixed(2),
    high:       last.high, low: last.low,
    ema_fast:   +ema(closes, 9).toFixed(2),
    ema_med:    +ema(closes, 20).toFixed(2),
    ema_slow:   +ema(closes, 50).toFixed(2),
    rsi:        rsi(closes),
    macd_hist:  m.hist, macd_line: m.macd, macd_signal: m.signal,
    bb_upper:   bb?.upper || 0, bb_lower: bb?.lower || 0,
    atr:        +atr(candles).toFixed(4),
    support, resistance,
    vol_ratio:  +(last.volume / avgVol).toFixed(2),
    regime:     detectRegime(candles)
  };
}

function generateSignal(symbol, ind) {
  const { price, prev_close, support, resistance, rsi: r, vol_ratio,
          macd_hist, atr: atrVal, regime, ema_med, bb_upper, bb_lower } = ind;
  const change_pct = +((price - prev_close) / prev_close * 100).toFixed(2);
  const candidates = [];

  if (price > resistance && prev_close <= resistance * 1.002) {
    let s = (vol_ratio>1.5?30:vol_ratio>1.2?20:5)+(regime==="TRENDING_UP"?20:0)
            +(macd_hist>0?15:0)+(r>50&&r<72?15:0)+(price>ind.ema_med?10:0);
    candidates.push({ dir:"BUY", score:s, pattern:"BREAKOUT",
      reason:`كسر مقاومة $${resistance} بفوليوم ${vol_ratio}x` });
  }
  if (prev_close<=ema_med*1.005 && price>ema_med && regime==="TRENDING_UP" && r<65) {
    let s = (vol_ratio>1.3?25:vol_ratio>1.0?15:5)+(r>38&&r<60?25:0)
            +(macd_hist>0?20:0)+(price>support?15:0);
    candidates.push({ dir:"BUY", score:s, pattern:"PULLBACK_EMA20",
      reason:`ارتداد على EMA20 مع زخم صاعد RSI=${r}` });
  }
  if (prev_close<=support*1.005 && price>prev_close && vol_ratio>1.2 && r<55) {
    let s = (vol_ratio>1.5?30:20)+(r<40?25:r<50?15:5)+(price>ema_med?15:0)+(macd_hist>0?10:0);
    candidates.push({ dir:"BUY", score:s, pattern:"SUPPORT_BOUNCE",
      reason:`ارتداد قوي من دعم $${support}` });
  }
  if (price<support && prev_close>=support*0.998 && vol_ratio>1.3) {
    let s = (vol_ratio>1.6?35:20)+(regime==="TRENDING_DOWN"?25:0)
            +(macd_hist<0?20:0)+(r<50?15:0);
    candidates.push({ dir:"SELL", score:s, pattern:"BREAKDOWN",
      reason:`كسر دعم $${support} هبوطي` });
  }
  if (r>74 && price>bb_upper && vol_ratio>1.3) {
    let s = Math.min(40+(r-70)*2+(macd_hist<0?15:0), 80);
    candidates.push({ dir:"SELL", score:s, pattern:"OVERBOUGHT",
      reason:`تشبع شراء RSI=${r} + فوق Bollinger` });
  }
  if (r<26 && price<bb_lower && vol_ratio>1.2) {
    let s = Math.min(40+(30-r)*2+(macd_hist>0?15:0), 80);
    candidates.push({ dir:"BUY", score:s, pattern:"OVERSOLD",
      reason:`تشبع بيع RSI=${r} + تحت Bollinger` });
  }

  if (!candidates.length || vol_ratio < 1.2) {
    return { symbol, signal:"NO TRADE", confidence:0, strength:"WEAK",
      entry:price, stop_loss:0, take_profit:0, rr_ratio:0,
      reason:"لا توجد إشارة بتلاقي كافٍ للشروط — انتظر تأكيداً أقوى",
      pattern:"NONE", ...ind, change_pct };
  }

  const best = candidates.sort((a,b) => b.score-a.score)[0];
  if (best.score < 55) return { symbol, signal:"NO TRADE", confidence:0, strength:"WEAK",
    entry:price, stop_loss:0, take_profit:0, rr_ratio:0,
    reason:"الإشارة ضعيفة — انتظر تأكيداً", pattern:"NONE", ...ind, change_pct };

  const atr_sl = atrVal * 1.5;
  const sl = best.dir==="BUY" ? +(price-atr_sl).toFixed(2) : +(price+atr_sl).toFixed(2);
  const tp = best.dir==="BUY" ? +(price+atr_sl*2.5).toFixed(2) : +(price-atr_sl*2.5).toFixed(2);
  const rr = +((Math.abs(tp-price)/Math.abs(price-sl))).toFixed(2);
  const conf = Math.min(best.score, 95);
  return {
    symbol, signal: best.dir, confidence: conf,
    strength: conf>=70?"HIGH":conf>=50?"MEDIUM":"WEAK",
    entry: price, stop_loss: sl, take_profit: tp, rr_ratio: rr,
    reason: best.reason, pattern: best.pattern, ...ind, change_pct
  };
}

// ─── Claude AI analysis via Anthropic API ─────────────────────────────────

async function getClaudeAnalysis(signal) {
  const prompt = `أنت محلل تداول خبير. بناءً على البيانات التالية لسهم ${signal.symbol}، قدّم تحليلاً موجزاً واحترافياً باللغة العربية:

السعر: $${signal.price} (${signal.change_pct > 0 ? "+" : ""}${signal.change_pct}%)
الإشارة: ${signal.signal} | الثقة: ${signal.confidence}% | القوة: ${signal.strength}
النمط: ${signal.pattern}
السبب: ${signal.reason}
حالة السوق: ${signal.regime}
RSI: ${signal.rsi} | فوليوم: ${signal.vol_ratio}x
EMA 9/20/50: ${signal.ema_fast}/${signal.ema_med}/${signal.ema_slow}
دعم: $${signal.support} | مقاومة: $${signal.resistance}
${signal.signal !== "NO TRADE" ? `دخول: $${signal.entry} | SL: $${signal.stop_loss} | TP: $${signal.take_profit} | R:R 1:${signal.rr_ratio}` : ""}

قدّم تحليلاً في 3 نقاط فقط:
1. تقييم الإشارة وقوتها
2. أهم عوامل الخطر
3. توصية نهائية واضحة

كن مختصراً وعملياً. لا تكرر الأرقام. أجب في 4-5 جمل فقط.`;

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1000,
      messages: [{ role: "user", content: prompt }]
    })
  });
  const data = await response.json();
  return data.content?.[0]?.text || "لم يتمكن النظام من توليد التحليل.";
}

// ─── Candle Chart SVG ─────────────────────────────────────────────────────

function CandleChart({ candles, support, resistance }) {
  if (!candles || candles.length < 5) return null;
  const sl = candles.slice(-50);
  const W = 560, H = 130;
  const prices = sl.flatMap(c => [c.high, c.low]);
  const mn = Math.min(...prices) * 0.998;
  const mx = Math.max(...prices) * 1.002;
  const sy = v => H - 6 - ((v - mn) / (mx - mn || 1)) * (H - 12);
  const sx = i => 6 + (i / (sl.length - 1)) * (W - 12);
  const bw = Math.max((W - 12) / sl.length * 0.5, 1.5);

  // EMA lines
  const closes = sl.map(c => c.close);
  const e20pts = [], e50pts = [];
  for (let i = 20; i <= sl.length; i++) {
    const v = ema(closes.slice(0, i), 20);
    e20pts.push(`${sx(i-1)},${sy(v)}`);
  }
  for (let i = Math.min(50, sl.length); i <= sl.length; i++) {
    const v = ema(closes.slice(0, i), Math.min(50, i));
    e50pts.push(`${sx(i-1)},${sy(v)}`);
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      <line x1={6} y1={sy(support)} x2={W-6} y2={sy(support)} stroke="#3af" strokeWidth="1" strokeDasharray="4,3" opacity=".5"/>
      <line x1={6} y1={sy(resistance)} x2={W-6} y2={sy(resistance)} stroke="#f44" strokeWidth="1" strokeDasharray="4,3" opacity=".5"/>
      {e20pts.length>1 && <polyline points={e20pts.join(" ")} fill="none" stroke="#ffd54f" strokeWidth="1.2" opacity=".7"/>}
      {e50pts.length>1 && <polyline points={e50pts.join(" ")} fill="none" stroke="#ff9800" strokeWidth="1.2" opacity=".7"/>}
      {sl.map((c, i) => {
        const bull = c.close >= c.open;
        const col  = bull ? "#00e676" : "#ff1744";
        const oy = sy(c.open), cy = sy(c.close);
        return (
          <g key={i}>
            <line x1={sx(i)} y1={sy(c.high)} x2={sx(i)} y2={sy(c.low)} stroke={col} strokeWidth=".8" opacity=".6"/>
            <rect x={sx(i)-bw/2} y={Math.min(oy,cy)} width={bw} height={Math.max(Math.abs(cy-oy),1)} fill={col} opacity=".9"/>
          </g>
        );
      })}
      <text x={W-4} y={sy(support)-2} textAnchor="end" fill="#3af" fontSize="7" opacity=".8">S {support}</text>
      <text x={W-4} y={sy(resistance)-2} textAnchor="end" fill="#f44" fontSize="7" opacity=".8">R {resistance}</text>
    </svg>
  );
}

function VolChart({ candles }) {
  if (!candles) return null;
  const sl = candles.slice(-50);
  const W = 560, H = 32;
  const maxV = Math.max(...sl.map(c => c.volume));
  const sx = i => 6 + (i / (sl.length - 1)) * (W - 12);
  const bw = Math.max((W-12)/sl.length*0.5, 1.5);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {sl.map((c, i) => (
        <rect key={i} x={sx(i)-bw/2} y={H - (c.volume/maxV)*(H-2) - 1}
          width={bw} height={(c.volume/maxV)*(H-2)}
          fill={c.close>=c.open?"#00e676":"#ff1744"} opacity=".45"/>
      ))}
    </svg>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────

const C = {
  bg: "#04080f", panel: "#070d18", border: "#0d1e30", borderL: "#132540",
  buy: "#00e676", sell: "#ff1744", gold: "#ffd54f", blue: "#40c4ff",
  text: "#90a4ae", bright: "#eceff1", dim: "#263238", muted: "#37474f"
};

export default function TradingApp() {
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [aiLoading, setAiLoad]  = useState(false);
  const [signal, setSignal]     = useState(null);
  const [candles, setCandles]   = useState(null);
  const [aiText, setAiText]     = useState("");
  const [error, setError]       = useState("");
  const [history, setHistory]   = useState([]);
  const inputRef = useRef(null);

  const analyze = useCallback(async (sym) => {
    const symbol = (sym || input).trim().toUpperCase();
    if (!symbol) return;
    setLoading(true); setError(""); setAiText(""); setSignal(null); setCandles(null);

    try {
      await new Promise(r => setTimeout(r, 600));
      const cdls = generateRealisticData(symbol, 120);
      const ind  = computeIndicators(cdls);
      const sig  = generateSignal(symbol, ind);
      setCandles(cdls);
      setSignal(sig);
      setHistory(h => [{ symbol, signal: sig.signal, conf: sig.confidence, time: new Date().toLocaleTimeString("ar") }, ...h].slice(0, 8));

      // Get Claude AI analysis
      setAiLoad(true);
      try {
        const txt = await getClaudeAnalysis(sig);
        setAiText(txt);
      } catch {
        setAiText("⚠ لا يمكن الوصول لتحليل الذكاء الاصطناعي حالياً.");
      } finally {
        setAiLoad(false);
      }
    } catch (e) {
      setError("فشل في تحليل " + symbol + ". تأكد من صحة الرمز.");
    } finally {
      setLoading(false);
    }
  }, [input]);

  const sc  = s => s==="BUY"?C.buy:s==="SELL"?C.sell:C.muted;
  const ricon = r => ({ TRENDING_UP:"↗", TRENDING_DOWN:"↘", SIDEWAYS:"→", HIGH_VOLATILITY:"⚡" })[r] || "?";
  const rlabel = r => ({ TRENDING_UP:"صاعد", TRENDING_DOWN:"هابط", SIDEWAYS:"عرضي", HIGH_VOLATILITY:"متذبذب" })[r] || r;

  const QUICK = ["AAPL","NVDA","TSLA","MSFT","AMZN","META","GOOGL","AMD"];

  return (
    <div style={{
      fontFamily: "'JetBrains Mono','Fira Code',monospace",
      background: C.bg, color: C.text, minHeight: "100vh",
      display: "flex", flexDirection: "column"
    }}>
      <style>{`
        @keyframes spin { to{transform:rotate(360deg)} }
        @keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
        ::-webkit-scrollbar{width:3px} ::-webkit-scrollbar-track{background:#070d18}
        ::-webkit-scrollbar-thumb{background:#132540;border-radius:2px}
        .quick-btn:hover{background:#0d1e30!important;border-color:#40c4ff44!important}
        .hist-row:hover{background:#0a1520!important}
        input:focus{outline:none!important}
      `}</style>

      {/* ── HEADER ── */}
      <div style={{
        background:"linear-gradient(90deg,#060d1a,#0a1628)",
        borderBottom:`1px solid ${C.border}`,
        padding:"12px 20px",
        display:"flex", alignItems:"center", justifyContent:"space-between"
      }}>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <div style={{width:8,height:8,borderRadius:"50%",background:C.buy,animation:"pulse 2s infinite"}}/>
          <span style={{fontSize:15,fontWeight:800,color:C.bright,letterSpacing:".08em"}}>QUANT AI TRADER</span>
          <span style={{fontSize:9,color:"#3a6",border:"1px solid #3a644",padding:"1px 6px",borderRadius:2}}>
            AI-POWERED
          </span>
        </div>
        <span style={{fontSize:10,color:C.muted}}>تحليل فني + ذكاء اصطناعي • بيانات شبه-حقيقية</span>
      </div>

      <div style={{flex:1,display:"flex",overflow:"hidden"}}>

        {/* ── LEFT SIDEBAR ── */}
        <div style={{
          width:200, background:C.panel,
          borderRight:`1px solid ${C.border}`,
          display:"flex", flexDirection:"column",
          flexShrink:0
        }}>
          {/* Quick symbols */}
          <div style={{padding:"12px 10px",borderBottom:`1px solid ${C.border}`}}>
            <div style={{fontSize:9,color:C.muted,marginBottom:8,letterSpacing:".05em"}}>أسهم سريعة</div>
            {QUICK.map(s => (
              <button key={s} className="quick-btn" onClick={() => { setInput(s); analyze(s); }}
                style={{
                  display:"block",width:"100%",background:"transparent",
                  border:`1px solid ${signal?.symbol===s?C.blue+"44":C.border}`,
                  color: signal?.symbol===s ? C.blue : C.text,
                  padding:"5px 10px",borderRadius:4,marginBottom:4,
                  cursor:"pointer",fontFamily:"inherit",fontSize:11,
                  textAlign:"right",transition:"all .15s"
                }}>{s}</button>
            ))}
          </div>

          {/* History */}
          {history.length > 0 && (
            <div style={{padding:"12px 10px",flex:1,overflowY:"auto"}}>
              <div style={{fontSize:9,color:C.muted,marginBottom:8}}>آخر التحليلات</div>
              {history.map((h,i) => (
                <div key={i} className="hist-row" onClick={() => { setInput(h.symbol); analyze(h.symbol); }}
                  style={{
                    padding:"5px 8px",borderRadius:4,marginBottom:3,cursor:"pointer",
                    transition:"all .15s",
                    display:"flex",justifyContent:"space-between",alignItems:"center"
                  }}>
                  <span style={{fontSize:11,color:C.bright,fontWeight:700}}>{h.symbol}</span>
                  <span style={{fontSize:9,color:sc(h.signal),fontWeight:700}}>{h.signal.replace("NO TRADE","—")}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ── MAIN AREA ── */}
        <div style={{flex:1,display:"flex",flexDirection:"column",overflow:"hidden"}}>

          {/* Search bar */}
          <div style={{
            padding:"14px 20px",
            background:"#060c16",
            borderBottom:`1px solid ${C.border}`,
            display:"flex", gap:10, alignItems:"center"
          }}>
            <div style={{
              flex:1, display:"flex", alignItems:"center",
              background:C.panel, border:`1px solid ${C.borderL}`,
              borderRadius:6, padding:"0 14px", gap:10
            }}>
              <span style={{color:C.muted,fontSize:14}}>⌕</span>
              <input ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value.toUpperCase())}
                onKeyDown={e => e.key==="Enter" && analyze()}
                placeholder="أدخل رمز السهم — مثال: AAPL"
                style={{
                  flex:1, background:"transparent", border:"none",
                  color:C.bright, fontFamily:"inherit", fontSize:14,
                  padding:"10px 0", direction:"rtl"
                }}
              />
              {input && (
                <span onClick={() => setInput("")}
                  style={{color:C.muted,cursor:"pointer",fontSize:12}}>✕</span>
              )}
            </div>
            <button onClick={() => analyze()} disabled={loading || !input}
              style={{
                background: loading?"#0d1e30":`${C.blue}22`,
                border:`1px solid ${loading?C.border:C.blue+"55"}`,
                color: loading?C.muted:C.blue,
                padding:"10px 22px", borderRadius:6,
                fontFamily:"inherit", fontSize:12, fontWeight:700,
                cursor: loading||!input?"not-allowed":"pointer",
                transition:"all .2s", whiteSpace:"nowrap"
              }}>
              {loading ? (
                <span style={{display:"flex",alignItems:"center",gap:6}}>
                  <span style={{animation:"spin 1s linear infinite",display:"inline-block"}}>⟳</span> تحليل...
                </span>
              ) : "▶ تحليل"}
            </button>
          </div>

          {/* Content */}
          <div style={{flex:1,overflowY:"auto",padding:"16px 20px"}}>

            {/* Empty state */}
            {!signal && !loading && (
              <div style={{
                display:"flex",flexDirection:"column",alignItems:"center",
                justifyContent:"center",height:"60%",gap:16,
                animation:"fadeUp .5s ease"
              }}>
                <div style={{fontSize:40,opacity:.15}}>◈</div>
                <div style={{fontSize:14,color:C.muted,textAlign:"center",lineHeight:2}}>
                  أدخل رمز سهم للحصول على تحليل فوري<br/>
                  <span style={{fontSize:11,color:C.dim}}>
                    يدعم جميع أسهم الأسواق الأمريكية
                  </span>
                </div>
              </div>
            )}

            {/* Loading skeleton */}
            {loading && (
              <div style={{animation:"fadeUp .3s ease"}}>
                {[140,80,60,100].map((h,i) => (
                  <div key={i} style={{
                    background:C.panel,border:`1px solid ${C.border}`,
                    borderRadius:8,height:h,marginBottom:12,
                    animation:"pulse 1.5s infinite",opacity:.5
                  }}/>
                ))}
              </div>
            )}

            {/* Results */}
            {signal && !loading && (
              <div style={{animation:"fadeUp .4s ease",display:"flex",flexDirection:"column",gap:12}}>

                {/* Signal Hero */}
                <div style={{
                  background: signal.signal==="BUY"?"rgba(0,230,118,.05)":
                              signal.signal==="SELL"?"rgba(255,23,68,.05)":"rgba(96,125,139,.04)",
                  border:`1px solid ${sc(signal.signal)}44`,
                  borderRadius:10, padding:"18px 20px"
                }}>
                  <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12}}>
                    <div>
                      <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:8,flexWrap:"wrap"}}>
                        <span style={{fontSize:26,fontWeight:800,color:C.bright}}>{signal.symbol}</span>
                        <span style={{
                          fontSize:16,fontWeight:900,color:sc(signal.signal),
                          border:`2px solid ${sc(signal.signal)}`,padding:"3px 12px",borderRadius:4
                        }}>{signal.signal}</span>
                        <span style={{
                          fontSize:10,fontWeight:700,
                          color: signal.strength==="HIGH"?C.buy:signal.strength==="MEDIUM"?C.gold:C.muted,
                          border:`1px solid currentColor`,padding:"2px 8px",borderRadius:3
                        }}>
                          {signal.strength==="HIGH"?"◈":signal.strength==="MEDIUM"?"◇":"○"} {signal.strength}
                        </span>
                        <span style={{fontSize:12,color:sc(signal.signal),fontWeight:700}}>{signal.confidence}% ثقة</span>
                      </div>
                      <div style={{display:"flex",gap:14,fontSize:12,flexWrap:"wrap",marginBottom:8}}>
                        <span style={{color:C.bright,fontWeight:700,fontSize:18}}>${signal.price}</span>
                        <span style={{color:signal.change_pct>=0?C.buy:C.sell}}>
                          {signal.change_pct>=0?"+":""}{signal.change_pct}%
                        </span>
                        <span style={{color:C.text}}>
                          {ricon(signal.regime)} {rlabel(signal.regime)}
                        </span>
                        <span style={{color:C.muted,fontSize:11}}>نمط: {signal.pattern}</span>
                      </div>
                      <div style={{fontSize:11,color:"#4a7a9a"}}>{signal.reason}</div>
                    </div>

                    {/* Confidence ring */}
                    <svg width={64} height={64} viewBox="0 0 64 64" style={{flexShrink:0}}>
                      <circle cx={32} cy={32} r={26} fill="none" stroke={C.border} strokeWidth={5}/>
                      <circle cx={32} cy={32} r={26} fill="none"
                        stroke={sc(signal.signal)} strokeWidth={5}
                        strokeDasharray={`${signal.confidence*1.634} 163.4`}
                        strokeDashoffset={40.8} strokeLinecap="round"
                        transform="rotate(-90 32 32)"/>
                      <text x={32} y={38} textAnchor="middle" fill={sc(signal.signal)}
                        fontSize={14} fontWeight={800}>{signal.confidence}</text>
                    </svg>
                  </div>

                  {/* Trade levels */}
                  {signal.signal !== "NO TRADE" && (
                    <div style={{
                      marginTop:14,
                      display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8
                    }}>
                      {[
                        ["📌 دخول", "$"+signal.entry, C.gold],
                        ["🛑 وقف خسارة", "$"+signal.stop_loss, C.sell],
                        ["🎯 هدف ربح", "$"+signal.take_profit, C.buy],
                        ["📊 R:R", "1:"+signal.rr_ratio, C.blue],
                      ].map(([l,v,c]) => (
                        <div key={l} style={{
                          background:C.panel,borderRadius:6,padding:"10px",textAlign:"center",
                          border:`1px solid ${C.border}`
                        }}>
                          <div style={{fontSize:9,color:C.muted,marginBottom:4}}>{l}</div>
                          <div style={{fontSize:14,fontWeight:800,color:c}}>{v}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Chart */}
                {candles && (
                  <div style={{background:C.panel,border:`1px solid ${C.border}`,borderRadius:8,padding:14}}>
                    <div style={{fontSize:10,color:C.muted,marginBottom:6,display:"flex",gap:14}}>
                      <span>مخطط الشموع (50 شمعة)</span>
                      <span style={{color:"#ffd54f88"}}>── EMA20</span>
                      <span style={{color:"#ff980088"}}>── EMA50</span>
                      <span style={{color:"#3af8"}}>-- دعم</span>
                      <span style={{color:"#f448"}}>-- مقاومة</span>
                    </div>
                    <CandleChart candles={candles} support={signal.support} resistance={signal.resistance}/>
                    <VolChart candles={candles}/>
                  </div>
                )}

                {/* Indicators grid */}
                <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8}}>
                  {[
                    ["RSI", signal.rsi, signal.rsi>70?"#ff9800":signal.rsi<30?C.blue:C.bright],
                    ["فوليوم ×", signal.vol_ratio+"x", signal.vol_ratio>1.5?C.gold:signal.vol_ratio>1.2?C.buy:C.text],
                    ["EMA 9", "$"+signal.ema_fast, signal.price>signal.ema_fast?C.buy:C.sell],
                    ["EMA 20", "$"+signal.ema_med, signal.price>signal.ema_med?C.buy:C.sell],
                    ["EMA 50", "$"+signal.ema_slow, signal.price>signal.ema_slow?C.buy:C.sell],
                    ["MACD H", signal.macd_hist?.toFixed(3), signal.macd_hist>0?C.buy:C.sell],
                    ["دعم", "$"+signal.support, C.blue],
                    ["مقاومة", "$"+signal.resistance, "#ff9800"],
                    ["BB أعلى", "$"+signal.bb_upper, C.muted],
                    ["BB أدنى", "$"+signal.bb_lower, C.muted],
                    ["ATR", "$"+signal.atr, C.text],
                    ["حالة السوق", rlabel(signal.regime),
                      signal.regime==="TRENDING_UP"?C.buy:signal.regime==="TRENDING_DOWN"?C.sell:C.gold],
                  ].map(([l,v,c]) => (
                    <div key={l} style={{
                      background:C.panel,border:`1px solid ${C.border}`,
                      borderRadius:6,padding:"10px",textAlign:"center"
                    }}>
                      <div style={{fontSize:8,color:C.muted,marginBottom:3}}>{l}</div>
                      <div style={{fontSize:12,fontWeight:700,color:c}}>{v||"—"}</div>
                    </div>
                  ))}
                </div>

                {/* AI Analysis */}
                <div style={{
                  background:"rgba(64,196,255,.04)",
                  border:`1px solid #40c4ff22`,
                  borderRadius:8,padding:16
                }}>
                  <div style={{
                    display:"flex",alignItems:"center",gap:8,
                    marginBottom:10,fontSize:12,color:C.blue,fontWeight:700
                  }}>
                    <span>🤖</span>
                    <span>تحليل الذكاء الاصطناعي</span>
                    {aiLoading && (
                      <span style={{fontSize:10,color:C.muted,animation:"pulse 1.5s infinite"}}>
                        ⟳ جاري التحليل...
                      </span>
                    )}
                  </div>
                  <div style={{
                    fontSize:12,color:"#5a8aaa",lineHeight:1.9,
                    minHeight:40,direction:"rtl",textAlign:"right"
                  }}>
                    {aiLoading ? (
                      <span style={{color:C.muted}}>⟳ يحلل الذكاء الاصطناعي الإشارة...</span>
                    ) : (
                      aiText || <span style={{color:C.muted}}>—</span>
                    )}
                  </div>
                </div>

                {/* Python code hint */}
                <div style={{
                  background:"#060f18",border:`1px solid ${C.border}`,
                  borderRadius:8,padding:"12px 16px"
                }}>
                  <div style={{fontSize:10,color:C.muted,marginBottom:8}}>
                    🐍 كود Python المكافئ — تشغيل مباشر على جهازك
                  </div>
                  <code style={{
                    display:"block",fontSize:11,color:"#4ec9b0",
                    lineHeight:1.9,direction:"ltr",textAlign:"left"
                  }}>
                    {`# تثبيت: pip install alpaca-py yfinance pandas numpy
python trading_system.py ${signal.symbol}

# أو الوضع التفاعلي:
python trading_system.py
← أدخل رمز السهم: ${signal.symbol}`}
                  </code>
                </div>

              </div>
            )}

            {error && (
              <div style={{
                background:"rgba(255,23,68,.06)",border:`1px solid ${C.sell}33`,
                borderRadius:8,padding:"14px 16px",color:C.sell,fontSize:12
              }}>
                ⚠ {error}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        borderTop:`1px solid ${C.border}`,padding:"7px 20px",
        display:"flex",justifyContent:"space-between",
        fontSize:9,color:C.dim,background:"#060b14"
      }}>
        <span>QUANT AI TRADER • Python Backend + Claude AI Analysis</span>
        <span>البيانات: yfinance / Alpaca API • التحليل: خوارزميات TA مدمجة</span>
      </div>
    </div>
  );
}
