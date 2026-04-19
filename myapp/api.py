from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess

app = Flask(__name__)
CORS(app)

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    ticker = data.get("ticker").strip()

    try:
        process = subprocess.Popen(
            ["python", "trading_system.py", ticker],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            result = f"❌ خطأ:\n{stderr}"
        else:
            result = stdout

    except Exception as e:
        result = f"❌ خطأ عام: {str(e)}"

    return jsonify({"result": result})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)