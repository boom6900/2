import React, { useState } from "react";

function App() {
  const [ticker, setTicker] = useState("");
  const [result, setResult] = useState("");

  const analyze = async () => {
    if (!ticker) return;

    setResult("⏳ جاري التحليل...");

    try {
      const res = await fetch("http://127.0.0.1:5000/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ticker }),
      });

      const data = await res.json();
      setResult(data.result);
    } catch (err) {
      setResult("❌ فشل الاتصال بالسيرفر");
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      <h1>📊 Trading Analyzer</h1>

      <input
        type="text"
        placeholder="AAPL, TSLA..."
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
      />

      <button onClick={analyze}>Analyze</button>

      <pre style={{ marginTop: "20px", whiteSpace: "pre-wrap" }}>
        {result}
      </pre>
    </div>
  );
}

export default App;