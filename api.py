from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    ticker = data.get("ticker", "").strip()

    try:
        result = subprocess.run(
            ["python", "trading_system.py", ticker],
            capture_output=True,
            text=True
        )

        output = result.stdout + "\n" + result.stderr

    except Exception as e:
        output = f"❌ خطأ: {str(e)}"

    return jsonify({"result": output})


import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)