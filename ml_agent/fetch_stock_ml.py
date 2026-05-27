"""
fetch_stock_ml.py
Genera stock_status.json desde la API de ML (no depende de STATUS.xlsx).

Obtiene todos los items activos del vendedor con:
  - available_quantity (stock disponible)
  - logistic_type (Full / Flex / Colecta)
  - sold_quantity (para estimar días de cobertura)

Guarda: data/stock_status.json — mismo formato esperado por ml_dashboard.py
"""
import os, sys, json
from datetime import datetime, date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "data")
sys.path.insert(0, SCRIPT_DIR)


def fetch(session=None) -> list:
    print("\n  📦 Fetching stock desde ML API...")
    if session is None:
        from ml_auth import MLSession
        session = MLSession()

    uid = session.user_id

    # 1. Obtener IDs de items activos
    all_ids = []
    offset  = 0
    while True:
        r = session.get(f"/users/{uid}/items/search",
                        params={"status": "active", "limit": 100, "offset": offset})
        batch = r.get("results", [])
        if not batch:
            break
        all_ids.extend(batch)
        total = r.get("paging", {}).get("total", 0)
        offset += 100
        if offset >= total or offset >= 2000:   # cap en 2000 items
            break

    print(f"  📋 {len(all_ids)} items activos")
    if not all_ids:
        return []

    # 2. Obtener detalles en lotes de 20
    items_detail = []
    for i in range(0, len(all_ids), 20):
        batch_ids = ",".join(all_ids[i:i+20])
        try:
            r2 = session.get("/items", params={"ids": batch_ids,
                             "attributes": "id,title,available_quantity,sold_quantity,logistic_type,category_id"})
            for entry in (r2 if isinstance(r2, list) else []):
                body = entry.get("body", {})
                if body and body.get("id"):
                    items_detail.append(body)
        except Exception as e:
            print(f"  ⚠️  Batch {i//20+1}: {e}")
            continue

    print(f"  ✅ {len(items_detail)} items con detalle")

    # Cargar cat_names.json para resolver MLA IDs a nombres legibles
    # (generado por run_daily.py paso 1.5, antes que este paso 1.14)
    cat_names_path = os.path.join(DATA_DIR, "cat_names.json")
    _cat_names = {}
    if os.path.exists(cat_names_path):
        try:
            with open(cat_names_path, encoding="utf-8") as _f:
                _cat_names = json.load(_f)
            print(f"  cat_names cargado: {len(_cat_names)} categorias")
        except Exception:
            pass

    # 3. Calcular ventas últimos 30 días para estimar días de cobertura
    # Usamos orders_current.json si existe (ya calculado por el pipeline)
    # ESTRUCTURA: cada orden tiene o["items"] = [{item_id, quantity, ...}]
    ventas_sku = {}
    orders_path = os.path.join(DATA_DIR, "orders_current.json")
    if os.path.exists(orders_path):
        try:
            with open(orders_path, encoding="utf-8") as f:
                orders = json.load(f)
            cutoff = (date.today() - timedelta(days=30)).isoformat()
            for o in orders:
                if (o.get("date_created", "") >= cutoff and
                        o.get("status") == "paid"):
                    # FIX: los items estan en o["items"][] con keys item_id/quantity
                    for it in o.get("items", []):
                        item_id = it.get("item_id")
                        qty = it.get("quantity", 1) or 1
                        if item_id:
                            ventas_sku[item_id] = ventas_sku.get(item_id, 0) + qty
        except Exception:
            pass

    # 4. Construir resultado
    result = []
    for item in items_detail:
        item_id  = item.get("id", "")
        stock    = item.get("available_quantity", 0) or 0
        sold_30d = ventas_sku.get(item_id, 0)

        # Días de stock: si vendemos N/30 por día, tenemos stock/(N/30) días
        if sold_30d > 0:
            dias = round(stock / (sold_30d / 30))
            if dias == 0:
                dias_label = "QUIEBRE"
            elif dias <= 7:
                dias_label = f"{dias}D"
            elif dias <= 30:
                dias_label = f"{dias}D"
            else:
                dias_label = f"{dias}D"
        else:
            dias_label = "S/MOV" if stock > 0 else "QUIEBRE"

        logistic = item.get("logistic_type", "")
        log_map  = {"fulfillment": "Full", "cross_docking": "Flex",
                    "self_service": "Colecta", "default_buying_flow": "Colecta"}

        result.append({
            "codigo":       item_id,
            "descripcion":  (item.get("title") or "")[:80],
            "categoria":    _cat_names.get(item.get("category_id", ""), item.get("category_id", "")),
            "sub_cat":      "",
            "marca":        "",
            "dias_stock":   dias_label,
            "activado":     "SI",
            "stock_total":  stock,
            "stock_dep":    stock,
            "stock_full":   stock if logistic == "fulfillment" else 0,
            "stock_aduana": 0,
            "vta_semana":   round(sold_30d / 4) if sold_30d else 0,
            "vta_mes":      sold_30d,
        })

    # Ordenar por quiebre primero, luego por stock ascendente
    result.sort(key=lambda x: (0 if x["dias_stock"] == "QUIEBRE" else 1, x["stock_total"]))

    out = os.path.join(DATA_DIR, "stock_status.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    quiebres = sum(1 for x in result if x["dias_stock"] == "QUIEBRE")
    print(f"  💾 stock_status.json: {len(result)} SKUs | {quiebres} quiebres")
    return result


def run(session=None):
    """Punto de entrada para run_daily.py."""
    return fetch(session=session)


if __name__ == "__main__":
    fetch()
