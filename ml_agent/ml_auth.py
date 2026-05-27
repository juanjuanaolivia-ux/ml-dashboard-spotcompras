"""
ml_auth.py — Autenticación OAuth 2.0 para Mercado Libre Argentina
Maneja: autorización, intercambio de código, refresh automático, persistencia de tokens
"""

import json
import os
import time
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs
import requests

# ── Rutas ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "ml_config.json")
TOKEN_FILE  = os.path.join(SCRIPT_DIR, "ml_tokens.json")

# ── URLs de ML Argentina ────────────────────────────────────────────────────
AUTH_URL    = "https://auth.mercadolibre.com.ar/authorization"
TOKEN_URL   = "https://api.mercadolibre.com/oauth/token"
API_BASE    = "https://api.mercadolibre.com"
SITE_ID     = "MLA"


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"No se encontró {CONFIG_FILE}.\n"
            "Ejecutá: python ml_setup.py  para configurar las credenciales."
        )
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Token management
# ─────────────────────────────────────────────────────────────────────────────

def load_tokens() -> dict | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_tokens(tokens: dict):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    print(f"  ✅ Tokens guardados en {TOKEN_FILE}")


def is_token_expired(tokens: dict, buffer_seconds: int = 300) -> bool:
    """Devuelve True si el access_token expira en menos de buffer_seconds."""
    expires_at = tokens.get("expires_at", 0)
    return time.time() >= (expires_at - buffer_seconds)


def refresh_access_token(tokens: dict, cfg: dict) -> dict:
    """Usa el refresh_token para obtener un nuevo access_token."""
    print("  🔄 Renovando access_token...")
    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": tokens["refresh_token"],
    }, timeout=20)
    resp.raise_for_status()
    new_tokens = resp.json()
    new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 21600)
    # Preservar user_id si no viene en el refresh
    if "user_id" not in new_tokens and "user_id" in tokens:
        new_tokens["user_id"] = tokens["user_id"]
    save_tokens(new_tokens)
    print("  ✅ Token renovado correctamente.")
    return new_tokens


def get_valid_token() -> tuple[str, int]:
    """
    Devuelve (access_token, user_id) válidos.
    Refresca automáticamente si está por vencer.
    """
    cfg    = load_config()
    tokens = load_tokens()

    if tokens is None:
        raise RuntimeError(
            "No hay tokens guardados.\n"
            "Ejecutá primero: python ml_setup.py --authorize"
        )

    if is_token_expired(tokens):
        tokens = refresh_access_token(tokens, cfg)

    return tokens["access_token"], tokens["user_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Flujo de autorización inicial (se corre una sola vez)
# ─────────────────────────────────────────────────────────────────────────────

def get_authorization_url(cfg: dict) -> str:
    params = {
        "response_type": "code",
        "client_id":     cfg["client_id"],
        "redirect_uri":  cfg["redirect_uri"],
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, cfg: dict) -> dict:
    """Intercambia el authorization_code por access_token + refresh_token."""
    print("  🔄 Intercambiando código por tokens...")
    resp = requests.post(TOKEN_URL, data={
        "grant_type":   "authorization_code",
        "client_id":    cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code":          code,
        "redirect_uri":  cfg["redirect_uri"],
    })
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 21600)
    save_tokens(tokens)
    return tokens


def run_authorization_flow():
    """
    Flujo interactivo de autorización inicial.
    Abre el navegador, pide el código de retorno y guarda los tokens.
    """
    cfg = load_config()
    url = get_authorization_url(cfg)

    print("\n" + "="*60)
    print("  AUTORIZACIÓN MERCADO LIBRE")
    print("="*60)
    print("\n  Se va a abrir tu navegador para que autorices la app.")
    print(f"\n  Si no se abre, copiá esta URL manualmente:\n  {url}\n")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("  Después de autorizar, ML te va a redirigir a una URL como:")
    print("  https://tu-redirect-uri/?code=TG-XXXXXXXXXXXX\n")

    redirect_url = input("  Pegá acá la URL completa de redirección (o solo el código): ").strip()

    # Extraer el code de la URL o usarlo directo
    if redirect_url.startswith("http"):
        parsed = urlparse(redirect_url)
        code = parse_qs(parsed.query).get("code", [None])[0]
    else:
        code = redirect_url

    if not code:
        raise ValueError("No se pudo extraer el código de autorización.")

    tokens = exchange_code_for_token(code, cfg)
    print(f"\n  ✅ ¡Autorización exitosa! User ID: {tokens.get('user_id')}")
    print("  A partir de ahora, el agente se autentica automáticamente.\n")
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Sesión HTTP con auth automática
# ─────────────────────────────────────────────────────────────────────────────

class MLSession:
    """Wrapper de requests que inyecta el Bearer token automáticamente."""

    def __init__(self):
        self._token, self._user_id = get_valid_token()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Content-Type":  "application/json",
        })

    @property
    def user_id(self) -> int:
        return self._user_id

    def get(self, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        kwargs.setdefault('timeout', 30)
        resp = self._session.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_paginated(self, path: str, params: dict = None, limit: int = 50) -> list:
        """
        Itera sobre resultados paginados de la API.
        Acumula todos los resultados hasta agotar las páginas.
        """
        params = params or {}
        params["limit"]  = limit
        params["offset"] = 0
        results = []

        while True:
            data = self.get(path, params=params)

            # Detectar estructura de respuesta (orders, items, claims, etc.)
            items = (
                data.get("results") or
                data.get("orders")  or
                data.get("elements") or
                []
            )
            results.extend(items)

            total  = data.get("paging", {}).get("total", len(results))
            offset = data.get("paging", {}).get("offset", 0)

            if offset + limit >= total or not items:
                break

            params["offset"] += limit

        return results
