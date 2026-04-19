from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return "Trading API is running 🚀"

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    ticker = data.get("ticker", "AAPL")

    try:
        result = subprocess.run(
            ["python", "trading_system.py", ticker],
            capture_output=True,
            text=True
        )

        output = result.stdout + result.stderr
        return jsonify({"result": output})

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)