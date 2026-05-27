#!/usr/bin/env python3
"""
regression_snapshots.py  v1.0
Sistema de detección de regresiones para ML 360 Dashboard.

Funciona en dos fases:
  1. save_snapshot()   → guarda métricas clave post-deploy exitoso
  2. check_regression() → en el próximo run, compara nuevas métricas contra snapshot

El objetivo es detectar cuando un cambio rompe datos históricos o genera
variaciones imposibles entre un día y el siguiente.

IMPORTANTE: este sistema NO reemplaza QA. Corre DESPUÉS de QA (si QA pasó).
Si check_regression() detecta regresión → agrega WARNINGs al log pero NO bloquea.
La lógica de bloqueo está en qa_validator.py.
"""

import json
import os
from datetime import datetime, date, timedelta
from typing import Optional

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR      = os.path.join(BASE_DIR, 'data')
SNAPSHOTS_DIR = os.path.join(BASE_DIR, 'data', 'regression_snapshots')
REG_LOG       = os.path.join(BASE_DIR, 'qa_run.log')

os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def _log(msg):
    ts   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"{ts}  {msg}"
    print(line, flush=True)
    with open(REG_LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def _load(name):
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Extractor de métricas clave para snapshot
# ─────────────────────────────────────────────────────────────────────────────

def extract_snapshot_metrics() -> dict:
    """
    Extrae las métricas clave que se monitoreán para regresión.
    Solo incluye métricas que deberían ser estables de un día al siguiente
    (valores acumulados del mes, no valores puntuales de ayer).
    """
    today = date.today()
    mc    = _load('metrics_current') or {}
    ec    = _load('enrich_current')  or {}
    mp    = _load('mp_balance')      or {}
    ads   = _load('ads_daily')       or {}
    items = _load('items')           or []
    pv    = _load('postventa_current') or {}

    # Top 10 items del mes (solo IDs y gmv, para detectar cambios drásticos)
    top10 = [(t.get('id', '?'), round(t.get('gmv', 0)))
             for t in (mc.get('top', [])[:10])]

    # Ads: últimos 7 días
    ads_last7 = {}
    if ads:
        for i in range(1, 8):
            d = (today - timedelta(days=i)).isoformat()
            if d in ads:
                ads_last7[d] = {
                    'roas':   ads[d].get('roas', 0),
                    'cost':   round(ads[d].get('cost', 0)),
                    'spend':  round(ads[d].get('cost', 0)),
                }

    # By logistic_type breakdown
    by_log = {k: {'gmv': round(v.get('gmv', 0)), 'units': v.get('units', 0)}
              for k, v in (ec.get('by_logistic', {}) or {}).items()} if ec else {}

    snapshot = {
        'snapshot_date':    today.isoformat(),
        'snapshot_time':    datetime.now().isoformat(),

        # Métricas maestras del mes
        'gmv':              mc.get('gmv', 0),
        'units':            mc.get('units', 0),
        'paid_orders':      mc.get('paid', 0),
        'cancelled_orders': mc.get('cancelled', 0),
        'cancel_rate':      mc.get('cancel_rate', 0),
        'avg_ticket':       mc.get('avg_ticket', 0),
        'fees':             mc.get('fees', 0),
        'fee_rate':         mc.get('fee_rate', 0),

        # MP
        'mp_disponible':    mp.get('disponible', 0),
        'mp_a_cobrar':      mp.get('a_cobrar', 0),

        # Catálogo
        'items_count':      len(items),

        # Top 10
        'top10':            top10,

        # Ads
        'ads_last7':        ads_last7,

        # Logística
        'by_logistic':      by_log,

        # Postventa
        'pv_data_present':  bool(pv),
    }

    return snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Guardar snapshot
# ─────────────────────────────────────────────────────────────────────────────

def save_snapshot() -> str:
    """
    Guarda un snapshot de las métricas actuales.
    Retorna el path del archivo guardado.
    """
    today    = date.today().isoformat()
    metrics  = extract_snapshot_metrics()
    fname    = f"snap_{today}_{datetime.now().strftime('%H%M%S')}.json"
    fpath    = os.path.join(SNAPSHOTS_DIR, fname)

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # También guardar como "latest"
    latest = os.path.join(SNAPSHOTS_DIR, 'latest.json')
    with open(latest, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    _log(f"  [REGRESSION] Snapshot guardado: {fname}")
    return fpath


# ─────────────────────────────────────────────────────────────────────────────
# Verificar regresión
# ─────────────────────────────────────────────────────────────────────────────

def check_regression() -> dict:
    """
    Compara las métricas actuales contra el último snapshot.
    Retorna dict con lista de anomalías detectadas.

    Las reglas de comparación son asimétricas:
    - Métricas acumuladas del mes SOLO pueden crecer de un día al siguiente
    - GMV, units, paid_orders: si BAJAN más de 2% → problema grave
    - cancel_rate, fee_rate: no deben cambiar más de 10pp de un día al otro
    - items_count: no debe bajar más de 10% de un día al otro
    """
    latest_path = os.path.join(SNAPSHOTS_DIR, 'latest.json')
    if not os.path.exists(latest_path):
        _log("  [REGRESSION] Sin snapshot previo — primera ejecución, skipping")
        return {'anomalies': [], 'snapshot_missing': True}

    try:
        with open(latest_path, encoding='utf-8') as f:
            prev = json.load(f)
    except Exception as e:
        _log(f"  [REGRESSION] Error cargando snapshot: {e}")
        return {'anomalies': [], 'error': str(e)}

    curr     = extract_snapshot_metrics()
    today    = date.today().isoformat()
    prev_day = prev.get('snapshot_date', '')

    anomalies = []

    def flag(name: str, prev_val, curr_val, detail: str, level: str = "WARNING"):
        anomalies.append({
            'name':    name,
            'level':   level,
            'prev':    prev_val,
            'curr':    curr_val,
            'detail':  detail,
        })
        _log(f"  [REGRESSION] {'🚨' if level=='CRITICAL' else '⚠️'} {name}: {detail}")

    # ─── GMV del mes ───────────────────────────────────────────────────────
    # Solo puede bajar si cambiamos de mes (curr < prev de meses distintos)
    gmv_prev = prev.get('gmv', 0)
    gmv_curr = curr.get('gmv', 0)
    if gmv_prev > 0 and gmv_curr > 0:
        # mismo mes: GMV solo puede crecer o mantenerse
        pct_change = (gmv_curr - gmv_prev) / gmv_prev * 100
        if gmv_curr < gmv_prev * 0.98:  # bajó más de 2%
            flag("regression.gmv_dropped",
                 f"${gmv_prev:,.0f}", f"${gmv_curr:,.0f}",
                 f"GMV bajó {abs(pct_change):.1f}% vs snapshot anterior "
                 f"(${gmv_prev:,.0f} → ${gmv_curr:,.0f}) — posible dato borrado o mes cambiado",
                 "CRITICAL" if pct_change < -10 else "WARNING")

    # ─── Órdenes pagadas ───────────────────────────────────────────────────
    paid_prev = prev.get('paid_orders', 0)
    paid_curr = curr.get('paid_orders', 0)
    if paid_prev > 5 and paid_curr < paid_prev * 0.9:
        flag("regression.paid_orders_dropped",
             paid_prev, paid_curr,
             f"Órdenes pagadas bajaron {paid_prev} → {paid_curr} ({(paid_curr-paid_prev)/paid_prev*100:.1f}%)",
             "WARNING")

    # ─── Ticket promedio ───────────────────────────────────────────────────
    avg_prev = prev.get('avg_ticket', 0)
    avg_curr = curr.get('avg_ticket', 0)
    if avg_prev > 0 and avg_curr > 0:
        pct = abs(avg_curr - avg_prev) / avg_prev * 100
        if pct > 30:
            flag("regression.avg_ticket_jump",
                 f"${avg_prev:,.0f}", f"${avg_curr:,.0f}",
                 f"Ticket promedio cambió {pct:.1f}% en 1 día (de ${avg_prev:,.0f} a ${avg_curr:,.0f})",
                 "WARNING" if pct < 60 else "CRITICAL")

    # ─── Fee rate ──────────────────────────────────────────────────────────
    fee_prev = prev.get('fee_rate', 0)
    fee_curr = curr.get('fee_rate', 0)
    if fee_prev > 0 and fee_curr > 0:
        diff_pp = abs(fee_curr - fee_prev)
        if diff_pp > 10:
            flag("regression.fee_rate_jump",
                 f"{fee_prev:.1f}%", f"{fee_curr:.1f}%",
                 f"fee_rate cambió {diff_pp:.1f}pp en 1 día ({fee_prev:.1f}% → {fee_curr:.1f}%)",
                 "WARNING")

    # ─── Cancel rate ───────────────────────────────────────────────────────
    cr_prev = prev.get('cancel_rate', 0)
    cr_curr = curr.get('cancel_rate', 0)
    diff_cr = abs(cr_curr - cr_prev)
    if diff_cr > 15:
        flag("regression.cancel_rate_jump",
             f"{cr_prev:.1f}%", f"{cr_curr:.1f}%",
             f"cancel_rate cambió {diff_cr:.1f}pp en 1 día ({cr_prev:.1f}% → {cr_curr:.1f}%)",
             "WARNING")

    # ─── Items count ───────────────────────────────────────────────────────
    ic_prev = prev.get('items_count', 0)
    ic_curr = curr.get('items_count', 0)
    if ic_prev > 0 and ic_curr < ic_prev * 0.85:
        flag("regression.items_count_drop",
             ic_prev, ic_curr,
             f"Catálogo bajó de {ic_prev} a {ic_curr} items ({(ic_curr-ic_prev)/ic_prev*100:.1f}%)",
             "WARNING")

    # ─── Top 10 cambios radicales ──────────────────────────────────────────
    top_prev = {t[0]: t[1] for t in (prev.get('top10') or []) if t}
    top_curr = {t[0]: t[1] for t in (curr.get('top10') or []) if t}
    # Items que estaban en top10 y desaparecieron completamente
    disappeared = [iid for iid in top_prev if iid not in top_curr and top_prev[iid] > 50_000]
    if disappeared:
        flag("regression.top10_items_disappeared",
             list(top_prev.keys()), list(top_curr.keys()),
             f"Items del top10 que desaparecieron: {disappeared[:3]}",
             "WARNING")

    # Items del top10 cuyo GMV bajó más de 50% (posible dato perdido)
    for iid in top_prev:
        if iid in top_curr:
            p = top_prev[iid]
            c = top_curr[iid]
            if p > 100_000 and c < p * 0.5:
                flag(f"regression.top10.{iid[:10]}_gmv_drop",
                     f"${p:,.0f}", f"${c:,.0f}",
                     f"Item {iid}: GMV bajó {(c-p)/p*100:.0f}% (${p:,.0f} → ${c:,.0f})",
                     "WARNING")

    # ─── MP a_cobrar ───────────────────────────────────────────────────────
    ac_prev = prev.get('mp_a_cobrar', 0)
    ac_curr = curr.get('mp_a_cobrar', 0)
    if ac_prev > 0 and ac_curr > 0:
        pct_ac = (ac_curr - ac_prev) / ac_prev * 100
        if pct_ac < -50:
            flag("regression.mp_a_cobrar_drop",
                 f"${ac_prev:,.0f}", f"${ac_curr:,.0f}",
                 f"a_cobrar bajó {abs(pct_ac):.0f}% (${ac_prev:,.0f} → ${ac_curr:,.0f}) — ¿cobro masivo?",
                 "WARNING")

    result = {
        'prev_snapshot_date': prev_day,
        'curr_date':          today,
        'anomalies':          anomalies,
        'anomaly_count':      len(anomalies),
        'critical_count':     sum(1 for a in anomalies if a['level'] == 'CRITICAL'),
    }

    if not anomalies:
        _log(f"  [REGRESSION] ✅ Sin regresiones detectadas vs snapshot {prev_day}")
    else:
        _log(f"  [REGRESSION] {len(anomalies)} anomalías vs snapshot {prev_day}")

    # Guardar resultado
    reg_path = os.path.join(DATA_DIR, 'regression_last_result.json')
    with open(reg_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Listar snapshots disponibles
# ─────────────────────────────────────────────────────────────────────────────

def list_snapshots() -> list:
    """Lista todos los snapshots disponibles ordenados por fecha."""
    snaps = []
    if not os.path.exists(SNAPSHOTS_DIR):
        return snaps
    for fname in sorted(os.listdir(SNAPSHOTS_DIR)):
        if fname.startswith('snap_') and fname.endswith('.json'):
            fpath = os.path.join(SNAPSHOTS_DIR, fname)
            try:
                with open(fpath, encoding='utf-8') as f:
                    s = json.load(f)
                snaps.append({
                    'file':   fname,
                    'date':   s.get('snapshot_date'),
                    'gmv':    s.get('gmv', 0),
                    'paid':   s.get('paid_orders', 0),
                })
            except Exception:
                pass
    return snaps


if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'

    if cmd == 'save':
        path = save_snapshot()
        print(f"Snapshot guardado: {path}")

    elif cmd == 'check':
        result = check_regression()
        if result.get('anomalies'):
            print(f"\n⚠️  {result['anomaly_count']} anomalías detectadas:")
            for a in result['anomalies']:
                print(f"   [{a['level']}] {a['name']}: {a['detail']}")
        else:
            print("✅ Sin regresiones detectadas")

    elif cmd == 'list':
        snaps = list_snapshots()
        print(f"\n{len(snaps)} snapshots disponibles:")
        for s in snaps[-10:]:
            print(f"   {s['date']}  GMV=${s['gmv']:,.0f}  órdenes={s['paid']}")

    else:
        print(f"Uso: python regression_snapshots.py [save|check|list]")
