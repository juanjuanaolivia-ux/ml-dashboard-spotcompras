"""
fetch_ship_performance.py
Obtiene métricas de Desempeño en Envíos (Flex + Colecta) desde la API
interna de Mercado Libre, usando las cookies de sesión del browser Chrome.

Endpoints descubiertos vía inspección de red:
  /api/soe-performance-widgets/module/current_performance?logistic=<L>&nodeId=<N>
  /api/soe-performance-widgets/module/next_performance?logistic=<L>

Guarda: data/shipment_performance.json
"""
import os, sys, json
from datetime import datetime, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
sys.path.insert(0, SCRIPT_DIR)

BASE_URL  = "https://www.mercadolibre.com.ar"
NODE_ID   = "ARP1545035221"   # Nodo del vendedor (Flex usa nodeId; Colecta no lo necesita)

LOGISTICS = {
    "flex":    {"param": "self_service",  "use_node": True,  "label": "Envíos Flex"},
    "colecta": {"param": "cross_docking", "use_node": False, "label": "Envíos con Colecta"},
}


def _get_chrome_session():
    """
    Intenta obtener una sesión requests con las cookies de Chrome.
    Requiere: pip install browser-cookie3 requests
    """
    try:
        import browser_cookie3, requests
        cookies = browser_cookie3.chrome(domain_name=".mercadolibre.com.ar")
        s = requests.Session()
        s.cookies.update(cookies)
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": f"{BASE_URL}/metricas/desempeno-en-envios",
        })
        return s
    except ImportError:
        print("  ⚠️  browser_cookie3 no instalado. Instalar con: pip install browser-cookie3 requests")
        return None
    except Exception as e:
        print(f"  ⚠️  No se pudieron obtener cookies de Chrome: {e}")
        return None


def _parse_current(data: dict) -> dict:
    """Extrae exposición actual del endpoint current_performance."""
    try:
        d = data["updateBricks"][0]["data"]
        perf     = d.get("performance") or {}
        benefits = d.get("benefits") or []
        detail   = ". ".join(
            (b.get("text", "") +
             (" " + b["badge"]["text"] if b.get("badge") else "") +
             (" " + b.get("textSuffix", "") if b.get("textSuffix") else "")).strip()
            for b in benefits
        )
        return {
            "exposure_actual":        perf.get("title", ""),
            "exposure_actual_detail": detail,
        }
    except Exception:
        return {"exposure_actual": "", "exposure_actual_detail": ""}


def _parse_next(data: dict) -> dict:
    """Extrae exposición prevista y métricas del endpoint next_performance."""
    try:
        d       = data["updateBricks"][0]["data"]
        perf    = d.get("performance") or {}
        msg     = (d.get("message") or "").replace("<b>", "").replace("</b>", "").replace('"', '"').strip()
        metrics = d.get("metrics") or {}
        values  = metrics.get("values") or []

        # El primer value suele ser el período acumulado; el segundo "esta semana"
        main  = values[0] if values else {}
        week  = next((v for v in values if "semana" in v.get("title","").lower()), main)

        return {
            "exposure_prevista":        perf.get("title", ""),
            "exposure_prevista_detail": msg,
            "envios_correctos_pct":     week.get("value", ""),
            "envios_correctos_abs":     week.get("description", ""),
            "periodo":                  week.get("title", ""),
            "umbral":                   "97%",
        }
    except Exception:
        return {
            "exposure_prevista": "", "exposure_prevista_detail": "",
            "envios_correctos_pct": "", "envios_correctos_abs": "",
            "periodo": "", "umbral": "97%",
        }


def fetch(session=None) -> dict:
    """
    Llama a los endpoints de ML y construye shipment_performance.json.
    `session` puede ser una requests.Session ya autenticada, o None para
    intentar obtenerla desde las cookies de Chrome.
    """
    print("\n  🚚 Fetching desempeño en envíos (Flex + Colecta)...")

    if session is None:
        session = _get_chrome_session()
    if session is None:
        print("  ⚠️  Sin sesión disponible — shipment_performance.json no se actualizará.")
        return {}

    result = {"fetched_at": date.today().isoformat()}

    for key, cfg in LOGISTICS.items():
        logistic = cfg["param"]
        label    = cfg["label"]
        try:
            # current_performance
            url_cur = f"{BASE_URL}/api/soe-performance-widgets/module/current_performance?logistic={logistic}"
            if cfg["use_node"]:
                url_cur += f"&nodeId={NODE_ID}"
            r_cur = session.get(url_cur, timeout=15)
            cur_data = r_cur.json() if r_cur.status_code == 200 and r_cur.text != "null" else {}

            # next_performance
            url_nxt = f"{BASE_URL}/api/soe-performance-widgets/module/next_performance?logistic={logistic}"
            r_nxt = session.get(url_nxt, timeout=15)
            nxt_data = r_nxt.json() if r_nxt.status_code == 200 and r_nxt.text != "null" else {}

            if not cur_data and not nxt_data:
                print(f"  ⚠️  {label}: respuesta vacía (sesión expirada?)")
                continue

            entry = {"type": key, "label": label}
            entry.update(_parse_current(cur_data) if cur_data else {})
            entry.update(_parse_next(nxt_data)    if nxt_data else {})
            result[key] = entry

            exp_a = entry.get("exposure_actual", "?")
            exp_p = entry.get("exposure_prevista", "?")
            pct   = entry.get("envios_correctos_pct", "?")
            print(f"  ✅ {label}: actual={exp_a} | prevista={exp_p} | envíos={pct}")

        except Exception as e:
            print(f"  ⚠️  {label}: error → {e}")

    if len(result) > 1:  # tiene al menos un logistic además de fetched_at
        out = os.path.join(DATA_DIR, "shipment_performance.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  💾 Guardado: shipment_performance.json")
    else:
        print("  ⚠️  No se obtuvo data — archivo no actualizado.")

    return result


def run(session=None):
    """Punto de entrada para run_daily.py."""
    return fetch(session=session)


if __name__ == "__main__":
    # Instalar dependencias si faltan
    try:
        import browser_cookie3, requests
    except ImportError:
        print("Instalando dependencias...")
        os.system(f"{sys.executable} -m pip install browser-cookie3 requests --quiet")

    result = fetch()
    print(json.dumps(result, indent=2, ensure_ascii=False))
