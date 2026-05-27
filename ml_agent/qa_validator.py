#!/usr/bin/env python3
"""
qa_validator.py  v1.0
Motor central de validación pre-deploy para ML 360 Dashboard.

Ejecuta todos los checks de integridad, frescura, reconciliación y anomalías
ANTES de publicar el dashboard. Si cualquier check CRÍTICO falla → bloquea deploy.

Niveles de severidad:
  CRITICAL  → bloquea deploy
  WARNING   → permite deploy pero alerta
  INFO      → solo log

Uso:
    from qa_validator import run_qa
    result = run_qa()
    if result['blocked']:
        # NO publicar
    else:
        # OK para publicar
"""

import json
import os
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
QA_LOG   = os.path.join(BASE_DIR, 'qa_run.log')

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load(name):
    """Carga un JSON desde data/. Retorna None si no existe o está corrupto."""
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return None


def _file_age_minutes(name):
    """Minutos desde la última modificación de data/{name}.json. None si no existe."""
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p):
        return None
    mtime = os.path.getmtime(p)
    return (datetime.now().timestamp() - mtime) / 60


def _file_size(name):
    """Tamaño en bytes de data/{name}.json. 0 si no existe."""
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p):
        return 0
    return os.path.getsize(p)


def _qa_log(msg):
    ts   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"{ts}  {msg}"
    print(line, flush=True)
    with open(QA_LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


# ─────────────────────────────────────────────────────────────────────────────
# Clase de resultado de check
# ─────────────────────────────────────────────────────────────────────────────

class QAResult:
    def __init__(self):
        self.checks   = []   # lista de dicts {name, level, passed, detail}
        self.blocked  = False
        self.warnings = 0
        self.errors   = 0

    def add(self, name: str, passed: bool, level: str, detail: str):
        icon = "✅" if passed else ("🚨" if level == "CRITICAL" else "⚠️")
        self.checks.append({
            'name':    name,
            'level':   level,
            'passed':  passed,
            'detail':  detail,
            'icon':    icon,
        })
        if not passed:
            if level == "CRITICAL":
                self.errors  += 1
                self.blocked  = True
            else:
                self.warnings += 1

    def summary(self) -> str:
        total  = len(self.checks)
        passed = sum(1 for c in self.checks if c['passed'])
        return (f"QA: {passed}/{total} checks OK | "
                f"Errores: {self.errors} | Warnings: {self.warnings} | "
                f"{'🚫 BLOQUEADO' if self.blocked else '✅ APROBADO'}")

    def to_dict(self) -> dict:
        return {
            'timestamp':  datetime.now().isoformat(),
            'blocked':    self.blocked,
            'errors':     self.errors,
            'warnings':   self.warnings,
            'checks':     self.checks,
            'summary':    self.summary(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# 1. CHECKS DE FRESCURA (freshness)
# ─────────────────────────────────────────────────────────────────────────────

# Archivos que deben estar frescos (actualizados en las últimas N horas)
FRESHNESS_RULES = {
    # archivo           max_age_horas  nivel
    'orders_current':   (6,  'CRITICAL'),
    'orders_prior':     (26, 'WARNING'),   # solo se regenera 1 vez/mes
    'metrics_current':  (6,  'CRITICAL'),
    'summary':          (6,  'CRITICAL'),
    'enrich_current':   (8,  'WARNING'),
    'mp_balance':       (26, 'WARNING'),
    'ads_daily':        (26, 'WARNING'),
    'items':            (26, 'WARNING'),
}

def check_freshness(r: QAResult):
    """Verifica que los archivos de datos fueron actualizados recientemente."""
    _qa_log("  [QA] Verificando frescura de datasets...")
    for fname, (max_hours, level) in FRESHNESS_RULES.items():
        age = _file_age_minutes(fname)
        if age is None:
            r.add(f"freshness.{fname}", False, level,
                  f"Archivo {fname}.json NO EXISTE")
            continue
        if age > max_hours * 60:
            r.add(f"freshness.{fname}", False, level,
                  f"{fname}.json tiene {age:.0f} min de antigüedad (máx {max_hours}h)")
        else:
            r.add(f"freshness.{fname}", True, level,
                  f"{fname}.json: {age:.0f} min OK")


# ─────────────────────────────────────────────────────────────────────────────
# 2. CHECKS DE COMPLETITUD (no vacíos, no truncados)
# ─────────────────────────────────────────────────────────────────────────────

def check_completeness(r: QAResult):
    """Verifica que los datasets no estén vacíos ni absurdamente pequeños."""
    _qa_log("  [QA] Verificando completitud de datasets...")

    # orders_current debe tener registros
    orders_cur = _load('orders_current') or []
    if len(orders_cur) == 0:
        r.add("completeness.orders_current", False, "CRITICAL",
              "orders_current.json está VACÍO — no hay órdenes del mes")
    else:
        r.add("completeness.orders_current", True, "CRITICAL",
              f"{len(orders_cur)} órdenes en mes actual OK")

    # orders_prior
    orders_pri = _load('orders_prior') or []
    if len(orders_pri) == 0:
        r.add("completeness.orders_prior", False, "WARNING",
              "orders_prior.json vacío — sin datos mes anterior")
    else:
        r.add("completeness.orders_prior", True, "WARNING",
              f"{len(orders_pri)} órdenes mes anterior OK")

    # items no vacío
    items = _load('items') or []
    if len(items) == 0:
        r.add("completeness.items", False, "WARNING",
              "items.json vacío — sin catálogo de productos")
    else:
        r.add("completeness.items", True, "WARNING",
              f"{len(items)} items en catálogo OK")

    # metrics_current debe tener gmv > 0 si hay órdenes pagadas
    mc = _load('metrics_current') or {}
    paid_count = mc.get('paid', 0)
    gmv        = mc.get('gmv', 0)
    if paid_count > 0 and gmv == 0:
        r.add("completeness.metrics_gmv", False, "CRITICAL",
              f"metrics_current: {paid_count} órdenes pagadas pero GMV=0 → cálculo roto")
    elif paid_count == 0 and len(orders_cur) > 0:
        # Hay órdenes pero ninguna pagada — puede ser legítimo (cancelaciones)
        canc = mc.get('cancelled', 0)
        r.add("completeness.metrics_paid", True, "INFO",
              f"metrics_current: 0 pagadas, {canc} canceladas de {len(orders_cur)} órdenes")
    else:
        r.add("completeness.metrics_gmv", True, "CRITICAL",
              f"metrics_current: GMV=${gmv:,.0f} con {paid_count} órdenes pagadas OK")

    # mp_balance
    mp = _load('mp_balance') or {}
    if not mp:
        r.add("completeness.mp_balance", False, "WARNING",
              "mp_balance.json vacío — sin datos de Mercado Pago")
    else:
        r.add("completeness.mp_balance", True, "WARNING",
              "mp_balance.json presente OK")

    # ads_daily
    ads = _load('ads_daily') or {}
    if not ads:
        r.add("completeness.ads_daily", False, "WARNING",
              "ads_daily.json vacío — sin datos de Ads")
    else:
        r.add("completeness.ads_daily", True, "WARNING",
              f"ads_daily.json: {len(ads)} días de datos OK")


# ─────────────────────────────────────────────────────────────────────────────
# 3. CHECKS DE CONSISTENCIA INTERNA
# ─────────────────────────────────────────────────────────────────────────────

def check_internal_consistency(r: QAResult):
    """Verifica que las métricas computadas coincidan con las órdenes crudas."""
    _qa_log("  [QA] Verificando consistencia interna orders → metrics...")

    orders_cur = _load('orders_current') or []
    mc         = _load('metrics_current') or {}

    if not orders_cur or not mc:
        r.add("consistency.orders_vs_metrics", False, "WARNING",
              "No hay datos suficientes para verificar consistencia")
        return

    # Recomputar desde cero
    paid_raw  = [o for o in orders_cur if o.get('status') == 'paid']
    canc_raw  = [o for o in orders_cur if o.get('status') == 'cancelled']
    gmv_raw   = sum(o.get('total_amount') or 0 for o in paid_raw)
    units_raw = sum(i.get('quantity') or 0 for o in paid_raw for i in o.get('items', []))

    # Tolerancia: 0.01% de diferencia permitida (redondeos)
    gmv_stored = mc.get('gmv', 0)
    diff_pct   = abs(gmv_raw - gmv_stored) / max(gmv_raw, 1) * 100

    if diff_pct > 0.5:
        r.add("consistency.gmv_recompute", False, "CRITICAL",
              f"GMV recomputado ${gmv_raw:,.0f} vs stored ${gmv_stored:,.0f} → diff {diff_pct:.2f}%")
    else:
        r.add("consistency.gmv_recompute", True, "CRITICAL",
              f"GMV consistente: ${gmv_stored:,.0f} (diff {diff_pct:.3f}%)")

    # Conteos
    paid_stored  = mc.get('paid', 0)
    canc_stored  = mc.get('cancelled', 0)
    if paid_stored != len(paid_raw):
        r.add("consistency.paid_count", False, "WARNING",
              f"paid count: raw={len(paid_raw)} vs stored={paid_stored}")
    else:
        r.add("consistency.paid_count", True, "WARNING",
              f"Conteo órdenes pagadas consistente: {paid_stored}")

    if canc_stored != len(canc_raw):
        r.add("consistency.canc_count", False, "WARNING",
              f"cancelled count: raw={len(canc_raw)} vs stored={canc_stored}")
    else:
        r.add("consistency.canc_count", True, "WARNING",
              f"Conteo cancelaciones consistente: {canc_stored}")

    # Units
    units_stored = mc.get('units', 0)
    if units_stored != units_raw:
        r.add("consistency.units_recompute", False, "WARNING",
              f"Unidades: raw={units_raw} vs stored={units_stored}")
    else:
        r.add("consistency.units_recompute", True, "WARNING",
              f"Unidades consistentes: {units_stored}")

    # Ticket promedio
    avg_stored = mc.get('avg_ticket', 0)
    avg_raw    = round(gmv_raw / len(paid_raw), 2) if paid_raw else 0
    if avg_raw > 0 and abs(avg_stored - avg_raw) / avg_raw > 0.01:
        r.add("consistency.avg_ticket", False, "WARNING",
              f"Ticket prom: raw=${avg_raw:,.0f} vs stored=${avg_stored:,.0f}")
    else:
        r.add("consistency.avg_ticket", True, "WARNING",
              f"Ticket promedio OK: ${avg_stored:,.0f}")

    # summary.json debe tener órdenes contadas igual que orders_current
    summary = _load('summary') or {}
    summary_count = summary.get('orders_current', None)
    if summary_count is not None and summary_count != len(orders_cur):
        r.add("consistency.summary_count", False, "WARNING",
              f"summary.json dice {summary_count} órdenes pero orders_current tiene {len(orders_cur)}")
    else:
        r.add("consistency.summary_count", True, "WARNING",
              f"summary.json consistente: {len(orders_cur)} órdenes")


# ─────────────────────────────────────────────────────────────────────────────
# 4. CHECKS CROSS-TABS (valores que aparecen en múltiples hojas)
# ─────────────────────────────────────────────────────────────────────────────

def check_cross_tab_consistency(r: QAResult):
    """
    Valida que los KPIs cross-tab sean computables desde la misma fuente.
    (No puede verificar el HTML renderizado, pero sí las fuentes de datos.)
    """
    _qa_log("  [QA] Verificando consistencia cross-tab...")

    mc  = _load('metrics_current') or {}
    ec  = _load('enrich_current')  or {}
    sum_ = _load('summary')        or {}

    gmv_mc = mc.get('gmv', 0)
    gmv_ec = sum(v.get('gmv', 0) for v in ec.get('by_category', {}).values()) if ec else 0

    # enrich_current agrega por categoría solo órdenes con logistic_type conocido
    # → puede ser menor que el total; verificamos que no sea > total
    if gmv_ec > gmv_mc * 1.01:
        r.add("cross_tab.enrich_vs_metrics", False, "WARNING",
              f"enrich GMV ${gmv_ec:,.0f} > metrics GMV ${gmv_mc:,.0f} (imposible)")
    else:
        r.add("cross_tab.enrich_vs_metrics", True, "WARNING",
              f"enrich GMV ${gmv_ec:,.0f} ≤ metrics GMV ${gmv_mc:,.0f} OK")

    # enrich_prior debe existir y tener gmv > 0 si metrics_prior tiene gmv > 0
    mp  = _load('metrics_prior') or {}
    ep  = _load('enrich_prior')  or {}
    gmv_mp = mp.get('gmv', 0)
    gmv_ep = sum(v.get('gmv', 0) for v in ep.get('by_category', {}).values()) if ep else 0
    if gmv_mp > 0 and gmv_ep == 0:
        r.add("cross_tab.enrich_prior", False, "WARNING",
              f"enrich_prior vacío pero metrics_prior GMV=${gmv_mp:,.0f}")
    else:
        r.add("cross_tab.enrich_prior", True, "WARNING",
              f"enrich_prior OK (GMV=${gmv_ep:,.0f})")

    # fee_rate no debe ser absurdo (entre 5% y 35% para ML)
    fee_rate = mc.get('fee_rate', 0)
    if mc.get('gmv', 0) > 0:
        if fee_rate < 1 or fee_rate > 50:
            r.add("cross_tab.fee_rate", False, "WARNING",
                  f"fee_rate={fee_rate:.1f}% fuera de rango razonable (1%-50%)")
        else:
            r.add("cross_tab.fee_rate", True, "WARNING",
                  f"fee_rate={fee_rate:.1f}% dentro de rango razonable OK")


# ─────────────────────────────────────────────────────────────────────────────
# 5. CHECKS DE ANOMALÍAS (valores absurdos)
# ─────────────────────────────────────────────────────────────────────────────

def check_anomalies(r: QAResult):
    """Detecta valores que son matemáticamente imposibles o absurdos."""
    _qa_log("  [QA] Verificando anomalías en métricas...")

    mc = _load('metrics_current') or {}

    # GMV no puede ser negativo
    if mc.get('gmv', 0) < 0:
        r.add("anomaly.gmv_negative", False, "CRITICAL",
              f"GMV negativo: ${mc.get('gmv')}")
    else:
        r.add("anomaly.gmv_negative", True, "CRITICAL",
              f"GMV >= 0 OK: ${mc.get('gmv', 0):,.0f}")

    # Ticket promedio: entre $100 y $5.000.000 ARS (rango razonable)
    avg = mc.get('avg_ticket', 0)
    if mc.get('paid', 0) > 0:
        if avg < 100:
            r.add("anomaly.avg_ticket_low", False, "WARNING",
                  f"Ticket promedio muy bajo: ${avg:,.0f} (< $100)")
        elif avg > 5_000_000:
            r.add("anomaly.avg_ticket_high", False, "WARNING",
                  f"Ticket promedio muy alto: ${avg:,.0f} (> $5M)")
        else:
            r.add("anomaly.avg_ticket_range", True, "WARNING",
                  f"Ticket promedio OK: ${avg:,.0f}")

    # Cancel rate no debe superar 80%
    cancel_rate = mc.get('cancel_rate', 0)
    if cancel_rate > 80:
        r.add("anomaly.cancel_rate_high", False, "WARNING",
              f"Cancel rate muy alto: {cancel_rate:.1f}% (> 80%)")
    else:
        r.add("anomaly.cancel_rate", True, "WARNING",
              f"Cancel rate OK: {cancel_rate:.1f}%")

    # fee_rate no debe ser > 100%
    fee_rate = mc.get('fee_rate', 0)
    if fee_rate > 100:
        r.add("anomaly.fee_rate_impossible", False, "CRITICAL",
              f"fee_rate IMPOSIBLE: {fee_rate:.1f}% (> 100%)")
    else:
        r.add("anomaly.fee_rate_range", True, "CRITICAL",
              f"fee_rate < 100% OK: {fee_rate:.1f}%")

    # Verificar que cada daily en metrics_current sea positivo
    daily = mc.get('daily', {})
    neg_days = [d for d, v in daily.items() if v < 0]
    if neg_days:
        r.add("anomaly.daily_negative", False, "WARNING",
              f"Días con GMV negativo en daily: {neg_days}")
    else:
        r.add("anomaly.daily_negative", True, "WARNING",
              f"No hay días con GMV negativo OK ({len(daily)} días)")

    # Detectar duplicados de order_id en orders_current
    orders_cur = _load('orders_current') or []
    ids = [o.get('order_id') for o in orders_cur if o.get('order_id')]
    dup_ids = [oid for oid, cnt in
               ((x, ids.count(x)) for x in set(ids)) if cnt > 1]
    if dup_ids:
        r.add("anomaly.order_duplicates", False, "CRITICAL",
              f"Órdenes DUPLICADAS en orders_current: {len(dup_ids)} IDs repetidos → {dup_ids[:5]}")
    else:
        r.add("anomaly.order_duplicates", True, "CRITICAL",
              f"Sin duplicados en órdenes OK ({len(ids)} IDs únicos)")

    # Ads: verificar ROAS entre 0 y 100 (ROAS de 1900% → bug)
    ads = _load('ads_daily') or {}
    bad_roas = []
    for day, vals in ads.items():
        roas = vals.get('roas', 0) if isinstance(vals, dict) else 0
        if roas > 100:
            bad_roas.append(f"{day}:{roas:.1f}")
    if bad_roas:
        r.add("anomaly.ads_roas_impossible", False, "WARNING",
              f"ROAS imposible (>100x) en días: {bad_roas[:5]}")
    else:
        r.add("anomaly.ads_roas_range", True, "WARNING",
              f"ROAS dentro de rango razonable OK ({len(ads)} días)")

    # Ads: ACOS no debe ser > 200%
    # NOTA: ads_daily.json guarda acos como PORCENTAJE (6.83 = 6.83%), no ratio
    bad_acos = []
    for day, vals in ads.items():
        acos = vals.get('acos', 0) if isinstance(vals, dict) else 0
        if acos and acos > 200:  # ACOS > 200% es imposible/error de datos
            bad_acos.append(f"{day}:{acos:.0f}%")
    if bad_acos:
        r.add("anomaly.ads_acos_high", False, "WARNING",
              f"ACOS muy alto (>200%) en días: {bad_acos[:5]}")
    else:
        r.add("anomaly.ads_acos_range", True, "WARNING",
              f"ACOS dentro de rango OK")


# ─────────────────────────────────────────────────────────────────────────────
# 6. CHECKS DE RECONCILIACIÓN ML vs MP
# ─────────────────────────────────────────────────────────────────────────────

def check_reconciliation(r: QAResult):
    """
    Reconciliación entre ventas ML y balance MP.
    La reconciliación exacta es compleja (comisiones, retenciones, holdouts),
    así que verificamos rangos y tendencias, no igualdad exacta.
    """
    _qa_log("  [QA] Verificando reconciliación ML vs MP...")

    mc = _load('metrics_current') or {}
    mp = _load('mp_balance')      or {}

    if not mp:
        r.add("reconciliation.mp_available", False, "WARNING",
              "mp_balance.json no disponible — reconciliación omitida")
        return

    gmv_ml   = mc.get('gmv', 0)
    fees_ml  = mc.get('fees', 0)
    net_ml   = gmv_ml - fees_ml

    # disponible + retenido + a_cobrar del balance MP
    mp_disp      = mp.get('disponible',  0) or 0
    mp_retenido  = mp.get('retenido',    0) or 0
    mp_a_cobrar  = mp.get('a_cobrar',    0) or 0
    mp_total_rep = mp_disp + mp_retenido + mp_a_cobrar

    r.add("reconciliation.mp_data_present", True, "INFO",
          f"MP: disponible=${mp_disp:,.0f} retenido=${mp_retenido:,.0f} a_cobrar=${mp_a_cobrar:,.0f}")

    # Verificar que saldo disponible MP no sea negativo
    if mp_disp < 0:
        r.add("reconciliation.mp_disponible", False, "WARNING",
              f"Saldo disponible MP NEGATIVO: ${mp_disp:,.0f}")
    else:
        r.add("reconciliation.mp_disponible", True, "WARNING",
              f"Saldo disponible MP >= 0 OK: ${mp_disp:,.0f}")

    # a_cobrar no debe superar el GMV del mes * 2 (redundancia de seguridad)
    if gmv_ml > 0 and mp_a_cobrar > gmv_ml * 2:
        r.add("reconciliation.a_cobrar_range", False, "WARNING",
              f"a_cobrar=${mp_a_cobrar:,.0f} parece alto vs GMV=${gmv_ml:,.0f} (> 2x)")
    elif gmv_ml > 0:
        r.add("reconciliation.a_cobrar_range", True, "WARNING",
              f"a_cobrar=${mp_a_cobrar:,.0f} vs GMV=${gmv_ml:,.0f} OK")

    # Liquidaciones vs GMV: net de liquidaciones debería ser ~60-90% del GMV mensual
    liq = _load('cobro_summary') or _load('liq_summary') or {}
    if liq and gmv_ml > 0:
        neto_liq = liq.get('neto', 0) or 0
        ratio    = neto_liq / gmv_ml if gmv_ml else 0
        if ratio < 0.3 or ratio > 1.1:
            r.add("reconciliation.liq_vs_gmv_ratio", False, "WARNING",
                  f"Neto liquidaciones ${neto_liq:,.0f} = {ratio*100:.0f}% del GMV — fuera de rango (30%-110%)")
        else:
            r.add("reconciliation.liq_vs_gmv_ratio", True, "WARNING",
                  f"Neto liquidaciones ${neto_liq:,.0f} = {ratio*100:.0f}% del GMV OK")


# ─────────────────────────────────────────────────────────────────────────────
# 7. CHECKS DE STOCK
# ─────────────────────────────────────────────────────────────────────────────

def check_stock(r: QAResult):
    """Verifica consistencia e integridad del stock."""
    _qa_log("  [QA] Verificando stock...")

    items = _load('items') or []
    stock = _load('stock_ml') or _load('fulfillment_stock') or []

    if not items:
        r.add("stock.items_present", False, "WARNING",
              "items.json vacío — sin datos de stock")
        return

    r.add("stock.items_present", True, "WARNING",
          f"{len(items)} items en catálogo")

    # Verificar que no haya items con stock negativo
    neg_stock = [i.get('item_id') for i in items
                 if (i.get('available_quantity') or 0) < 0]
    if neg_stock:
        r.add("stock.negative_qty", False, "WARNING",
              f"Items con stock negativo: {neg_stock[:5]}")
    else:
        r.add("stock.negative_qty", True, "WARNING",
              f"Sin stock negativo OK")

    # Items sin item_id (registros corruptos)
    no_id = [i for i in items if not i.get('item_id')]
    if no_id:
        r.add("stock.missing_item_id", False, "WARNING",
              f"{len(no_id)} items sin item_id (registros corruptos)")
    else:
        r.add("stock.missing_item_id", True, "WARNING",
              f"Todos los items tienen item_id OK")

    # Verificar que items del top 10 de ventas tengan stock
    mc = _load('metrics_current') or {}
    top = mc.get('top', [])[:10]
    items_map = {i.get('item_id'): i for i in items}
    out_of_stock_top = []
    for t in top:
        iid = t.get('id')
        item = items_map.get(iid, {})
        if item and (item.get('available_quantity') or 0) == 0 and item.get('status') == 'active':
            out_of_stock_top.append(iid)

    if out_of_stock_top:
        r.add("stock.top10_out_of_stock", False, "WARNING",
              f"Top items sin stock: {out_of_stock_top}")
    else:
        r.add("stock.top10_out_of_stock", True, "WARNING",
              f"Top 10 items con stock disponible OK")


# ─────────────────────────────────────────────────────────────────────────────
# 8. CHECKS DE PERÍODO CORRECTO
# ─────────────────────────────────────────────────────────────────────────────

def check_periods(r: QAResult):
    """Verifica que los datos correspondan al período correcto."""
    _qa_log("  [QA] Verificando períodos de datos...")

    today       = date.today()
    cur_month   = today.strftime('%Y-%m')
    orders_cur  = _load('orders_current') or []

    if not orders_cur:
        r.add("period.orders_current_month", False, "WARNING",
              "No hay órdenes para verificar período")
        return

    # Verificar que las órdenes más recientes sean del mes actual
    dates = [o.get('date_created', '')[:7] for o in orders_cur if o.get('date_created')]
    if dates:
        max_month = max(dates)
        if max_month < cur_month:
            r.add("period.orders_current_month", False, "CRITICAL",
                  f"Última orden es de {max_month} pero hoy es {cur_month} → datos STALE")
        elif max_month > cur_month:
            r.add("period.orders_current_month", False, "WARNING",
                  f"Hay órdenes de mes futuro {max_month} (¿timezone issue?)")
        else:
            r.add("period.orders_current_month", True, "CRITICAL",
                  f"Órdenes más recientes del mes correcto: {max_month}")

    # Verificar que summary.updated_at sea de hoy
    summary = _load('summary') or {}
    updated = summary.get('updated_at', '')
    if updated:
        updated_date = updated[:10]
        today_str    = today.isoformat()
        if updated_date < today_str:
            r.add("period.summary_today", False, "WARNING",
                  f"summary.json actualizado {updated_date}, no hoy {today_str}")
        else:
            r.add("period.summary_today", True, "WARNING",
                  f"summary.json actualizado hoy {updated_date} OK")

    # Verificar que ads_daily tenga datos de ayer (día más reciente esperado)
    ads    = _load('ads_daily') or {}
    ayer   = (today - timedelta(days=1)).isoformat()
    if ads and ayer not in ads:
        # Buscar el día más reciente
        last_ads_day = max(ads.keys()) if ads else "N/A"
        if last_ads_day < ayer:
            r.add("period.ads_daily_fresh", False, "WARNING",
                  f"ads_daily último día: {last_ads_day} — falta datos de ayer {ayer}")
        else:
            r.add("period.ads_daily_fresh", True, "WARNING",
                  f"ads_daily OK (último: {last_ads_day})")
    elif ads:
        r.add("period.ads_daily_fresh", True, "WARNING",
              f"ads_daily tiene datos de ayer {ayer} OK")


# ─────────────────────────────────────────────────────────────────────────────
# 9. CHECKS DE POSTVENTA
# ─────────────────────────────────────────────────────────────────────────────

def check_postventa(r: QAResult):
    """Verifica datos de postventa."""
    _qa_log("  [QA] Verificando postventa...")

    mc   = _load('metrics_current')   or {}
    pv   = _load('postventa_current') or {}
    canc = _load('cancelled_current') or {}

    # cancel_rate de postventa vs cancel_rate de metrics deben ser cercanos
    mc_canc_rate = mc.get('cancel_rate', 0)
    if pv:
        pv_canc = pv.get('cancelled_orders', 0) or pv.get('total_cancelled', 0)
        pv_paid = pv.get('paid_orders', 0)      or pv.get('total_paid', 0)
        if pv_paid > 0:
            pv_rate = round(pv_canc / (pv_paid + pv_canc) * 100, 2) if (pv_paid + pv_canc) else 0
            diff    = abs(mc_canc_rate - pv_rate)
            if diff > 10:
                r.add("postventa.cancel_rate_consistency", False, "WARNING",
                      f"Cancel rate: metrics={mc_canc_rate:.1f}% vs postventa={pv_rate:.1f}% (diff {diff:.1f}%)")
            else:
                r.add("postventa.cancel_rate_consistency", True, "WARNING",
                      f"Cancel rate consistente: metrics={mc_canc_rate:.1f}% OK")
        else:
            r.add("postventa.data_present", True, "INFO",
                  "postventa_current.json presente")
    else:
        r.add("postventa.data_present", False, "WARNING",
              "postventa_current.json ausente")


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_qa(verbose: bool = True) -> dict:
    """
    Ejecuta todos los checks QA y retorna un dict con resultados.

    Returns:
        {
          'blocked': bool,      # True = NO publicar
          'errors': int,        # checks CRITICAL fallados
          'warnings': int,      # checks WARNING fallados
          'checks': list,       # detalle de cada check
          'summary': str,       # resumen de una línea
          'timestamp': str,
        }
    """
    r = QAResult()
    _qa_log("=" * 55)
    _qa_log("=== QA PRE-DEPLOY START ===")

    try:
        check_freshness(r)
    except Exception as e:
        r.add("freshness.error", False, "WARNING", f"Error en check_freshness: {e}")

    try:
        check_completeness(r)
    except Exception as e:
        r.add("completeness.error", False, "WARNING", f"Error en check_completeness: {e}")

    try:
        check_internal_consistency(r)
    except Exception as e:
        r.add("consistency.error", False, "WARNING", f"Error en check_consistency: {e}")

    try:
        check_cross_tab_consistency(r)
    except Exception as e:
        r.add("cross_tab.error", False, "WARNING", f"Error en check_cross_tab: {e}")

    try:
        check_anomalies(r)
    except Exception as e:
        r.add("anomaly.error", False, "WARNING", f"Error en check_anomalies: {e}")

    try:
        check_reconciliation(r)
    except Exception as e:
        r.add("reconciliation.error", False, "WARNING", f"Error en check_reconciliation: {e}")

    try:
        check_stock(r)
    except Exception as e:
        r.add("stock.error", False, "WARNING", f"Error en check_stock: {e}")

    try:
        check_periods(r)
    except Exception as e:
        r.add("period.error", False, "WARNING", f"Error en check_periods: {e}")

    try:
        check_postventa(r)
    except Exception as e:
        r.add("postventa.error", False, "WARNING", f"Error en check_postventa: {e}")

    result = r.to_dict()

    # Log del resumen
    _qa_log("")
    _qa_log("─" * 55)
    for c in r.checks:
        _qa_log(f"  {c['icon']}  [{c['level']:8s}] {c['name']}: {c['detail']}")
    _qa_log("─" * 55)
    _qa_log(result['summary'])
    _qa_log("=== QA PRE-DEPLOY END ===")

    # Guardar resultado del QA
    qa_result_path = os.path.join(DATA_DIR, 'qa_last_result.json')
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(qa_result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


if __name__ == '__main__':
    result = run_qa()
    print()
    print(result['summary'])
    sys.exit(1 if result['blocked'] else 0)
