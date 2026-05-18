"""
app.py — Servidor web para Railway
Sirve el dashboard ML 360° como página web pública.
Endpoint /update acepta HTML nuevo vía POST (con API key) para actualización sin git.
"""
from flask import Flask, send_file, jsonify, request, abort
import os, hashlib, hmac

app = Flask(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DASHBOARD  = os.path.join(BASE_DIR, 'ml_agent', 'dashboards', 'ml_dashboard_360.html')

# Clave secreta: se lee de variable de entorno en Railway, o del archivo local
UPDATE_KEY = os.environ.get('DASHBOARD_UPDATE_KEY', 'bfe8b0cb8feddb565e82a0ef1cd677c498d1f17f636d136e6e4036a95430b802')


@app.route('/')
def index():
    if os.path.exists(DASHBOARD):
        return send_file(DASHBOARD)
    return "<h2 style='font-family:sans-serif;padding:40px'>Dashboard aún no generado.</h2>", 404


@app.route('/health')
def health():
    import datetime
    mtime = None
    if os.path.exists(DASHBOARD):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(DASHBOARD)).isoformat()
    return jsonify({'status': 'ok', 'dashboard': os.path.exists(DASHBOARD), 'updated_at': mtime})


@app.route('/update', methods=['POST'])
def update_dashboard():
    """
    Recibe el HTML del dashboard generado localmente y lo persiste en Railway.
    Headers requeridos:
        X-Update-Key: <clave secreta>
        Content-Type: text/html  (o application/octet-stream)
    Body: contenido HTML del dashboard
    """
    key = request.headers.get('X-Update-Key', '')
    if not hmac.compare_digest(key, UPDATE_KEY):
        abort(403)

    html = request.get_data(as_text=True)
    if not html or len(html) < 100:
        return jsonify({'error': 'HTML vacío o muy corto'}), 400

    os.makedirs(os.path.dirname(DASHBOARD), exist_ok=True)
    with open(DASHBOARD, 'w', encoding='utf-8') as f:
        f.write(html)

    import datetime
    print(f"[update] Dashboard actualizado vía POST — {datetime.datetime.now().isoformat()}")
    return jsonify({'status': 'ok', 'bytes': len(html)}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
