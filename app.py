"""
app.py — Servidor web para Railway
Sirve el dashboard ML 360° como página web pública.
"""
from flask import Flask, send_file, jsonify
import os

app = Flask(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DASHBOARD  = os.path.join(BASE_DIR, 'ml_agent', 'dashboards', 'ml_dashboard_360.html')

@app.route('/')
def index():
    if os.path.exists(DASHBOARD):
        return send_file(DASHBOARD)
    return "<h2 style='font-family:sans-serif;padding:40px'>Dashboard aún no generado. Corré ml_main.py para crearlo.</h2>", 404

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'dashboard': os.path.exists(DASHBOARD)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
