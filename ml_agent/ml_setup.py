"""
ml_setup.py — Configuración inicial del agente Mercado Libre
Ejecutar UNA SOLA VEZ para guardar credenciales y autorizar la app.

Uso:
  python ml_setup.py              → configura client_id, secret y redirect_uri
  python ml_setup.py --authorize  → lanza el flujo OAuth y guarda los tokens
  python ml_setup.py --check      → verifica que todo esté funcionando
"""

import sys
import os
import json

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "ml_config.json")
TOKEN_FILE  = os.path.join(SCRIPT_DIR, "ml_tokens.json")


def setup_credentials():
    print("\n" + "="*60)
    print("  CONFIGURACIÓN DEL AGENTE MERCADO LIBRE")
    print("="*60)
    print("\n  Necesito tus credenciales de la app en:")
    print("  https://developers.mercadolibre.com.ar/\n")

    client_id     = input("  App ID (client_id):     ").strip()
    client_secret = input("  Secret Key (client_secret): ").strip()
    redirect_uri  = input("  Redirect URI (la que configuraste en la app): ").strip()

    cfg = {
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  redirect_uri,
        "site_id":       "MLA",
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"\n  ✅ Credenciales guardadas en {CONFIG_FILE}")
    print("  Ahora ejecutá: python ml_setup.py --authorize\n")


def check_setup():
    print("\n  🔍 Verificando configuración...\n")

    # Config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        print(f"  ✅ Credenciales: client_id={cfg.get('client_id', '?')[:8]}***")
    else:
        print("  ❌ No hay credenciales. Ejecutá: python ml_setup.py")
        return False

    # Tokens
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tokens = json.load(f)
        import time
        expires_at = tokens.get("expires_at", 0)
        remaining  = max(0, int(expires_at - time.time()))
        print(f"  ✅ Tokens encontrados. User ID: {tokens.get('user_id')}")
        print(f"     Access token expira en: {remaining // 3600}h {(remaining % 3600) // 60}m")
    else:
        print("  ❌ No hay tokens. Ejecutá: python ml_setup.py --authorize")
        return False

    # Test API call
    try:
        from ml_auth import MLSession
        session = MLSession()
        user    = session.get("/users/me")
        print(f"  ✅ Conexión a ML API OK. Vendedor: {user.get('nickname')}")
        print(f"     Reputación: {user.get('seller_reputation', {}).get('level_id', 'N/A')}")
        return True
    except Exception as e:
        print(f"  ❌ Error al conectar a la API: {e}")
        return False


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--authorize":
        from ml_auth import run_authorization_flow
        run_authorization_flow()

    elif arg == "--check":
        ok = check_setup()
        sys.exit(0 if ok else 1)

    else:
        setup_credentials()
        print("  Siguiente paso: python ml_setup.py --authorize")
