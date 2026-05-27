"""
fetch_claims_analysis.py
Fetchea claims y mediations desde ML API y genera data/claims_analysis.json

NOTA: La ML Claims API requiere scope especial (post-sale) no disponible en el
flujo OAuth estandar. Si la API no esta disponible, mantiene el archivo existente.
Llamar desde run_daily.py como paso independiente.
"""
import json, os, sys
from datetime import date, timedelta
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')

CLAIMS_PATH = os.path.join(DATA, 'claims_analysis.json')


def _save(obj):
    with open(CLAIMS_PATH, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


def _load_existing():
    """Carga el archivo existente si existe."""
    try:
        if os.path.exists(CLAIMS_PATH):
            return json.load(open(CLAIMS_PATH, encoding='utf-8'))
    except Exception:
        pass
    return None


def run(session=None):
    if session is None:
        sys.path.insert(0, BASE)
        from ml_auth import MLSession
        session = MLSession()

    today     = date.today()
    date_from = (today - timedelta(days=60)).strftime('%Y-%m-%d')

    print(f"  [claims] Fetching abiertos y cerrados desde {date_from}...")

    api_success = False

    # --- Claims abiertos ---
    opened = []
    try:
        opened = session.get_paginated(
            "/claims/search",
            params={"role": "respondent", "status": "opened",
                    "date_created_from": date_from},
            limit=50
        )
        print(f"  [claims] opened: {len(opened)}")
        api_success = True
    except Exception as e:
        print(f"  [claims] WARN opened: {e}")

    # --- Claims cerrados ---
    closed = []
    try:
        closed = session.get_paginated(
            "/claims/search",
            params={"role": "respondent", "status": "closed",
                    "date_created_from": date_from},
            limit=50
        )
        print(f"  [claims] closed: {len(closed)}")
        api_success = True
    except Exception as e:
        print(f"  [claims] WARN closed: {e}")

    # --- Mediaciones (devoluciones) ---
    mediations = []
    try:
        mediations = session.get_paginated(
            "/mediations/search",
            params={"role": "respondent", "date_from": date_from},
            limit=50
        )
        print(f"  [claims] mediations: {len(mediations)}")
        api_success = True
    except Exception as e:
        print(f"  [claims] WARN mediations: {e}")

    # --- Si NINGUNA API funciono, mantener datos existentes ---
    if not api_success:
        existing = _load_existing()
        if existing:
            print(f"  [claims] API no disponible (scope faltante). Manteniendo claims_analysis.json existente.")
            return existing
        else:
            print(f"  [claims] API no disponible y no hay datos existentes. Saltando.")
            return None

    # --- Procesar abiertos ---
    urgente  = 0
    disputa  = 0
    opened_detail   = []
    activos_by_sku  = defaultdict(int)

    for c in opened:
        stage = (c.get('stage') or '').lower()
        if 'claim' in stage:
            urgente += 1
        elif 'dispute' in stage or 'mediaci' in stage:
            disputa += 1

        resource = c.get('resource') or {}
        item_id  = resource.get('item', {}).get('id') if isinstance(resource, dict) else None
        res_id   = c.get('resource_id') or c.get('order_id')

        if item_id:
            activos_by_sku[item_id] += 1

        opened_detail.append({
            'id':           c.get('id'),
            'stage':        c.get('stage'),
            'date_created': c.get('date_created', '')[:10],
            'reason_id':    c.get('reason_id'),
            'item_id':      item_id,
            'order_id':     res_id,
        })

    # --- Procesar cerrados ---
    buyer_wins  = 0
    mixed_res   = 0
    seller_wins = 0
    by_reason   = defaultdict(int)
    by_benef    = defaultdict(int)
    by_closed_by = defaultdict(int)
    closed_med  = []
    closed_ret  = []

    for c in closed:
        res      = (c.get('resolution') or {})
        benef    = (res.get('benefited') or '').lower()
        reason   = c.get('reason_id') or c.get('type') or 'unknown'
        closed_by = res.get('closed_by') or 'unknown'
        by_reason[reason]      += 1
        by_benef[benef]        += 1
        by_closed_by[closed_by] += 1
        if 'buyer' in benef:
            buyer_wins += 1
        elif 'seller' in benef:
            seller_wins += 1
        else:
            mixed_res += 1
        row = {
            'id':           c.get('id'),
            'stage':        c.get('stage'),
            'reason_id':    reason,
            'date_created': c.get('date_created', '')[:10],
            'date_closed':  res.get('date_created', '')[:10] if res else '',
            'benefited':    benef,
            'closed_by':    closed_by,
        }
        if 'return' in reason.lower() or 'devol' in reason.lower():
            closed_ret.append(row)
        else:
            closed_med.append(row)

    total_closed_real = len(closed)

    # --- Procesar mediaciones ---
    cancel_purchase = sum(
        1 for m in mediations
        if 'cancel' in (m.get('status') or '').lower()
    )

    result = {
        'summary': {
            'total_opened':        len(opened),
            'urgente_claim_stage': urgente,
            'dispute_stage':       disputa,
            'total_closed_real':   total_closed_real,
            'mediaciones_closed':  len(closed_med),
            'returns_closed':      len(closed_ret),
            'cancel_purchase':     cancel_purchase,
            'buyer_wins_closed':   buyer_wins,
            'mixed_closed':        mixed_res,
            'seller_wins_closed':  seller_wins,
        },
        'opened_detail':      opened_detail,
        'closed_mediaciones': closed_med,
        'closed_returns':     closed_ret,
        'closed_combined': {
            'by_reason':    dict(by_reason),
            'by_benefited': dict(by_benef),
            'by_closed_by': dict(by_closed_by),
        },
        'activos_by_sku': dict(activos_by_sku),
    }

    _save(result)
    print(f"  [claims] OK — {len(opened)} abiertos, {total_closed_real} cerrados -> claims_analysis.json")
    return result


if __name__ == '__main__':
    run()
