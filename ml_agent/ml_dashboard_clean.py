#!/usr/bin/env python3
import json
import os
import math
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUT_DIR  = os.path.join(BASE_DIR, 'dashboards')


def load_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def fmt_money(v):
    v = float(v or 0)
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"


def fmt_pct(v):
    return f"{float(v or 0):.1f}%"


def delta_pct(cur, pri):
    cur = float(cur or 0)
    pri = float(pri or 0)
    if not pri:
        return None
    return ((cur - pri) / pri) * 100


def delta_arrow(pct, inverted=False):
    if pct is None:
        return ("—", "neutral")
    if pct > 0:
        color = "bad" if inverted else "good"
        return (f"▲ {pct:.1f}%", color)
    elif pct < 0:
        color = "good" if inverted else "bad"
        return (f"▼ {abs(pct):.1f}%", color)
    else:
        return ("= 0.0%", "neutral")


def build_dashboard():
    # ── 1. Load all JSONs ─────────────────────────────────────────────────────
    mc = load_json('metrics_current.json') or {}
    mp = load_json('metrics_prior.json') or {}
    ec = load_json('enrich_current.json') or {}
    ep = load_json('enrich_prior.json') or {}
    items_data = load_json('items.json') or []
    summary = load_json('summary.json') or {}
    cat_names = load_json('cat_names.json') or {}
    monthly = load_json('monthly_2026.json') or []
    orders_cur = load_json('orders_current.json') or []

    # ── 2. Period labels ──────────────────────────────────────────────────────
    period_cur = summary.get('period_cur_label', 'Mes actual')
    period_pri = summary.get('period_pri_label', 'Mes anterior')
    updated_at = summary.get('updated_at', '')[:16].replace('T', ' ')

    # ── 3. KPI computations ───────────────────────────────────────────────────
    def kpi(key, inverted=False):
        c = mc.get(key, 0) or 0
        p = mp.get(key, 0) or 0
        d = delta_pct(c, p)
        arr, cls = delta_arrow(d, inverted=inverted)
        return c, p, d, arr, cls

    gmv_c, gmv_p, _, gmv_arr, gmv_cls             = kpi('gmv')
    units_c, units_p, _, units_arr, units_cls      = kpi('units')
    fees_c, fees_p, _, fees_arr, fees_cls          = kpi('fees', inverted=True)
    net_c, net_p, _, net_arr, net_cls              = kpi('net')
    paid_c, paid_p, _, paid_arr, paid_cls          = kpi('paid')
    cancel_c, cancel_p, _, cancel_arr, cancel_cls  = kpi('cancelled', inverted=True)
    ticket_c, ticket_p, _, ticket_arr, ticket_cls  = kpi('avg_ticket')
    fee_rate_c, fee_rate_p, _, fee_rate_arr, fee_rate_cls = kpi('fee_rate', inverted=True)
    crate_c, crate_p, _, crate_arr, crate_cls      = kpi('cancel_rate', inverted=True)

    # ── 4. Listing type and logistic ──────────────────────────────────────────
    # Keys may be raw API ('gold_special','gold_pro','fulfillment','cross_docking')
    # OR translated ('Clásica','Premium','Full','Flex','Colecta') depending on pipeline version
    blt = ec.get('by_listing_type', {})
    blg = ec.get('by_logistic', {})
    def _blt(key, fallback):
        return (blt.get(key) or blt.get(fallback) or {})
    def _blg(key, fallback):
        return (blg.get(key) or blg.get(fallback) or {})
    classic_gmv   = _blt('Clásica',  'gold_special').get('gmv', 0) or 0
    classic_units = _blt('Clásica',  'gold_special').get('units', 0) or 0
    premium_gmv   = _blt('Premium',  'gold_pro').get('gmv', 0) or 0
    premium_units = _blt('Premium',  'gold_pro').get('units', 0) or 0
    flex_gmv      = _blg('Flex',     'cross_docking').get('gmv', 0) or 0
    flex_units    = _blg('Flex',     'cross_docking').get('units', 0) or 0
    full_gmv      = _blg('Full',     'fulfillment').get('gmv', 0) or 0
    full_units    = _blg('Full',     'fulfillment').get('units', 0) or 0
    colecta_gmv   = _blg('Colecta',  'self_service').get('gmv', 0) or 0
    colecta_units = _blg('Colecta',  'self_service').get('units', 0) or 0

    # prior listing type
    blt_p = ep.get('by_listing_type', {})
    blg_p = ep.get('by_logistic', {})

    # installment dist
    inst_dist = mc.get('installment_dist', {}) or {}

    # ── 5. Daily chart data ───────────────────────────────────────────────────
    daily_c = mc.get('daily', {})
    daily_p = mp.get('daily', {})
    all_days = sorted(set(list(daily_c.keys()) + list(daily_p.keys())), key=lambda x: int(x))
    daily_labels  = [f"Día {d}" for d in all_days]
    daily_cur_vals = [daily_c.get(d, 0) for d in all_days]
    daily_pri_vals = [daily_p.get(d, 0) for d in all_days]

    # ── 6. DOW data ───────────────────────────────────────────────────────────
    dow_raw = mc.get('dow', [0]*7)
    dow_count_raw = mc.get('dow_count', [1]*7)
    if not dow_count_raw:
        dow_count_raw = [1]*7

    # ── 7. Heatmap & hourly ───────────────────────────────────────────────────
    heatmap = ec.get('heatmap', [[0]*24 for _ in range(7)])
    by_hour = ec.get('by_hour', {})
    hour_vals = [by_hour.get(str(h), 0) or 0 for h in range(24)]

    # ── 8. Top products ───────────────────────────────────────────────────────
    top_items = mc.get('top', []) or []
    top15 = top_items[:15]
    cancels_list = mc.get('cancels', []) or []

    # Build lookup maps from items.json
    item_perms   = {}
    item_lt_map  = {}
    item_log_map = {}
    item_health  = {}
    item_stock   = {}
    item_titles  = {}
    for it in items_data:
        iid = it.get('item_id', '')
        item_perms[iid]   = it.get('permalink', '') or ''
        item_lt_map[iid]  = it.get('listing_type_id', '') or ''
        item_log_map[iid] = it.get('logistic_type', '') or ''
        item_health[iid]  = it.get('health', 0) or 0
        item_stock[iid]   = it.get('available_quantity', 0) or 0
        item_titles[iid]  = it.get('title', '') or ''

    # ── 9. Units this month per item ──────────────────────────────────────────
    item_units_month = {}
    for o in orders_cur:
        if o.get('status') == 'paid':
            for it in o.get('items', []):
                iid = it.get('item_id', '')
                item_units_month[iid] = item_units_month.get(iid, 0) + (it.get('quantity') or 0)

    # ── 10. Categories ────────────────────────────────────────────────────────
    by_cat = ec.get('by_category', {})
    total_gmv = gmv_c or 1
    cat_rows = []
    for cat_id, cdata in by_cat.items():
        cname = cdata.get('name') or cat_names.get(cat_id, cat_id)
        cgmv  = cdata.get('gmv', 0) or 0
        cunits = cdata.get('units', 0) or 0
        cpct  = cgmv / total_gmv * 100
        cat_rows.append((cname, cgmv, cunits, cpct))
    cat_rows.sort(key=lambda x: -x[1])

    # ── 11. Monthly data ──────────────────────────────────────────────────────
    if monthly:
        j_monthly_labels      = json.dumps([m.get('label','') for m in monthly])
        j_monthly_gmv         = json.dumps([m.get('gmv', 0) or 0 for m in monthly])
        j_monthly_units       = json.dumps([m.get('units', 0) or 0 for m in monthly])
        j_monthly_cancel_rate = json.dumps([m.get('cancel_rate', 0) or 0 for m in monthly])
        j_monthly_fees        = json.dumps([m.get('fees', 0) or 0 for m in monthly])
    else:
        j_monthly_labels      = '[]'
        j_monthly_gmv         = '[]'
        j_monthly_units       = '[]'
        j_monthly_cancel_rate = '[]'
        j_monthly_fees        = '[]'

    j_daily_labels     = json.dumps(daily_labels)
    j_daily_cur        = json.dumps(daily_cur_vals)
    j_daily_pri        = json.dumps(daily_pri_vals)
    j_dow              = json.dumps(dow_raw)
    j_dow_count        = json.dumps(dow_count_raw)
    j_hour_vals        = json.dumps(hour_vals)
    j_heatmap          = json.dumps(heatmap)
    j_classic_gmv      = json.dumps(classic_gmv)
    j_premium_gmv      = json.dumps(premium_gmv)
    j_classic_units    = json.dumps(classic_units)
    j_premium_units    = json.dumps(premium_units)
    j_flex_gmv         = json.dumps(flex_gmv)
    j_full_gmv         = json.dumps(full_gmv)
    j_colecta_gmv      = json.dumps(colecta_gmv)
    j_flex_units       = json.dumps(flex_units)
    j_full_units       = json.dumps(full_units)
    j_colecta_units    = json.dumps(colecta_units)
    j_fees_c           = json.dumps(fees_c)
    j_net_c            = json.dumps(net_c)
    j_gmv_c            = json.dumps(gmv_c)

    # ── 12. Stock items (Full and Flex) ───────────────────────────────────────
    full_items = [it for it in items_data if it.get('logistic_type') == 'fulfillment']
    flex_items = [it for it in items_data if it.get('logistic_type') == 'cross_docking']
    full_items_sorted = sorted(full_items, key=lambda x: item_units_month.get(x['item_id'], 0), reverse=True)
    flex_items_sorted = sorted(flex_items, key=lambda x: item_units_month.get(x['item_id'], 0), reverse=True)

    def lt_label(lt):
        if lt == 'gold_pro': return 'Premium'
        if lt == 'gold_special': return 'Clásica'
        return lt or '—'

    # ── 13. Write HTML ────────────────────────────────────────────────────────
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, 'ml_360.html')

    with open(out, 'w', encoding='utf-8') as f:

        # HEAD
        f.write('<!DOCTYPE html>\n<html lang="es">\n<head>\n')
        f.write('<meta charset="UTF-8">\n')
        f.write('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
        f.write(f'<title>ML 360° - {period_cur}</title>\n')
        f.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>\n')

        # CSS
        f.write('<style>\n')
        f.write(':root{--bg:#0d0d1a;--card:#151528;--border:#1e1e3a;--text:#e0e0e0;--muted:#7a7a9a;')
        f.write('--blue:#3483FA;--yellow:#FFE600;--green:#00A650;--red:#F23D4F;--purple:#9b59b6;}\n')
        f.write('*{box-sizing:border-box;margin:0;padding:0;}\n')
        f.write('body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;min-height:100vh;}\n')
        f.write('a{color:var(--blue);text-decoration:none;}\n')
        f.write('a:hover{text-decoration:underline;}\n')
        f.write('header{background:linear-gradient(135deg,#0d0d2e,#151540);padding:16px 24px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);}\n')
        f.write('.header-title{font-size:1.3rem;font-weight:700;color:var(--blue);letter-spacing:.5px;}\n')
        f.write('.header-sub{font-size:.8rem;color:var(--muted);margin-top:2px;}\n')
        f.write('.header-right{text-align:right;font-size:.8rem;color:var(--muted);}\n')
        f.write('nav{background:var(--card);border-bottom:1px solid var(--border);padding:8px 24px;display:flex;gap:6px;flex-wrap:wrap;}\n')
        f.write('.tab-btn{background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:20px;padding:6px 16px;cursor:pointer;font-size:.85rem;transition:all .2s;}\n')
        f.write('.tab-btn:hover{border-color:var(--blue);color:var(--blue);}\n')
        f.write('.tab-btn.active{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:600;}\n')
        f.write('.tab-content{display:none;padding:24px;}\n')
        f.write('.tab-content.active{display:block;}\n')
        f.write('.section-title{font-size:1rem;font-weight:700;color:var(--blue);margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--border);}\n')
        f.write('.kpi-row{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:24px;}\n')
        f.write('.kpi-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 20px;flex:1;min-width:160px;}\n')
        f.write('.kpi-label{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;}\n')
        f.write('.kpi-val{font-size:1.6rem;font-weight:700;color:var(--text);}\n')
        f.write('.kpi-prev{font-size:.78rem;color:var(--muted);margin-top:4px;}\n')
        f.write('.kpi-delta{font-size:.82rem;font-weight:600;margin-top:2px;}\n')
        f.write('.good{color:var(--green);} .bad{color:var(--red);} .neutral{color:var(--muted);}\n')
        f.write('.chart-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:20px;}\n')
        f.write('.chart-title{font-size:.9rem;font-weight:600;color:var(--text);margin-bottom:14px;}\n')
        f.write('.chart-grid{display:grid;gap:16px;}\n')
        f.write('.chart-grid.cols2{grid-template-columns:1fr 1fr;}\n')
        f.write('.chart-grid.cols3{grid-template-columns:1fr 1fr 1fr;}\n')
        f.write('table{width:100%;border-collapse:collapse;font-size:.83rem;}\n')
        f.write('thead th{background:#0d0d2e;color:var(--muted);text-transform:uppercase;font-size:.72rem;padding:10px 12px;text-align:left;cursor:pointer;user-select:none;border-bottom:1px solid var(--border);}\n')
        f.write('thead th:hover{color:var(--blue);}\n')
        f.write('tbody tr:hover{background:rgba(52,131,250,.06);}\n')
        f.write('tbody td{padding:9px 12px;border-bottom:1px solid var(--border);}\n')
        f.write('.table-card{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:20px;}\n')
        f.write('.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.72rem;font-weight:600;}\n')
        f.write('.pill-blue{background:rgba(52,131,250,.15);color:var(--blue);}\n')
        f.write('.pill-yellow{background:rgba(255,230,0,.15);color:var(--yellow);}\n')
        f.write('.pill-green{background:rgba(0,166,80,.15);color:var(--green);}\n')
        f.write('.pill-purple{background:rgba(155,89,182,.15);color:var(--purple);}\n')
        f.write('.health-bar{display:inline-block;height:8px;border-radius:4px;vertical-align:middle;}\n')
        f.write('.info-box{background:rgba(52,131,250,.08);border:1px solid rgba(52,131,250,.25);border-radius:10px;padding:14px 18px;font-size:.85rem;color:var(--muted);margin-bottom:16px;}\n')
        f.write('.info-box strong{color:var(--blue);}\n')
        f.write('.warn-box{background:rgba(242,61,79,.08);border:1px solid rgba(242,61,79,.25);border-radius:10px;padding:14px 18px;font-size:.85rem;color:var(--muted);margin-bottom:16px;}\n')
        f.write('.warn-box strong{color:var(--red);}\n')
        f.write('.heatmap-table{border-collapse:collapse;font-size:.7rem;width:100%;}\n')
        f.write('.heatmap-table td{width:3.5%;padding:3px;text-align:center;border:1px solid #0d0d1a;border-radius:3px;cursor:default;}\n')
        f.write('.heatmap-table th{padding:4px 2px;font-size:.65rem;color:var(--muted);text-align:center;}\n')
        f.write('.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;}\n')
        f.write('@media(max-width:800px){.chart-grid.cols2,.chart-grid.cols3,.two-col{grid-template-columns:1fr;}}\n')
        f.write('</style>\n</head>\n<body>\n')

        # HEADER
        f.write('<header>\n')
        f.write('<div><div class="header-title">ML 360°</div>')
        f.write(f'<div class="header-sub">{period_cur} vs {period_pri}</div></div>\n')
        f.write(f'<div class="header-right">Actualizado: {updated_at}</div>\n')
        f.write('</header>\n')

        # NAV
        f.write('<nav>\n')
        f.write('<button class="tab-btn active" onclick="T(\'resumen\',this)">Resumen</button>\n')
        f.write('<button class="tab-btn" onclick="T(\'ventas\',this)">Ventas</button>\n')
        f.write('<button class="tab-btn" onclick="T(\'horarios\',this)">Horarios</button>\n')
        f.write('<button class="tab-btn" onclick="T(\'stock\',this)">Stock</button>\n')
        f.write('<button class="tab-btn" onclick="T(\'comisiones\',this)">Comisiones</button>\n')
        f.write('<button class="tab-btn" onclick="T(\'cancelaciones\',this)">Cancelaciones</button>\n')
        f.write('<button class="tab-btn" onclick="T(\'impuestos\',this)">Impuestos</button>\n')
        f.write('</nav>\n')

        # ── TAB: RESUMEN ─────────────────────────────────────────────────────
        f.write('<div id="tab-resumen" class="tab-content active">\n')
        f.write(f'<div class="section-title">KPIs Principales — {period_cur}</div>\n')
        f.write('<div class="kpi-row">\n')

        # GMV
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">GMV</div>')
        f.write(f'<div class="kpi-val">{fmt_money(gmv_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_money(gmv_p)}</div>')
        f.write(f'<div class="kpi-delta {gmv_cls}">{gmv_arr}</div>')
        f.write('</div>\n')

        # Unidades
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Unidades</div>')
        f.write(f'<div class="kpi-val">{int(units_c):,}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {int(units_p):,}</div>')
        f.write(f'<div class="kpi-delta {units_cls}">{units_arr}</div>')
        f.write('</div>\n')

        # Órdenes Pagadas
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Órdenes Pagadas</div>')
        f.write(f'<div class="kpi-val">{int(paid_c):,}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {int(paid_p):,}</div>')
        f.write(f'<div class="kpi-delta {paid_cls}">{paid_arr}</div>')
        f.write('</div>\n')

        # Ticket Promedio
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Ticket Promedio</div>')
        f.write(f'<div class="kpi-val">{fmt_money(ticket_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_money(ticket_p)}</div>')
        f.write(f'<div class="kpi-delta {ticket_cls}">{ticket_arr}</div>')
        f.write('</div>\n')

        # Neto ML
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Neto ML</div>')
        f.write(f'<div class="kpi-val">{fmt_money(net_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_money(net_p)}</div>')
        f.write(f'<div class="kpi-delta {net_cls}">{net_arr}</div>')
        f.write('</div>\n')

        # Comisiones
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Comisiones ML</div>')
        f.write(f'<div class="kpi-val">{fmt_money(fees_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_money(fees_p)}</div>')
        f.write(f'<div class="kpi-delta {fees_cls}">{fees_arr}</div>')
        f.write('</div>\n')

        # % Comisión
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">% Comisión</div>')
        f.write(f'<div class="kpi-val">{fmt_pct(fee_rate_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_pct(fee_rate_p)}</div>')
        f.write(f'<div class="kpi-delta {fee_rate_cls}">{fee_rate_arr}</div>')
        f.write('</div>\n')

        # Cancelaciones
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Cancelaciones</div>')
        f.write(f'<div class="kpi-val">{int(cancel_c):,} ({fmt_pct(crate_c)})</div>')
        f.write(f'<div class="kpi-prev">Anterior: {int(cancel_p):,} ({fmt_pct(crate_p)})</div>')
        f.write(f'<div class="kpi-delta {crate_cls}">{crate_arr}</div>')
        f.write('</div>\n')

        f.write('</div>\n')  # kpi-row

        # Listing type section
        f.write('<div class="two-col">\n')

        # Left: Clásica vs Premium
        f.write('<div class="chart-card">\n')
        f.write('<div class="chart-title">Tipo de Publicación</div>\n')
        f.write('<div style="display:flex;gap:20px;margin-bottom:16px;">\n')
        f.write('<div style="flex:1;background:#0d0d2e;border-radius:10px;padding:14px;">')
        f.write('<div style="font-size:.75rem;color:var(--muted);margin-bottom:4px;">CLÁSICA</div>')
        f.write(f'<div style="font-size:1.3rem;font-weight:700;color:var(--blue);">{fmt_money(classic_gmv)}</div>')
        f.write(f'<div style="font-size:.8rem;color:var(--muted);">{int(classic_units):,} unidades</div>')
        f.write('</div>\n')
        f.write('<div style="flex:1;background:#0d0d2e;border-radius:10px;padding:14px;">')
        f.write('<div style="font-size:.75rem;color:var(--muted);margin-bottom:4px;">PREMIUM</div>')
        f.write(f'<div style="font-size:1.3rem;font-weight:700;color:var(--yellow);">{fmt_money(premium_gmv)}</div>')
        f.write(f'<div style="font-size:.8rem;color:var(--muted);">{int(premium_units):,} unidades</div>')
        f.write('</div>\n')
        f.write('</div>\n')
        f.write('<canvas id="c-listing-type" height="120"></canvas>\n')
        f.write('</div>\n')  # chart-card

        # Right: Logística
        f.write('<div class="chart-card">\n')
        f.write('<div class="chart-title">Logística</div>\n')
        f.write('<div style="display:flex;gap:20px;margin-bottom:16px;">\n')
        f.write('<div style="flex:1;background:#0d0d2e;border-radius:10px;padding:14px;">')
        f.write('<div style="font-size:.75rem;color:var(--muted);margin-bottom:4px;">FULL</div>')
        f.write(f'<div style="font-size:1.3rem;font-weight:700;color:var(--green);">{fmt_money(full_gmv)}</div>')
        f.write(f'<div style="font-size:.8rem;color:var(--muted);">{int(full_units):,} unidades</div>')
        f.write('</div>\n')
        f.write('<div style="flex:1;background:#0d0d2e;border-radius:10px;padding:14px;">')
        f.write('<div style="font-size:.75rem;color:var(--muted);margin-bottom:4px;">FLEX</div>')
        f.write(f'<div style="font-size:1.3rem;font-weight:700;color:var(--purple);">{fmt_money(flex_gmv)}</div>')
        f.write(f'<div style="font-size:.8rem;color:var(--muted);">{int(flex_units):,} unidades</div>')
        f.write('</div>\n')
        if colecta_gmv > 0:
            f.write('<div style="flex:1;background:#0d0d2e;border-radius:10px;padding:14px;">')
            f.write('<div style="font-size:.75rem;color:var(--muted);margin-bottom:4px;">COLECTA</div>')
            f.write(f'<div style="font-size:1.3rem;font-weight:700;color:var(--yellow);">{fmt_money(colecta_gmv)}</div>')
            f.write(f'<div style="font-size:.8rem;color:var(--muted);">{int(colecta_units):,} unidades</div>')
            f.write('</div>\n')
        f.write('</div>\n')
        f.write('<canvas id="c-logistic" height="120"></canvas>\n')
        f.write('</div>\n')  # chart-card

        f.write('</div>\n')  # two-col

        f.write('</div>\n')  # tab-resumen


        # ── TAB: VENTAS ──────────────────────────────────────────────────────
        f.write('<div id="tab-ventas" class="tab-content">\n')

        if monthly:
            f.write('<div class="chart-card">\n')
            f.write('<div class="chart-title">GMV Mensual 2026</div>\n')
            f.write('<canvas id="c-monthly-gmv" height="80"></canvas>\n')
            f.write('</div>\n')

        f.write('<div class="chart-card">\n')
        f.write(f'<div class="chart-title">GMV Diario: {period_cur} vs {period_pri}</div>\n')
        f.write('<canvas id="c-daily-gmv" height="80"></canvas>\n')
        f.write('</div>\n')

        # Top 15 products table
        f.write(f'<div class="section-title">Top {len(top15)} Productos por GMV</div>\n')
        f.write('<div class="table-card">\n')
        f.write('<table id="tbl-top15">\n')
        f.write('<thead><tr>')
        f.write('<th onclick="srt(\'tbl-top15\',0)">#</th>')
        f.write('<th onclick="srt(\'tbl-top15\',1)">Producto</th>')
        f.write('<th onclick="srt(\'tbl-top15\',2)">GMV</th>')
        f.write('<th onclick="srt(\'tbl-top15\',3)">Unidades</th>')
        f.write('<th onclick="srt(\'tbl-top15\',4)">Comisión</th>')
        f.write('<th onclick="srt(\'tbl-top15\',5)">% Com.</th>')
        f.write('</tr></thead><tbody>\n')
        for i, item in enumerate(top15, 1):
            iid    = item.get('id', '')
            title  = item.get('title', '') or iid
            igmv   = item.get('gmv', 0) or 0
            iunits = item.get('units', 0) or 0
            ifees  = item.get('fees', 0) or 0
            ipct   = (ifees / igmv * 100) if igmv else 0
            perm   = item_perms.get(iid, '')
            if perm:
                title_html = f'<a href="{perm}" target="_blank">{title}</a>'
            else:
                title_html = title
            f.write(f'<tr><td>{i}</td><td>{title_html}</td>')
            f.write(f'<td data-val="{igmv}">{fmt_money(igmv)}</td>')
            f.write(f'<td data-val="{iunits}">{int(iunits):,}</td>')
            f.write(f'<td data-val="{ifees}">{fmt_money(ifees)}</td>')
            f.write(f'<td data-val="{ipct:.2f}">{fmt_pct(ipct)}</td>')
            f.write('</tr>\n')
        f.write('</tbody></table>\n</div>\n')

        # By category table
        f.write('<div class="section-title">Por Categoría</div>\n')
        f.write('<div class="table-card">\n')
        f.write('<table id="tbl-cat">\n')
        f.write('<thead><tr>')
        f.write('<th onclick="srt(\'tbl-cat\',0)">Categoría</th>')
        f.write('<th onclick="srt(\'tbl-cat\',1)">GMV</th>')
        f.write('<th onclick="srt(\'tbl-cat\',2)">Unidades</th>')
        f.write('<th onclick="srt(\'tbl-cat\',3)">% del Total</th>')
        f.write('</tr></thead><tbody>\n')
        for cname, cgmv, cunits, cpct in cat_rows:
            f.write(f'<tr><td>{cname}</td>')
            f.write(f'<td data-val="{cgmv}">{fmt_money(cgmv)}</td>')
            f.write(f'<td data-val="{cunits}">{int(cunits):,}</td>')
            f.write(f'<td data-val="{cpct:.2f}">{fmt_pct(cpct)}</td>')
            f.write('</tr>\n')
        f.write('</tbody></table>\n</div>\n')

        # Logistica breakdown
        f.write('<div class="section-title">Logística</div>\n')
        f.write('<div class="kpi-row">\n')
        total_log_gmv = full_gmv + flex_gmv + colecta_gmv
        log_items = [
            ('Full', full_gmv, full_units, 'var(--green)'),
            ('Flex', flex_gmv, flex_units, 'var(--purple)'),
        ]
        if colecta_gmv > 0:
            log_items.append(('Colecta', colecta_gmv, colecta_units, 'var(--yellow)'))
        for lname, lgmv, lunits, lcolor in log_items:
            lpct = (lgmv / total_log_gmv * 100) if total_log_gmv else 0
            f.write(f'<div class="kpi-card" style="border-left:3px solid {lcolor};">')
            f.write(f'<div class="kpi-label">{lname}</div>')
            f.write(f'<div class="kpi-val" style="color:{lcolor};">{fmt_money(lgmv)}</div>')
            f.write(f'<div class="kpi-prev">{int(lunits):,} unidades — {fmt_pct(lpct)} del total</div>')
            f.write('</div>\n')
        f.write('</div>\n')

        f.write('</div>\n')  # tab-ventas

        # ── TAB: HORARIOS ─────────────────────────────────────────────────────
        f.write('<div id="tab-horarios" class="tab-content">\n')

        # Heatmap
        f.write('<div class="chart-card">\n')
        f.write('<div class="chart-title">Heatmap GMV — Día × Hora</div>\n')
        f.write('<div style="overflow-x:auto;">\n')
        f.write('<table class="heatmap-table">\n')
        f.write('<thead><tr><th>Día\\H</th>\n')
        for h in range(24):
            f.write(f'<th>{h}</th>\n')
        f.write('</tr></thead>\n<tbody>\n')
        DOW_NAMES = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom']
        # Compute max for color scaling
        hm_max = max((heatmap[r][c] for r in range(len(heatmap)) for c in range(len(heatmap[r]))), default=1) or 1
        for r, dname in enumerate(DOW_NAMES):
            f.write(f'<tr><th>{dname}</th>\n')
            row_data = heatmap[r] if r < len(heatmap) else [0]*24
            for c in range(24):
                val = row_data[c] if c < len(row_data) else 0
                intensity = int(val / hm_max * 255)
                r_col = intensity
                g_col = int(intensity * 0.6)
                b_col = 50
                fmt_val = fmt_money(val) if val else '—'
                f.write(f'<td style="background:rgb({r_col},{g_col},{b_col});" title="{dname} {c}h: {fmt_val}">')
                f.write('</td>\n')
            f.write('</tr>\n')
        f.write('</tbody></table>\n</div>\n</div>\n')

        # Hourly bar chart
        f.write('<div class="two-col">\n')
        f.write('<div class="chart-card">\n')
        f.write('<div class="chart-title">GMV Promedio por Hora</div>\n')
        f.write('<canvas id="c-hourly" height="140"></canvas>\n')
        f.write('</div>\n')

        # DOW chart
        f.write('<div class="chart-card">\n')
        f.write('<div class="chart-title">Promedio Diario por Día de la Semana</div>\n')
        f.write('<canvas id="c-dow" height="140"></canvas>\n')
        f.write('</div>\n')
        f.write('</div>\n')  # two-col

        f.write('</div>\n')  # tab-horarios

        # ── TAB: STOCK ────────────────────────────────────────────────────────
        f.write('<div id="tab-stock" class="tab-content">\n')
        f.write('<div class="info-box"><strong>Nota:</strong> Para ver stock preciso por SKU, colocá el archivo <strong>stock_externo.xlsx</strong> en la carpeta ml_agent/ con columnas: sku, descripcion, stock_deposito, stock_full</div>\n')

        for section_name, section_items in [('Full (Fulfillment)', full_items_sorted), ('Flex (Cross Docking)', flex_items_sorted)]:
            f.write(f'<div class="section-title">{section_name} — {len(section_items)} publicaciones</div>\n')
            f.write(f'<div class="table-card">\n')
            tbl_id = 'tbl-full' if 'Full' in section_name else 'tbl-flex'
            f.write(f'<table id="{tbl_id}">\n')
            f.write('<thead><tr>')
            f.write(f'<th onclick="srt(\'{tbl_id}\',0)">Producto</th>')
            f.write(f'<th onclick="srt(\'{tbl_id}\',1)">Tipo</th>')
            f.write(f'<th onclick="srt(\'{tbl_id}\',2)">Stock Disponible</th>')
            f.write(f'<th onclick="srt(\'{tbl_id}\',3)">Ventas Mes</th>')
            f.write(f'<th onclick="srt(\'{tbl_id}\',4)">Health %</th>')
            f.write('</tr></thead><tbody>\n')
            for it in section_items[:30]:
                iid    = it.get('item_id', '')
                ititle = it.get('title', '') or iid
                iperm  = it.get('permalink', '') or ''
                ilt    = lt_label(it.get('listing_type_id', ''))
                istock = it.get('available_quantity', 0) or 0
                ihealth = (it.get('health', 0) or 0) * 100
                iunits_m = item_units_month.get(iid, 0)
                if ihealth >= 80:
                    hcol = 'var(--green)'
                elif ihealth >= 60:
                    hcol = 'var(--yellow)'
                else:
                    hcol = 'var(--red)'
                if iperm:
                    title_html = f'<a href="{iperm}" target="_blank">{ititle[:55]}</a>'
                else:
                    title_html = ititle[:55]
                lt_pill = 'pill-yellow' if ilt == 'Premium' else 'pill-blue'
                f.write(f'<tr><td>{title_html}</td>')
                f.write(f'<td><span class="pill {lt_pill}">{ilt}</span></td>')
                f.write(f'<td data-val="{istock}">{istock:,}</td>')
                f.write(f'<td data-val="{iunits_m}">{iunits_m:,}</td>')
                f.write(f'<td data-val="{ihealth:.0f}" title="Calidad de publicación según ML: >80% excelente, 60-80% buena, <60% necesita atención">')
                f.write(f'<span class="health-bar" style="width:{min(ihealth,100):.0f}px;background:{hcol};"></span> ')
                f.write(f'<span style="color:{hcol};">{ihealth:.0f}%</span></td>')
                f.write('</tr>\n')
            f.write('</tbody></table>\n</div>\n')

        f.write('</div>\n')  # tab-stock


        # ── TAB: COMISIONES ───────────────────────────────────────────────────
        f.write('<div id="tab-comisiones" class="tab-content">\n')

        # KPI cards
        f.write('<div class="kpi-row">\n')
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Total Comisiones</div>')
        f.write(f'<div class="kpi-val">{fmt_money(fees_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_money(fees_p)}</div>')
        f.write(f'<div class="kpi-delta {fees_cls}">{fees_arr}</div>')
        f.write('</div>\n')
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">% Comisión Promedio</div>')
        f.write(f'<div class="kpi-val">{fmt_pct(fee_rate_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_pct(fee_rate_p)}</div>')
        f.write(f'<div class="kpi-delta {fee_rate_cls}">{fee_rate_arr}</div>')
        f.write('</div>\n')
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Neto (GMV - Comisiones)</div>')
        f.write(f'<div class="kpi-val">{fmt_money(net_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_money(net_p)}</div>')
        f.write(f'<div class="kpi-delta {net_cls}">{net_arr}</div>')
        f.write('</div>\n')
        f.write('</div>\n')  # kpi-row

        f.write('<div class="warn-box"><strong>Nota:</strong> El costo de envío al vendedor estará disponible cuando se habilite el scope <strong>billing:read</strong> en la app de ML.</div>\n')

        # Donut chart
        f.write('<div class="chart-card" style="max-width:380px;">\n')
        f.write('<div class="chart-title">Distribución GMV / Comisiones / Neto</div>\n')
        f.write('<canvas id="c-fees-donut" height="220"></canvas>\n')
        f.write('</div>\n')

        # Top 20 by commissions
        f.write('<div class="section-title">Top 20 Productos por Comisión</div>\n')
        top20_fees = sorted(top_items[:25], key=lambda x: -(x.get('fees', 0) or 0))[:20]
        f.write('<div class="table-card">\n')
        f.write('<table id="tbl-com">\n')
        f.write('<thead><tr>')
        f.write('<th onclick="srt(\'tbl-com\',0)">Producto</th>')
        f.write('<th onclick="srt(\'tbl-com\',1)">GMV</th>')
        f.write('<th onclick="srt(\'tbl-com\',2)">Comisión</th>')
        f.write('<th onclick="srt(\'tbl-com\',3)">% Com.</th>')
        f.write('<th onclick="srt(\'tbl-com\',4)">Logística</th>')
        f.write('<th onclick="srt(\'tbl-com\',5)">Tipo Pub.</th>')
        f.write('</tr></thead><tbody>\n')
        for item in top20_fees:
            iid    = item.get('id', '')
            ititle = item.get('title', '') or iid
            igmv   = item.get('gmv', 0) or 0
            ifees  = item.get('fees', 0) or 0
            ipct   = (ifees / igmv * 100) if igmv else 0
            perm   = item_perms.get(iid, '')
            ilog   = item_log_map.get(iid, '')
            ilt    = lt_label(item_lt_map.get(iid, ''))
            log_label = 'Full' if ilog == 'fulfillment' else ('Flex' if ilog == 'cross_docking' else ilog)
            if perm:
                title_html = f'<a href="{perm}" target="_blank">{ititle[:50]}</a>'
            else:
                title_html = ititle[:50]
            lt_pill = 'pill-yellow' if ilt == 'Premium' else 'pill-blue'
            log_pill = 'pill-green' if log_label == 'Full' else 'pill-purple'
            f.write(f'<tr><td>{title_html}</td>')
            f.write(f'<td data-val="{igmv}">{fmt_money(igmv)}</td>')
            f.write(f'<td data-val="{ifees}">{fmt_money(ifees)}</td>')
            f.write(f'<td data-val="{ipct:.2f}">{fmt_pct(ipct)}</td>')
            f.write(f'<td><span class="pill {log_pill}">{log_label}</span></td>')
            f.write(f'<td><span class="pill {lt_pill}">{ilt}</span></td>')
            f.write('</tr>\n')
        f.write('</tbody></table>\n</div>\n')

        f.write('</div>\n')  # tab-comisiones

        # ── TAB: CANCELACIONES ────────────────────────────────────────────────
        f.write('<div id="tab-cancelaciones" class="tab-content">\n')

        f.write('<div class="kpi-row">\n')
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Total Cancelaciones</div>')
        f.write(f'<div class="kpi-val">{int(cancel_c):,}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {int(cancel_p):,}</div>')
        f.write(f'<div class="kpi-delta {cancel_cls}">{cancel_arr}</div>')
        f.write('</div>\n')
        f.write('<div class="kpi-card">')
        f.write('<div class="kpi-label">Tasa de Cancelación</div>')
        f.write(f'<div class="kpi-val">{fmt_pct(crate_c)}</div>')
        f.write(f'<div class="kpi-prev">Anterior: {fmt_pct(crate_p)}</div>')
        f.write(f'<div class="kpi-delta {crate_cls}">{crate_arr}</div>')
        f.write('</div>\n')
        f.write('</div>\n')

        if monthly:
            f.write('<div class="chart-card">\n')
            f.write('<div class="chart-title">Tasa de Cancelación Mensual 2026</div>\n')
            f.write('<canvas id="c-cancel-rate" height="80"></canvas>\n')
            f.write('</div>\n')

        # Top cancellations chart + table
        top_cancels = sorted(cancels_list, key=lambda x: -(x.get('rate', 0) or 0))[:15]
        f.write('<div class="chart-card">\n')
        f.write('<div class="chart-title">Top 15 Productos por Tasa de Cancelación</div>\n')
        f.write('<canvas id="c-cancel-bar" height="120"></canvas>\n')
        f.write('</div>\n')

        f.write('<div class="section-title">Detalle Cancelaciones</div>\n')
        f.write('<div class="table-card">\n')
        f.write('<table id="tbl-cancels">\n')
        f.write('<thead><tr>')
        f.write('<th onclick="srt(\'tbl-cancels\',0)">Producto</th>')
        f.write('<th onclick="srt(\'tbl-cancels\',1)">Cancelaciones</th>')
        f.write('<th onclick="srt(\'tbl-cancels\',2)">Órdenes Pagadas</th>')
        f.write('<th onclick="srt(\'tbl-cancels\',3)">Tasa %</th>')
        f.write('</tr></thead><tbody>\n')
        for item in top_cancels:
            iid    = item.get('id', '')
            ititle = item.get('title', '') or iid
            ic     = item.get('c', 0) or 0
            ip     = item.get('p', 0) or 0
            irate  = item.get('rate', 0) or 0
            perm   = item_perms.get(iid, '')
            if perm:
                title_html = f'<a href="{perm}" target="_blank">{ititle}</a>'
            else:
                title_html = ititle
            f.write(f'<tr><td>{title_html}</td>')
            f.write(f'<td data-val="{ic}">{ic:,}</td>')
            f.write(f'<td data-val="{ip}">{ip:,}</td>')
            f.write(f'<td data-val="{irate:.2f}">{fmt_pct(irate)}</td>')
            f.write('</tr>\n')
        f.write('</tbody></table>\n</div>\n')

        f.write('</div>\n')  # tab-cancelaciones

        # ── TAB: IMPUESTOS ────────────────────────────────────────────────────
        f.write('<div id="tab-impuestos" class="tab-content">\n')
        f.write('<div class="section-title">Percepciones y Retenciones por Provincia</div>\n')
        f.write('<div class="warn-box">')
        f.write('<strong>Tab requiere permisos adicionales.</strong><br><br>')
        f.write('Este tab requiere activar el scope <strong>finances:read</strong> o <strong>billing:read</strong> en tu app de Mercado Libre. ')
        f.write('Una vez habilitado, mostrará percepciones IIBB, retenciones de ganancias y IVA discriminadas por provincia, ')
        f.write('con % sobre la venta de cada zona.<br><br>')
        f.write('<strong>Instrucciones para habilitar:</strong><br>')
        f.write('1. Ir a <a href="https://developers.mercadolibre.com.ar" target="_blank">developers.mercadolibre.com.ar</a><br>')
        f.write('2. Seleccionar tu app → Permisos<br>')
        f.write('3. Activar <strong>billing:read</strong><br>')
        f.write('4. Ejecutar: <code>python ml_setup.py --authorize</code>')
        f.write('</div>\n')
        f.write('<div class="table-card">\n')
        f.write('<table><thead><tr>')
        f.write('<th>Provincia</th><th>IIBB Percepción</th><th>Ret. Ganancias</th><th>IVA</th><th>% sobre Venta</th>')
        f.write('</tr></thead><tbody>')
        f.write('<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:40px;">Datos no disponibles — habilitar billing:read</td></tr>')
        f.write('</tbody></table>\n</div>\n')
        f.write('</div>\n')  # tab-impuestos


        # ── JS DATA INJECTION ─────────────────────────────────────────────────
        f.write('<script>\n')
        f.write(f'const MONTHLY_LABELS={j_monthly_labels};\n')
        f.write(f'const MONTHLY_GMV={j_monthly_gmv};\n')
        f.write(f'const MONTHLY_UNITS={j_monthly_units};\n')
        f.write(f'const MONTHLY_CANCEL_RATE={j_monthly_cancel_rate};\n')
        f.write(f'const MONTHLY_FEES={j_monthly_fees};\n')
        f.write(f'const DAILY_LABELS={j_daily_labels};\n')
        f.write(f'const DAILY_CUR={j_daily_cur};\n')
        f.write(f'const DAILY_PRI={j_daily_pri};\n')
        f.write(f'const DOW_RAW={j_dow};\n')
        f.write(f'const DOW_COUNT={j_dow_count};\n')
        f.write(f'const HOUR_VALS={j_hour_vals};\n')
        f.write(f'const HEATMAP={j_heatmap};\n')
        f.write(f'const CLASSIC_GMV={j_classic_gmv};\n')
        f.write(f'const PREMIUM_GMV={j_premium_gmv};\n')
        f.write(f'const CLASSIC_UNITS={j_classic_units};\n')
        f.write(f'const PREMIUM_UNITS={j_premium_units};\n')
        f.write(f'const FLEX_GMV={j_flex_gmv};\n')
        f.write(f'const FULL_GMV={j_full_gmv};\n')
        f.write(f'const COLECTA_GMV={j_colecta_gmv};\n')
        f.write(f'const FLEX_UNITS={j_flex_units};\n')
        f.write(f'const FULL_UNITS={j_full_units};\n')
        f.write(f'const COLECTA_UNITS={j_colecta_units};\n')
        f.write(f'const FEES_C={j_fees_c};\n')
        f.write(f'const NET_C={j_net_c};\n')
        f.write(f'const GMV_C={j_gmv_c};\n')

        # Cancels data for chart
        cancel_titles = json.dumps([c.get('title', '')[:30] for c in top_cancels])
        cancel_rates  = json.dumps([c.get('rate', 0) or 0 for c in top_cancels])
        f.write(f'const CANCEL_TITLES={cancel_titles};\n')
        f.write(f'const CANCEL_RATES={cancel_rates};\n')
        f.write('</script>\n')

        # ── JS LOGIC (pure JS, no Python interpolation) ───────────────────────
        f.write('''<script>
// ── Tab switching ────────────────────────────────────────────────────────────
const built = new Set();
function T(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (!built.has(name)) { built.add(name); buildC(name); }
}

// ── Table sort ───────────────────────────────────────────────────────────────
const srtDir = {};
function srt(tid, col) {
  const tbl = document.getElementById(tid);
  if (!tbl) return;
  const tbody = tbl.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const key = tid + '_' + col;
  srtDir[key] = !srtDir[key];
  rows.sort((a, b) => {
    const ac = a.cells[col], bc = b.cells[col];
    if (!ac || !bc) return 0;
    const av = ac.dataset.val !== undefined ? parseFloat(ac.dataset.val) : ac.textContent.trim();
    const bv = bc.dataset.val !== undefined ? parseFloat(bc.dataset.val) : bc.textContent.trim();
    if (typeof av === 'number' && typeof bv === 'number') return srtDir[key] ? av - bv : bv - av;
    return srtDir[key] ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
  });
  rows.forEach(r => tbody.appendChild(r));
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
const BLUE   = '#3483FA';
const YELLOW = '#FFE600';
const GREEN  = '#00A650';
const RED    = '#F23D4F';
const PURPLE = '#9b59b6';
const MUTED  = '#7a7a9a';
const gridColor = 'rgba(255,255,255,0.05)';

const baseOpts = {
  responsive: true,
  plugins: { legend: { labels: { color: '#e0e0e0', boxWidth: 12 } } },
  scales: {
    x: { ticks: { color: MUTED }, grid: { color: gridColor } },
    y: { ticks: { color: MUTED }, grid: { color: gridColor } }
  }
};

function fmtM(v) {
  v = parseFloat(v) || 0;
  if (v >= 1e9) return '$' + (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return '$' + (v/1e6).toFixed(1) + 'M';
  if (v >= 1e3) return '$' + (v/1e3).toFixed(0) + 'K';
  return '$' + v.toFixed(0);
}

// ── Build charts per tab ───────────────────────────────────────────────────
function buildC(name) {
  if (name === 'resumen') buildResumen();
  else if (name === 'ventas') buildVentas();
  else if (name === 'horarios') buildHorarios();
  else if (name === 'comisiones') buildComisiones();
  else if (name === 'cancelaciones') buildCancelaciones();
}

// ── RESUMEN charts ────────────────────────────────────────────────────────
function buildResumen() {
  // Listing type chart
  const lt = document.getElementById('c-listing-type');
  if (lt) new Chart(lt, {
    type: 'bar',
    data: {
      labels: ['Clásica', 'Premium'],
      datasets: [
        { label: 'GMV', data: [CLASSIC_GMV, PREMIUM_GMV], backgroundColor: [BLUE, YELLOW], yAxisID: 'y' },
        { label: 'Unidades', data: [CLASSIC_UNITS, PREMIUM_UNITS], backgroundColor: [BLUE+'55', YELLOW+'55'], yAxisID: 'y2', type: 'line' }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e0e0e0', boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: MUTED }, grid: { color: gridColor } },
        y: { ticks: { color: MUTED, callback: v => fmtM(v) }, grid: { color: gridColor } },
        y2: { position: 'right', ticks: { color: MUTED }, grid: { display: false } }
      }
    }
  });

  // Logistic chart
  const lg = document.getElementById('c-logistic');
  if (lg) {
    const lgLabels = ['Full', 'Flex'];
    const lgGmv    = [FULL_GMV, FLEX_GMV];
    const lgUnits  = [FULL_UNITS, FLEX_UNITS];
    const lgBg     = [GREEN, PURPLE];
    if (COLECTA_GMV > 0) { lgLabels.push('Colecta'); lgGmv.push(COLECTA_GMV); lgUnits.push(COLECTA_UNITS); lgBg.push(YELLOW); }
    new Chart(lg, {
    type: 'bar',
    data: {
      labels: lgLabels,
      datasets: [
        { label: 'GMV', data: lgGmv, backgroundColor: lgBg, yAxisID: 'y' },
        { label: 'Unidades', data: lgUnits, backgroundColor: lgBg.map(c=>c+'55'), yAxisID: 'y2', type: 'line' }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e0e0e0', boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: MUTED }, grid: { color: gridColor } },
        y: { ticks: { color: MUTED, callback: v => fmtM(v) }, grid: { color: gridColor } },
        y2: { position: 'right', ticks: { color: MUTED }, grid: { display: false } }
      }
    });
  }
}

// ── VENTAS charts ─────────────────────────────────────────────────────────
function buildVentas() {
  const mg = document.getElementById('c-monthly-gmv');
  if (mg && MONTHLY_LABELS.length) new Chart(mg, {
    type: 'bar',
    data: {
      labels: MONTHLY_LABELS,
      datasets: [{ label: 'GMV', data: MONTHLY_GMV, backgroundColor: BLUE + 'bb', borderColor: BLUE, borderWidth: 1 }]
    },
    options: { ...baseOpts, plugins: { legend: { labels: { color: '#e0e0e0' } }, tooltip: { callbacks: { label: ctx => fmtM(ctx.raw) } } }, scales: { x: { ticks: { color: MUTED }, grid: { color: gridColor } }, y: { ticks: { color: MUTED, callback: v => fmtM(v) }, grid: { color: gridColor } } } }
  });

  const dg = document.getElementById('c-daily-gmv');
  if (dg) new Chart(dg, {
    type: 'line',
    data: {
      labels: DAILY_LABELS,
      datasets: [
        { label: 'Mes Actual', data: DAILY_CUR, borderColor: BLUE, backgroundColor: BLUE + '22', fill: true, tension: 0.3, pointRadius: 3 },
        { label: 'Mes Anterior', data: DAILY_PRI, borderColor: MUTED, backgroundColor: 'transparent', borderDash: [4,3], tension: 0.3, pointRadius: 2 }
      ]
    },
    options: { ...baseOpts, plugins: { legend: { labels: { color: '#e0e0e0' } }, tooltip: { callbacks: { label: ctx => fmtM(ctx.raw) } } }, scales: { x: { ticks: { color: MUTED }, grid: { color: gridColor } }, y: { ticks: { color: MUTED, callback: v => fmtM(v) }, grid: { color: gridColor } } } }
  });
}

// ── HORARIOS charts ───────────────────────────────────────────────────────
function buildHorarios() {
  // Hourly bar chart
  const hh = document.getElementById('c-hourly');
  const hours = Array.from({length: 24}, (_, i) => i + 'h');
  if (hh) new Chart(hh, {
    type: 'bar',
    data: {
      labels: hours,
      datasets: [{ label: 'GMV por Hora', data: HOUR_VALS, backgroundColor: BLUE + 'bb', borderColor: BLUE, borderWidth: 1 }]
    },
    options: { ...baseOpts, plugins: { legend: { labels: { color: '#e0e0e0' } }, tooltip: { callbacks: { label: ctx => fmtM(ctx.raw) } } }, scales: { x: { ticks: { color: MUTED, font: { size: 10 } }, grid: { color: gridColor } }, y: { ticks: { color: MUTED, callback: v => fmtM(v) }, grid: { color: gridColor } } } }
  });

  // DOW chart (avg per day)
  const dc = document.getElementById('c-dow');
  const dowNames = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
  const totalDow = DOW_RAW.reduce((a, b) => a + b, 0) || 1;
  const dowAvg   = DOW_RAW.map((v, i) => (DOW_COUNT[i] || 1) > 0 ? v / (DOW_COUNT[i] || 1) : 0);
  const dowShare = DOW_RAW.map(v => (v / totalDow * 100).toFixed(1));
  if (dc) new Chart(dc, {
    type: 'bar',
    data: {
      labels: dowNames,
      datasets: [{ label: 'Promedio Diario', data: dowAvg, backgroundColor: [BLUE,BLUE,BLUE,BLUE,BLUE,PURPLE,RED].map(c => c + 'bb'), borderColor: [BLUE,BLUE,BLUE,BLUE,BLUE,PURPLE,RED], borderWidth: 1 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => fmtM(ctx.raw) + ' (' + dowShare[ctx.dataIndex] + '% share)' } }
      },
      scales: { x: { ticks: { color: MUTED, callback: v => fmtM(v) }, grid: { color: gridColor } }, y: { ticks: { color: MUTED }, grid: { color: gridColor } } }
    }
  });
}

// ── COMISIONES charts ─────────────────────────────────────────────────────
function buildComisiones() {
  const dd = document.getElementById('c-fees-donut');
  if (dd) new Chart(dd, {
    type: 'doughnut',
    data: {
      labels: ['Neto', 'Comisiones'],
      datasets: [{ data: [NET_C, FEES_C], backgroundColor: [GREEN + 'cc', RED + 'cc'], borderColor: [GREEN, RED], borderWidth: 2 }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#e0e0e0' } },
        tooltip: { callbacks: { label: ctx => ctx.label + ': ' + fmtM(ctx.raw) } }
      }
    }
  });
}

// ── CANCELACIONES charts ──────────────────────────────────────────────────
function buildCancelaciones() {
  const cr = document.getElementById('c-cancel-rate');
  if (cr && MONTHLY_LABELS.length) new Chart(cr, {
    type: 'bar',
    data: {
      labels: MONTHLY_LABELS,
      datasets: [{ label: 'Tasa de Cancelación %', data: MONTHLY_CANCEL_RATE, backgroundColor: RED + 'bb', borderColor: RED, borderWidth: 1 }]
    },
    options: { ...baseOpts, plugins: { legend: { labels: { color: '#e0e0e0' } } }, scales: { x: { ticks: { color: MUTED }, grid: { color: gridColor } }, y: { ticks: { color: MUTED, callback: v => v + '%' }, grid: { color: gridColor } } } }
  });

  const cb = document.getElementById('c-cancel-bar');
  if (cb) new Chart(cb, {
    type: 'bar',
    data: {
      labels: CANCEL_TITLES,
      datasets: [{ label: 'Tasa %', data: CANCEL_RATES, backgroundColor: RED + 'bb', borderColor: RED, borderWidth: 1 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ctx.raw.toFixed(1) + '%' } }
      },
      scales: { x: { ticks: { color: MUTED, callback: v => v + '%' }, grid: { color: gridColor } }, y: { ticks: { color: MUTED, font: { size: 10 } }, grid: { color: gridColor } } }
    }
  });
}

// Init first tab
window.addEventListener('DOMContentLoaded', () => {
  built.add('resumen');
  setTimeout(() => buildC('resumen'), 100);
});
</script>
''')

        f.write('</body>\n</html>\n')

    sz = os.path.getsize(out)
    print(f'Generated: {out}')
    print(f'Size: {sz/1024:.1f} KB')
    return out


if __name__ == '__main__':
    build_dashboard()
