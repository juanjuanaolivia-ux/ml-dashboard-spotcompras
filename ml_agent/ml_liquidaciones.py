"""
ml_liquidaciones.py — Módulo aislado de Liquidaciones & Conciliación Financiera
Fase 1: fetch /collections/search -> datasets -> JSON en data/
NO modifica ningun otro modulo.
"""
import json, os, sys, time, requests as _req
from datetime import date, timedelta, datetime
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')


def _save(name, data):
    with open(os.path.join(DATA_DIR, f'{name}.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def _load(name):
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p): return None
    with open(p, encoding='utf-8') as f: return json.load(f)


def _token():
    with open(os.path.join(BASE_DIR, 'ml_tokens.json')) as f:
        return json.load(f)['access_token']


# ---------------------------------------------------------------------------
# 1. FETCH COLLECTIONS
# ---------------------------------------------------------------------------

def fetch_collections(session, days_back=40):
    today     = date.today()
    date_from = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')
    print(f"\n  Fetching collections desde {date_from}...")

    tok = _token()
    all_results = []
    offset = 0

    while True:
        try:
            r = _req.get(
                'https://api.mercadolibre.com/collections/search',
                headers={'Authorization': f'Bearer {tok}'},
                params={'seller_id': session.user_id, 'sort': 'date_created',
                        'criteria': 'desc', 'offset': offset, 'limit': 50},
                timeout=20
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"\n  Error offset={offset}: {e}")
            break

        results = data.get('results', [])
        if not results:
            break

        stop = False
        for item in results:
            c = item.get('collection', item)
            rec_date = (c.get('date_created') or '')[:10]
            if rec_date < date_from:
                stop = True
                break
            all_results.append(c)

        offset += len(results)
        print(f"  {len(all_results):,} registros...", end='\r')

        if stop:
            break
        time.sleep(0.12)

    print(f"\n  OK: {len(all_results):,} collections ({date_from} a {today})")
    _save('collections_raw', all_results)
    return all_results


# ---------------------------------------------------------------------------
# 2. BUILD FACT TABLES
# ---------------------------------------------------------------------------

def build_fact_collections(collections_raw):
    facts = []
    for c in collections_raw:
        order_id_raw = c.get('external_reference') or c.get('transaction_order_id') or ''
        order_id = int(order_id_raw) if str(order_id_raw).isdigit() else None
        facts.append({
            'payment_id':          c.get('id'),
            'order_id':            order_id,
            'date_created':        (c.get('date_created') or '')[:10],
            'date_approved':       (c.get('date_approved') or '')[:10],
            'money_release_date':  (c.get('money_release_date') or '')[:10],
            'released':            c.get('released') == 'yes' or c.get('released') is True,
            'status':              c.get('status'),
            'status_detail':       c.get('status_detail'),
            'payment_type':        c.get('payment_type'),
            'installments':        c.get('installments', 1),
            'transaction_amount':  float(c.get('transaction_amount') or 0),
            'total_paid_amount':   float(c.get('total_paid_amount') or 0),
            'net_received_amount': float(c.get('net_received_amount') or 0),
            'shipping_cost':       float(c.get('shipping_cost') or 0),
            'coupon_amount':       float(c.get('coupon_amount') or 0),
            'coupon_fee':          float(c.get('coupon_fee') or 0),
            'mercadopago_fee':     float(c.get('mercadopago_fee') or 0),
            'finance_fee':         float(c.get('finance_fee') or 0),
            'marketplace_fee':     float(c.get('marketplace_fee') or 0),
            'amount_refunded':     float(c.get('amount_refunded') or 0),
            'has_refunds':         bool(c.get('refunds')),
        })
    _save('fact_collections', facts)
    print(f"  fact_collections: {len(facts):,}")
    return facts


def build_fact_conciliacion(fact_collections, orders_current, commissions):
    order_idx = {int(o['order_id']): o for o in orders_current if o.get('order_id')}
    fee_idx = {}
    for c in commissions:
        oid = c.get('order_id')
        if oid:
            fee_idx[int(oid)] = fee_idx.get(int(oid), 0) + float(c.get('sale_fee') or 0)

    coll_by_order = defaultdict(list)
    seen_payment_ids = {}
    dup_flags = set()
    for fc in fact_collections:
        pid = fc['payment_id']
        if pid in seen_payment_ids:
            dup_flags.add(pid)
        seen_payment_ids[pid] = True
        if fc.get('order_id'):
            coll_by_order[fc['order_id']].append(fc)

    conciliacion = []
    TOLERANCE = 1.0

    all_order_ids = set(order_idx.keys()) | set(coll_by_order.keys())
    for oid in all_order_ids:
        order = order_idx.get(oid)
        colls = coll_by_order.get(oid, [])

        gmv_venta   = float(order.get('paid_amount') or order.get('total_amount') or 0) if order else 0
        approved    = [fc for fc in colls if fc['status'] == 'approved']
        gmv_cobrado = sum(fc['transaction_amount'] for fc in approved)
        neto_real   = sum(fc['net_received_amount'] for fc in approved)
        devuelto    = sum(fc['amount_refunded'] for fc in colls)
        fee_ml      = fee_idx.get(oid, 0)
        fee_mp      = sum(fc['mercadopago_fee'] for fc in approved)
        fee_fin     = sum(fc['finance_fee'] for fc in approved)
        shipping    = sum(fc['shipping_cost'] for fc in approved)
        liberado    = sum(fc['net_received_amount'] for fc in approved if fc.get('released'))
        pendiente   = sum(fc['net_received_amount'] for fc in approved if not fc.get('released'))
        has_dup     = any(fc['payment_id'] in dup_flags for fc in colls)
        release_date = min(
            (fc['money_release_date'] for fc in approved
             if fc.get('money_release_date') and not fc.get('released')), default=''
        )
        diff = abs(gmv_venta - gmv_cobrado) if gmv_venta > 0 and gmv_cobrado > 0 else 0

        if not colls and order:
            estado = 'sin_pago'
        elif not order and colls:
            estado = 'cobro_sin_orden'
        elif any(fc['status'] == 'charged_back' for fc in colls):
            estado = 'devuelto'
        elif devuelto > 0:
            estado = 'parcial_devuelto'
        elif diff > TOLERANCE and gmv_venta > 0:
            estado = 'diferencia'
        elif has_dup:
            estado = 'duplicado'
        elif pendiente > 0:
            estado = 'pendiente_liberar'
        else:
            estado = 'conciliado'

        conciliacion.append({
            'order_id':      oid,
            'date':          (order.get('date_created') if order else (colls[0]['date_created'] if colls else ''))[:10],
            'gmv_venta':     round(gmv_venta, 2),
            'gmv_cobrado':   round(gmv_cobrado, 2),
            'neto_real':     round(neto_real, 2),
            'liberado':      round(liberado, 2),
            'pendiente':     round(pendiente, 2),
            'devuelto':      round(devuelto, 2),
            'fee_ml':        round(fee_ml, 2),
            'fee_mp':        round(fee_mp, 2),
            'fee_fin':       round(fee_fin, 2),
            'shipping':      round(shipping, 2),
            'diff_monto':    round(diff, 2),
            'estado':        estado,
            'n_pagos':       len(colls),
            'release_date':  release_date,
            'has_duplicate': has_dup,
        })

    _save('fact_conciliacion', conciliacion)
    print(f"  fact_conciliacion: {len(conciliacion):,}")
    estados = Counter(r['estado'] for r in conciliacion)
    for k, v in sorted(estados.items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")
    return conciliacion


def build_fact_cashflow(fact_collections):
    cf = defaultdict(lambda: {'released': 0.0, 'pending': 0.0, 'refunded': 0.0})
    today_str = date.today().strftime('%Y-%m-%d')
    for fc in fact_collections:
        if fc['status'] != 'approved':
            continue
        d = fc.get('money_release_date') or fc.get('date_approved') or fc.get('date_created')
        if not d: continue
        d = d[:10]
        if fc.get('released'):
            cf[d]['released'] += fc['net_received_amount']
        else:
            cf[d]['pending'] += fc['net_received_amount']
        if fc['amount_refunded'] > 0:
            cf[d]['refunded'] += fc['amount_refunded']

    cashflow = [
        {'date': d, 'released': round(v['released'], 2),
         'pending': round(v['pending'], 2), 'refunded': round(v['refunded'], 2),
         'net': round(v['released'] + v['pending'] - v['refunded'], 2),
         'is_future': d >= today_str}
        for d, v in sorted(cf.items())
    ]
    _save('fact_cashflow', cashflow)
    print(f"  fact_cashflow: {len(cashflow):,} dias")
    return cashflow


def build_liq_summary(fact_conciliacion, fact_collections, fact_cashflow):
    approved = [fc for fc in fact_collections if fc['status'] == 'approved']
    def S(lst, key): return sum(float(x.get(key) or 0) for x in lst)

    gmv          = S(approved, 'transaction_amount')
    cobrado      = S(approved, 'total_paid_amount')
    neto         = S(approved, 'net_received_amount')
    liberado     = sum(fc['net_received_amount'] for fc in approved if fc.get('released'))
    pendiente    = sum(fc['net_received_amount'] for fc in approved if not fc.get('released'))
    devuelto     = S(fact_collections, 'amount_refunded')
    fee_mp       = S(approved, 'mercadopago_fee')
    fee_fin      = S(approved, 'finance_fee')
    shipping_base= S(approved, 'shipping_cost')
    coupon       = S(approved, 'coupon_fee')
    fee_ml       = sum(r['fee_ml'] for r in fact_conciliacion)
    # Shipping real y retenciones desde charges_details enriquecidos (Full + Flex)
    shipping_real = sum(float(r.get('shipping_real', 0)) for r in fact_conciliacion)
    taxes_real    = sum(float(r.get('taxes_real', 0)) for r in fact_conciliacion)

    # Si charges_details individuales no tienen retenciones (devuelven vacío),
    # usar fetch_retenciones.py (payments/search agrega todas las retenciones reales)
    retenciones_es_real = True
    if taxes_real == 0:
        try:
            _ret_path = os.path.join(DATA_DIR, 'retenciones_real.json')
            if os.path.exists(_ret_path):
                _ret_data = json.load(open(_ret_path))
                _ret_month = date.today().strftime('%Y-%m')
                if _ret_data.get('month') == _ret_month and _ret_data.get('total', 0) > 0:
                    taxes_real = _ret_data['total']
                    retenciones_es_real = True
        except Exception:
            retenciones_es_real = False

    # Si charges_details individuales no tienen envíos (devuelven vacío),
    # usar fetch_envios.py (payments/search agrega todos los costos de envío reales)
    envios_es_real = True
    if shipping_real == 0:
        try:
            _env_path = os.path.join(DATA_DIR, 'envios_real.json')
            if os.path.exists(_env_path):
                _env_data = json.load(open(_env_path))
                _env_month = date.today().strftime('%Y-%m')
                if _env_data.get('month') == _env_month and _env_data.get('total', 0) > 0:
                    shipping_real = _env_data['total']
                    envios_es_real = True
        except Exception:
            envios_es_real = False

    # Usar shipping_real si está disponible (incluye Full/Colecta real), si no caer al base
    shipping = shipping_real if shipping_real > 0 else shipping_base
    today_s       = date.today().strftime('%Y-%m-%d')
    proximas      = sum(cf['pending'] for cf in fact_cashflow if cf['is_future'])
    # Segmentación correcta: por money_release_date vs hoy (independiente del flag 'released')
    fc_approved   = [fc for fc in fact_collections if fc['status'] == 'approved']
    lib_estimado  = sum(fc['net_received_amount'] for fc in fc_approved
                        if fc.get('money_release_date','') and fc['money_release_date'] <= today_s)
    pend_real     = sum(fc['net_received_amount'] for fc in fc_approved
                        if fc.get('money_release_date','') and fc['money_release_date'] > today_s)

    alertas = {
        'sin_pago':        sum(1 for r in fact_conciliacion if r['estado'] == 'sin_pago'),
        'diferencia':      sum(1 for r in fact_conciliacion if r['estado'] == 'diferencia'),
        'devuelto':        sum(1 for r in fact_conciliacion if r['estado'] in ('devuelto','parcial_devuelto')),
        'duplicado':       sum(1 for r in fact_conciliacion if r['estado'] == 'duplicado'),
        'cobro_sin_orden': sum(1 for r in fact_conciliacion if r['estado'] == 'cobro_sin_orden'),
    }
    n_total = len(fact_conciliacion)
    n_conc  = sum(1 for r in fact_conciliacion if r['estado'] in ('conciliado','pendiente_liberar'))

    summary = {
        'updated_at':        datetime.now().isoformat(),
        'gmv_total':         round(gmv, 2),
        'cobrado_total':     round(cobrado, 2),
        'neto_total':        round(neto, 2),
        'liberado_total':    round(liberado, 2),
        'pendiente_total':   round(pendiente, 2),
        'proximas_lib':      round(proximas, 2),
        'liberado_estimado': round(lib_estimado, 2),
        'pendiente_real':    round(pend_real, 2),
        'devuelto_total':    round(devuelto, 2),
        'fee_ml_total':      round(fee_ml, 2),
        'fee_mp_total':      round(fee_mp, 2),
        'fee_fin_total':     round(fee_fin, 2),
        'shipping_total':    round(shipping, 2),
        'envios_es_real':    envios_es_real,
        'retenciones_total': round(taxes_real, 2),
        'retenciones_es_real': retenciones_es_real,
        'coupon_total':      round(coupon, 2),
        'fee_rate_pct':      round((fee_ml + fee_mp) / gmv * 100, 2) if gmv else 0,
        'margen_pct':        round(neto / gmv * 100, 2) if gmv else 0,
        'tasa_conciliacion': round(n_conc / n_total * 100, 2) if n_total else 0,
        'total_ordenes':     n_total,
        'conciliadas':       n_conc,
        'alertas':           alertas,
    }
    _save('liq_summary', summary)
    print(f"\n  GMV: ${gmv:,.0f} | Neto: ${neto:,.0f} ({neto/gmv*100:.1f}%)" if gmv else "")
    print(f"  Liberado: ${liberado:,.0f} | Pendiente: ${pendiente:,.0f}")
    print(f"  Conciliacion: {n_conc}/{n_total} ({summary['tasa_conciliacion']:.1f}%)")
    print(f"  Alertas: {alertas}")
    return summary


# ---------------------------------------------------------------------------
# 3. ENTRY POINT
# ---------------------------------------------------------------------------

def run(session=None):
    if session is None:
        sys.path.insert(0, BASE_DIR)
        from ml_auth import MLSession
        session = MLSession()

    print("\n" + "="*50)
    print("  LIQUIDACIONES & CONCILIACION — Fase 1")
    print("="*50)

    collections_raw = fetch_collections(session, days_back=40)
    fact_coll = build_fact_collections(collections_raw)

    orders = _load('orders_current') or []
    # Siempre recomputar comisiones desde órdenes actuales (sale_fee viene embebido en items)
    # Esto evita depender de commissions.json potencialmente desactualizado
    comms = []
    for _o in orders:
        for _i in _o.get('items', []):
            _sf = _i.get('sale_fee')
            if _sf and float(_sf) > 0:
                comms.append({'order_id': _o.get('order_id'), 'sale_fee': float(_sf)})
    if not comms:
        # Fallback: cargar desde archivo si las órdenes no tienen sale_fee
        comms = _load('commissions') or []
    print(f"  Comisiones: {len(comms)} items (fee total: ${sum(c['sale_fee'] for c in comms):,.0f})")

    fact_conc = build_fact_conciliacion(fact_coll, orders, comms)

    # ── Enriquecer con charges_details: shipping real + retenciones ──────────
    try:
        import sys as _sys
        _sys.path.insert(0, BASE_DIR)
        from ml_enrich_charges import fetch_all_charges, build_enriched_conciliacion
        print("\n  Enriqueciendo con charges_details (shipping + retenciones)...")
        tok = _token()
        payment_ids = [int(r['id']) for r in collections_raw if r.get('id')]
        charges_cache = fetch_all_charges(payment_ids, tok, workers=30, force=False)
        fact_conc_enriched = build_enriched_conciliacion(charges_cache)
        # Re-aplicar fee_ml desde fact_conc en memoria (protege contra fact_conciliacion.json stale en disco)
        fee_ml_idx = {r['order_id']: r['fee_ml'] for r in fact_conc}
        for _r in fact_conc_enriched:
            if _r.get('fee_ml', 0) == 0 and _r.get('order_id') in fee_ml_idx:
                _r['fee_ml'] = fee_ml_idx[_r['order_id']]
        fact_conc = fact_conc_enriched
        print(f"  Enriquecido: {len(fact_conc)} registros con shipping/retenciones reales")
    except Exception as _e:
        print(f"  WARN charges_details: {_e} — usando fact_conc base")

    fact_cf = build_fact_cashflow(fact_coll)
    build_liq_summary(fact_conc, fact_coll, fact_cf)
    print("\n  OK: Liquidaciones completadas.")
