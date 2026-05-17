#!/usr/bin/env python3
import json, os, math, unicodedata
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUT_DIR  = os.path.join(BASE_DIR, 'dashboards')
os.makedirs(OUT_DIR, exist_ok=True)

def load_json(name):
    p = os.path.join(DATA_DIR, name)
    if not os.path.exists(p): return None
    with open(p, encoding='utf-8') as fh: return json.load(fh)

def jd(v): return json.dumps(v, ensure_ascii=False)

def fmt_money(v):
    v = float(v or 0)
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000: return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"

def delta_pct(cur, pri):
    c, p = float(cur or 0), float(pri or 0)
    if not p: return None
    return ((c - p) / p) * 100

def arrow(pct, inv=False):
    if pct is None: return "—", "neutral"
    if pct > 0: return f"▲ {pct:.1f}%", ("bad" if inv else "good")
    if pct < 0: return f"▼ {abs(pct):.1f}%", ("good" if inv else "bad")
    return "= 0%", "neutral"

# Title-based keyword → STATUS internal category (order matters: more specific first)
TITLE_RULES = [
    # COOK — real COOK items: espumadores de leche, pavas eléctricas
    (['ESPUMADOR DE LECHE', 'PAVA ELECTRICA', 'PAVA TIVOLI', 'PAVA DIGITAL'], 'COOK'),
    # PEQUEÑO ELECTRO
    (['BATIDORA', 'AMASADORA', 'STAND MIXER'], 'PEQUEÑO ELECTRO'),
    (['FREIDORA', 'AIR FRYER', 'HORNO FREIDOR'], 'PEQUEÑO ELECTRO'),
    (['CAFETERA'], 'PEQUEÑO ELECTRO'),
    (['MICROONDAS'], 'PEQUEÑO ELECTRO'),
    (['ASPIRADORA', 'ASPIRADOR', 'LAVATAPIZADO'], 'PEQUEÑO ELECTRO'),
    (['LICUADORA'], 'PEQUEÑO ELECTRO'),
    (['TOSTADORA'], 'PEQUEÑO ELECTRO'),
    (['WAFLERA', 'GOFRERA'], 'PEQUEÑO ELECTRO'),
    (['YOGURTERA'], 'PEQUEÑO ELECTRO'),
    (['EXPRIMIDOR'], 'PEQUEÑO ELECTRO'),
    (['MULTIRALLADOR', 'RALLADOR'], 'PEQUEÑO ELECTRO'),
    (['PROCESADORA', 'PROCESADOR ALIM'], 'PEQUEÑO ELECTRO'),
    (['JUGUERA'], 'PEQUEÑO ELECTRO'),
    (['SANDWICHERA', 'SANWICHERA'], 'PEQUEÑO ELECTRO'),
    (['PARRILLA', 'PLANCHA GRILL'], 'PEQUEÑO ELECTRO'),
    (['FABRICA DE MINI', 'FABRICA DE DONA', 'DONUTS', 'DONA MAKER'], 'PEQUEÑO ELECTRO'),
    # AUDIO
    (['PARTY BOX', 'PARLANTE', 'ALTAVOZ'], 'AUDIO'),
    (['AURICULAR', 'VINCHA', 'HEADPHONE', 'EARPHONE'], 'AUDIO'),
    (['TRIPODE PARA PARLANTE', 'TRIPODE PARLANTE'], 'AUDIO'),
    (['RADIO AM', 'RADIO FM'], 'AUDIO'),
    # LUCES
    (['REFLECTOR'], 'LUCES'),
    (['PLAFON', 'PANEL LED', 'PANEL 595', 'DOWNLIGHT'], 'LUCES'),
    (['LUZ DE EMERGENCIA', 'LUZ EMERGENCIA'], 'LUCES'),
    (['DRIVER', 'FUENTE 12W', 'FUENTE 6W', 'FUENTE 18W', 'FUENTE 24W'], 'LUCES'),
    (['LISTON BAJO MESADA'], 'LUCES'),
    # HERRAMIENTAS
    (['TALADRO'], 'HERRAMIENTAS'),
    (['AMOLADORA'], 'HERRAMIENTAS'),
    (['HIDROLAVADORA'], 'HERRAMIENTAS'),
    (['DESTORNILLADOR', 'ATORNILLADOR'], 'HERRAMIENTAS'),
    (['LIJADORA'], 'HERRAMIENTAS'),
    # ACCESORIOS BICICLETA
    (['CICLOCOMPUTADORA', 'CICLOCOMPUTADOR'], 'ACCESORIOS BICICLETA'),
    (['COMPRESOR PORTATIL', 'COMPRESOR BICICLETA', 'COMPRESOR CUBO'], 'ACCESORIOS BICICLETA'),
    (['CYCPLUS', 'ANT+ CICLISMO', 'RECEPTOR USB ANT'], 'ACCESORIOS BICICLETA'),
    # BIENESTAR
    (['MASAJEADOR', 'PISTOLA MASAJEAD'], 'BIENESTAR'),
    (['EJERCITADOR PARA ABDOMIN', 'EJERCITADOR ABDOMIN', 'ABS-250', 'RUEDA ABDOMINAL'], 'BIENESTAR'),
    (['EJERCITADOR DE PISO', 'EJERCITADOR PISO', 'EJERCITADOR PARA PISO'], 'BIENESTAR'),
    # SALUD
    (['BALANZA', 'BASCULA'], 'SALUD'),
    # CCTV
    (['CAMARA DE SEGURIDAD', 'CAMARA INDOOR', 'CAMARA OUTDOOR', 'DOBLE CAMARA'], 'CCTV'),
    # GAMING
    (['SILLA GAMER', 'SILLA GAMING'], 'GAMING'),
    # JUGUETES
    (['PISTOLA DE AGUA', 'PISTOLA AGUA', 'BURBUJERO', 'PISTOLA BURBUJAS'], 'JUGUETES'),
    (['MALETIN DE ARTE', 'SET DE ARTE', 'KIT DE ARTE', 'BLOQUES MAGNETICO', 'JUEGO MAGNETICO'], 'JUGUETES'),
    (['CONTROL REMOTO', 'BUGGY', 'AUTO A CONTROL', 'CAMIONETA A CONTROL'], 'JUGUETES'),
    # TEMPORADA
    (['VENTILADOR'], 'TEMPORADA'),
    # ARTICULOS PARA OFICINA
    (['CONTADOR DE BILLETE', 'CONTADORA DE BILLETE', 'CONTADORA BILLETE'], 'ARTICULOS PARA OFICINA'),
    # ARTICULOS PARA EL HOGAR
    (['MAQUINA DE COSER', 'MÁQUINA DE COSER'], 'ARTICULOS PARA EL HOGAR'),
    # PET
    (['CORTAPELO', 'SECADORA PARA MASCOTA', 'CORTAPELO ASPIRADORA'], 'PET'),
    # PC - INFORMATICA
    (['BASE PARA NOTEBOOK', 'BASE NOTEBOOK'], 'PC - INFORMATICA'),
    (['SOPORTE PARA MONITOR', 'SOPORTE MONITOR', 'BASE MONITOR', 'MONITOR SOPORTE'], 'PC - INFORMATICA'),
]

def _norm(s):
    """Uppercase + strip accents for accent-insensitive matching."""
    s = (s or '').upper()
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('ascii')

def classify_title(title):
    """Classify ML listing title into STATUS internal category."""
    t = _norm(title)
    for keywords, cat in TITLE_RULES:
        if any(k in t for k in keywords):
            return cat
    return 'VARIOS'

# ML category ID → STATUS internal category (used for PRIOR period only)
ML_CAT_TO_INTERNAL = {
    'MLA10085': 'PEQUEÑO ELECTRO',   # Batidoras planetarias
    'MLA456045': 'PEQUEÑO ELECTRO',  # Freidoras de aire
    'MLA416847': 'PEQUEÑO ELECTRO',  # Fábricas donuts
    'MLA1577':   'PEQUEÑO ELECTRO',  # Microondas
    'MLA4340':   'PEQUEÑO ELECTRO',  # Cafeteras de filtro
    'MLA4622':   'ARTICULOS PARA EL HOGAR',  # Máquinas de coser
    'MLA4339':   'PEQUEÑO ELECTRO',  # Procesadoras / ralladores
    'MLA8618':   'AUDIO',            # Parlantes portátiles
    'MLA370796': 'ACCESORIOS BICICLETA',     # Compresores Cycplus
    'MLA4337':   'PEQUEÑO ELECTRO',  # Aspiradoras de mano
    'MLA126142': 'PEQUEÑO ELECTRO',  # Yogurteras
    'MLA1588':   'LUCES',            # Plafones LED
    'MLA447782': 'GAMING',           # Sillas gamer
    'MLA409403': 'PEQUEÑO ELECTRO',  # Wafleras
    'MLA74279':  'PEQUEÑO ELECTRO',  # Exprimidores eléctricos
    'MLA5232':   'HERRAMIENTAS',     # Taladros inalámbricos
    'MLA10104':  'HERRAMIENTAS',     # Lijadoras
    'MLA401457': 'PEQUEÑO ELECTRO',  # Aspiradoras robot
    'MLA104680': 'PEQUEÑO ELECTRO',  # Licuadoras personales
    'MLA370486': 'PET',              # Aspiradoras mascotas
    'MLA373611': 'PEQUEÑO ELECTRO',  # Parrillas / sandwicheras
    'MLA417723': 'BIENESTAR',        # Masajeadores
    'MLA371883': 'ACCESORIOS BICICLETA',     # GPS Cycplus
    'MLA30840':  'HERRAMIENTAS',     # Hidrolavadoras
    'MLA388313': 'JUGUETES',         # Burbujeros
    'MLA414164': 'JUGUETES',         # Kits de arte
    'MLA9554':   'SALUD',            # Balanzas digitales
    'MLA126135': 'PEQUEÑO ELECTRO',  # Sandwicheras
    'MLA86840':  'PEQUEÑO ELECTRO',  # Aspiradoras tapizados
    'MLA3697':   'AUDIO',            # Auriculares
    'MLA10068':  'PEQUEÑO ELECTRO',  # Tostadoras
    'MLA30803':  'HERRAMIENTAS',     # Destornilladores
    'MLA407557': 'ARTICULOS PARA OFICINA',   # Contadoras de billetes
    'MLA10569':  'AUDIO',            # Trípodes parlante
    'MLA74278':  'PEQUEÑO ELECTRO',  # Jugueras
    'MLA5229':   'HERRAMIENTAS',     # Amoladoras
    'MLA456969': 'HERRAMIENTAS',     # Taladros percutores
    'MLA418043': 'PC - INFORMATICA', # Soportes monitor doble
    'MLA373504': 'LUCES',            # Reflectores LED
    'MLA5848':   'LUCES',            # Drivers LED
    'MLA417835': 'CCTV',             # Cámaras seguridad
    'MLA455865': 'TEMPORADA',        # Ventiladores portátiles
    'MLA438177': 'BIENESTAR',        # Ejercitadores abdominales
    'MLA9760':   'ACCESORIOS BICICLETA',     # Receptor ANT+ Cycplus
    'MLA418042': 'PC - INFORMATICA', # Bases monitor
    'MLA90321':  'JUGUETES',         # Pistolas de agua
    'MLA417724': 'BIENESTAR',        # Masajeadores de mano
    'MLA417130': 'VARIOS',           # Limpialentes
    'MLA125102': 'LUCES',            # Luces emergencia
    'MLA435473': 'PEQUEÑO ELECTRO',  # Exprimidores manuales
    'MLA3098':   'BIENESTAR',        # Ejercitadores piso
    'MLA413405': 'PEQUEÑO ELECTRO',  # Marcadores / sellos de carne
    'MLA417716': 'VARIOS',           # Aro de luz
}

def build_dashboard():
    mc  = load_json('metrics_current.json') or {}
    mp  = load_json('metrics_prior.json') or {}
    ec  = load_json('enrich_current.json') or {}
    ep  = load_json('enrich_prior.json') or {}
    sm  = load_json('summary.json') or {}
    rep = load_json('reputation.json') or {}
    ads = load_json('ads_manual.json') or {}
    mon = load_json('monthly_2026.json') or []
    stk = load_json('stock_status.json') or []
    sku = load_json('sku_categories.json') or {}
    items_list = load_json('items.json') or []

    today    = date.today()
    max_day  = today.day

    # ── Compute units_by_item + GMV + DOW units from orders ─────────────────
    orders_cur = load_json('orders_current.json') or []
    units_by_item = {}
    dow_units_raw = [0.0] * 7
    for o in orders_cur:
        if o.get('status') == 'cancelled': continue
        ds = o.get('date_closed') or o.get('date_created') or ''
        try:
            dobj = datetime.fromisoformat(ds[:19])
            dow  = dobj.weekday()
        except Exception:
            dow = 0
        for it in o.get('items', []):
            iid   = it.get('item_id', '?')
            qty   = it.get('quantity', 0) or 0
            price = float(it.get('unit_price', 0) or it.get('full_unit_price', 0) or 0)
            title = it.get('title', '')
            if iid not in units_by_item:
                units_by_item[iid] = {'units': 0, 'gmv': 0.0, 'title': title}
            units_by_item[iid]['units'] += qty
            units_by_item[iid]['gmv']   += qty * price
            dow_units_raw[dow] += qty

    # ── Build internal category grouping for Ventas (title-based) ───────────
    by_int_cur = {}
    for iid, d in units_by_item.items():
        cat = classify_title(d.get('title', ''))
        if cat not in by_int_cur:
            by_int_cur[cat] = {'gmv': 0.0, 'units': 0}
        by_int_cur[cat]['gmv']   += d['gmv']
        by_int_cur[cat]['units'] += d['units']
    for cat, v in by_int_cur.items():
        v['gmv'] = round(v['gmv'])
        v['avg_ticket'] = round(v['gmv'] / v['units']) if v['units'] else 0

    # Prior period: use ML category ID → STATUS mapping
    by_cat_pri = ep.get('by_category', {})
    by_int_pri = {}
    for cid, v in by_cat_pri.items():
        cat = ML_CAT_TO_INTERNAL.get(cid, 'VARIOS')
        if cat not in by_int_pri:
            by_int_pri[cat] = {'gmv': 0, 'units': 0}
        by_int_pri[cat]['gmv']   += v.get('gmv', 0)
        by_int_pri[cat]['units'] += v.get('units', 0)

    # ── Build ML items list for Stock tab ────────────────────────────────────
    # Primary: ML order data (exact sales). Overlay: STATUS stock data where matched.
    unique_days = mc.get('unique_days', 1) or 1
    item_avail = {i['item_id']: (i.get('available_quantity') or 0) for i in items_list}
    # Index STATUS by code (uppercased) for fast lookup
    stk_by_code = {}
    for s in stk:
        cod = (s.get('codigo') or '').upper().strip()
        if cod:
            stk_by_code[cod] = s

    ml_items_list = []
    for iid, d in units_by_item.items():
        title     = d['title']
        cat       = classify_title(title)
        avail_qty = item_avail.get(iid, 0)
        units_p   = d['units']
        gmv_p     = round(d['gmv'])
        # Compute dias_stock from ML available_quantity / daily_sales_rate
        daily_rate = units_p / unique_days if unique_days else 0
        dias = round(avail_qty / daily_rate) if daily_rate > 0 else None
        # Try STATUS match: exact code in title
        title_up = title.upper()
        status_match = None
        for cod, s in stk_by_code.items():
            if cod in title_up:
                status_match = s
                break
        row = {
            'item_id':     iid,
            'title':       title,
            'categoria':   status_match['categoria'] if status_match else cat,
            'sub_cat':     status_match.get('sub_cat', '') if status_match else '',
            'codigo':      status_match['codigo'] if status_match else '',
            'units_period': units_p,
            'gmv_period':  gmv_p,
            'available_qty': avail_qty,
            'dias_stock':  dias,
            'stock_dep':   status_match.get('stock_dep') if status_match else None,
            'stock_full':  status_match.get('stock_full') if status_match else None,
            'stock_aduana': status_match.get('stock_aduana') if status_match else None,
            'has_status':  bool(status_match),
        }
        ml_items_list.append(row)

    # Sort by category then units desc
    ml_items_list.sort(key=lambda x: (x['categoria'], -x['units_period']))

    # Keep stk_sorted for the STATUS stock KPIs still used by old stock tab
    stk_sorted = sorted(stk, key=lambda s: (
        s.get('categoria', '') or '',
        s.get('sub_cat', '') or '',
        s.get('codigo', '') or ''
    ))

    # ── Other data ───────────────────────────────────────────────────────────
    daily_cur   = mc.get('daily_stats', {})
    daily_pri   = mp.get('daily_stats', {})
    unique_days = mc.get('unique_days', 1) or 1
    dow_count   = mc.get('dow_count', [1]*7)
    dow_raw     = mc.get('dow', [0]*7)
    by_hour     = ec.get('by_hour', {})
    lt_cur      = ec.get('by_listing_type', {})
    lt_pri      = ep.get('by_listing_type', {})
    log_cur     = ec.get('by_logistic', {})
    log_pri     = ep.get('by_logistic', {})
    top_items   = mc.get('top', []) or []
    cancels     = mc.get('cancels', []) or []

    period_cur = sm.get('period_cur_label', 'Mes actual')
    period_pri = sm.get('period_pri_label', 'Mes anterior')
    updated_at = (sm.get('updated_at', '')[:16] or '').replace('T', ' ')

    a_inv   = float(ads.get('inversion', 0) or 0)
    a_rev   = float(ads.get('ingresos', 0) or 0)
    a_impr  = float(ads.get('impresiones', 0) or 0)
    a_clics = float(ads.get('clics', 0) or 0)
    a_ventas= float(ads.get('ventas', 0) or 0)
    a_roas  = f"{a_rev/a_inv:.2f}x" if a_inv else "—"
    a_tacos = f"{a_inv/a_rev*100:.1f}%" if a_rev else "—"
    a_ctr   = f"{a_clics/a_impr*100:.2f}%" if a_impr else "—"
    a_cpc   = fmt_money(a_inv/a_clics) if a_clics else "—"
    a_conv  = f"{a_ventas/a_clics*100:.1f}%" if a_clics else "—"

    rep_st  = rep.get('power_seller_status', '')
    rep_lbl = {'platinum':'MercadoLíder Platinum','gold':'MercadoLíder Gold',
               'silver':'MercadoLíder Silver'}.get(rep_st, rep_st.title() if rep_st else '—')
    rep_col = {'platinum':'#00d4e4','gold':'#FFD700','silver':'#A0A0A0'}.get(rep_st, '#aaa')

    gmv_c  = mc.get('gmv', 0) or 0
    gmv_p  = mp.get('gmv', 0) or 0
    un_c   = mc.get('units', 0) or 0
    un_p   = mp.get('units', 0) or 0
    pd_c   = mc.get('paid', 0) or 0
    pd_p   = mp.get('paid', 0) or 0
    net_c  = mc.get('net', 0) or 0
    net_p  = mp.get('net', 0) or 0
    tk_c   = mc.get('avg_ticket', 0) or 0
    tk_p   = mp.get('avg_ticket', 0) or 0
    cr_c   = mc.get('cancel_rate', 0) or 0
    cr_p   = mp.get('cancel_rate', 0) or 0
    fees_c = mc.get('fees', 0) or 0
    fee_rate_c = mc.get('fee_rate', 0) or 0
    fee_rate_p = mp.get('fee_rate', 0) or 0

    out_path = os.path.join(OUT_DIR, 'ml_dashboard_360.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        def w(s): f.write(s + '\n')

        # HEAD
        w('<!DOCTYPE html><html lang="es">')
        w('<head><meta charset="UTF-8">')
        w('<meta name="viewport" content="width=device-width,initial-scale=1.0">')
        w(f'<title>ML 360° · SPOTCOMPRAS · {updated_at}</title>')
        w('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>')
        f.write("""<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d1a;color:#e0e0f0;font-family:system-ui,-apple-system,sans-serif;font-size:14px}
:root{--blue:#3483FA;--yellow:#FFE600;--green:#00A650;--red:#F23D4F;--purple:#7B2FF7;--cyan:#00d4e4}
.nav{display:flex;gap:4px;padding:10px 14px;background:#0d0d2e;border-bottom:1px solid #1e1e3a;overflow-x:auto;flex-wrap:nowrap;-webkit-overflow-scrolling:touch;position:sticky;top:0;z-index:100}
.nav-btn{background:#151528;color:#888;border:1px solid #1e1e3a;border-radius:8px;padding:6px 13px;cursor:pointer;white-space:nowrap;font-size:13px;transition:.2s}
.nav-btn:hover,.nav-btn.active{background:#3483FA;color:#fff;border-color:#3483FA}
.nav-btn.active{font-weight:700}
.tab{display:none;padding:14px 16px}.tab.active{display:block}
.header{background:linear-gradient(135deg,#0d0d2e,#151540);border-radius:12px;padding:14px 18px;margin-bottom:14px;border:1px solid #1e1e3a}
.header h1{font-size:18px;font-weight:700;color:var(--blue)}.header .meta{font-size:11px;color:#666;margin-top:3px}
.card{background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:14px;overflow:hidden}
.card-title{padding:11px 16px;font-size:11px;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #1e1e3a}
.card-body{padding:14px 16px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
.kpi{background:#151528;border-radius:12px;border:1px solid #1e1e3a;padding:12px 14px}
.kpi-label{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.3px;margin-bottom:5px}
.kpi-val{font-size:20px;font-weight:700;color:#fff}
.kpi-delta{font-size:12px;margin-top:3px}.kpi-pri{font-size:11px;color:#444;margin-top:2px}
.good{color:var(--green)}.bad{color:var(--red)}.neutral{color:#888}
.chart-wrap{position:relative;width:100%}
.tbl-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{padding:8px 11px;text-align:left;font-size:11px;color:#555;font-weight:600;text-transform:uppercase;border-bottom:2px solid #1e1e3a;white-space:nowrap}
td{padding:8px 11px;border-bottom:1px solid #181830;white-space:nowrap}
tr:hover td{background:#1a1a35}
.slider-row{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#0d0d2e;border-radius:8px;margin-bottom:12px;flex-wrap:wrap}
.slider-row label{font-size:12px;color:#888;white-space:nowrap}
.slider-row input[type=range]{flex:1;min-width:100px;accent-color:var(--blue)}
.slider-val{font-size:14px;font-weight:700;color:var(--yellow);white-space:nowrap;min-width:90px}
.pct-row{display:flex;align-items:center;gap:8px;margin-bottom:9px}
.pct-lbl{font-size:12px;color:#ccc;min-width:120px;flex-shrink:0}
.pct-track{flex:1;background:#1e1e3a;border-radius:4px;height:11px;overflow:hidden}
.pct-fill{height:100%;border-radius:4px}
.pct-num{font-size:12px;color:#888;min-width:90px;text-align:right;flex-shrink:0}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}
.b-ok{background:#00A65020;color:var(--green)}.b-low{background:#FFE60020;color:var(--yellow)}.b-zero{background:#F23D4F20;color:var(--red)}
.rep-metric{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #1e1e3a}
.rep-metric:last-child{border-bottom:none}
.rep-lbl{font-size:12px;color:#888}.rep-val{font-size:13px;font-weight:700;color:#fff}
.ads-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.ads-kpi{background:#0d0d2e;border-radius:10px;padding:12px;text-align:center}
.ads-kpi .lbl{font-size:11px;color:#555;margin-bottom:6px}
.ads-kpi .val{font-size:20px;font-weight:700}
.cat-group-hdr td{background:#1a1a40;color:var(--blue);font-weight:700;font-size:12px}
@media(max-width:900px){.kpi-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.kpi-grid{grid-template-columns:repeat(2,1fr)}.kpi-val{font-size:17px}.header h1{font-size:15px}}
@media(max-width:400px){.nav-btn{padding:5px 8px;font-size:11px}}
</style></head>""")

        # BODY + NAV
        w('<body>')
        w('<div class="nav">')
        for idx, lbl in enumerate(['📊 Resumen','📈 Ventas','🕐 Horarios','📦 Stock','❌ Cancelaciones','🏅 Reputación','⚡ Ads','🏆 Top Items']):
            ac = ' active' if idx == 0 else ''
            w(f'<button class="nav-btn{ac}" onclick="showTab({idx})">{lbl}</button>')
        w('</div>')

        # DATA SCRIPT
        w('<script>')
        w(f'const DAILY_CUR={jd(daily_cur)};')
        w(f'const DAILY_PRI={jd(daily_pri)};')
        w(f'const UNIQUE_DAYS={unique_days};')
        w(f'const DOW_COUNT={jd(dow_count)};')
        w(f'const DOW_RAW={jd(dow_raw)};')
        w(f'const DOW_UNITS_RAW={jd(dow_units_raw)};')
        w(f'const BY_HOUR={jd(by_hour)};')
        w(f'const BY_INT_CUR={jd(by_int_cur)};')
        w(f'const BY_INT_PRI={jd(by_int_pri)};')
        w(f'const LT_CUR={jd(lt_cur)};')
        w(f'const LT_PRI={jd(lt_pri)};')
        w(f'const LOG_CUR={jd(log_cur)};')
        w(f'const LOG_PRI={jd(log_pri)};')
        w(f'const MONTHLY={jd(mon)};')
        w(f'const STOCK_DATA={jd(stk_sorted)};')
        w(f'const ML_ITEMS_DATA={jd(ml_items_list)};')
        w(f'const TOP_ITEMS={jd(top_items)};')
        w(f'const CANCELS={jd(cancels)};')
        w(f'const MC={jd(mc)};')
        w(f'const MP={jd(mp)};')
        w(f'const REP={jd(rep)};')
        w(f'const ADS={jd(ads)};')
        w(f'const MAX_DAY={max_day};')
        w(f'const PERIOD_CUR={jd(period_cur)};')
        w(f'const PERIOD_PRI={jd(period_pri)};')
        w(f'const FEE_RATE_C={fee_rate_c};')
        w(f'const FEE_RATE_P={fee_rate_p};')
        w('</script>')

        # TAB 0: RESUMEN
        w('<div id="tab0" class="tab active">')
        w(f'<div class="header"><h1>📊 Dashboard ML 360° · SPOTCOMPRAS</h1>')
        w(f'<div class="meta">Actualizado: {updated_at} &nbsp;|&nbsp; {period_cur} vs {period_pri}</div></div>')
        w('<div class="slider-row">')
        w(f'<label>Filtrar días del mes:</label>')
        w(f'<input type="range" id="day-slider" min="1" max="{max_day}" value="{max_day}" oninput="updateResumen()">')
        w(f'<span class="slider-val" id="slider-lbl">1–{max_day}</span>')
        w('</div>')
        w('<div class="kpi-grid" id="kpi-grid"></div>')
        w('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">')
        w('<div class="card"><div class="card-title">Tipo de publicación</div>')
        w('<div class="card-body" id="lt-section"></div></div>')
        w('<div class="card"><div class="card-title">Tipo de envío</div>')
        w('<div class="card-body" id="log-section"></div></div>')
        w('</div>')
        w('<div class="card"><div class="card-title">GMV diario · mes actual</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:200px">')
        w('<canvas id="c-daily"></canvas></div></div></div>')
        w('</div>')

        # TAB 1: VENTAS
        w('<div id="tab1" class="tab">')
        w(f'<div class="header"><h1>📈 Ventas</h1><div class="meta">{period_cur} vs {period_pri}</div></div>')
        w('<div class="card"><div class="card-title">GMV mensual 2026</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:260px">')
        w('<canvas id="c-monthly"></canvas></div></div></div>')
        w('<div class="card"><div class="card-title">Ventas por categoría interna · mes actual</div>')
        w('<div class="card-body tbl-scroll">')
        w('<table><thead><tr><th>Categoría</th><th>GMV</th><th>Unidades</th><th>Ticket Prom.</th><th>% GMV</th><th>vs Mes ant.</th></tr></thead>')
        w('<tbody id="cat-tbody"></tbody></table></div></div>')
        w('</div>')

        # TAB 2: HORARIOS
        w('<div id="tab2" class="tab">')
        w(f'<div class="header"><h1>🕐 Horarios</h1><div class="meta">Promedio por hora y día · {period_cur} ({unique_days} días activos)</div></div>')
        w('<div class="card"><div class="card-title">Promedio GMV por hora del día</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:240px">')
        w('<canvas id="c-hour"></canvas></div></div></div>')
        w('<div class="card"><div class="card-title">Promedio GMV y unidades por día de semana</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:240px">')
        w('<canvas id="c-dow"></canvas></div></div></div>')
        w('</div>')

        # TAB 3: STOCK
        cats_ml = sorted(set(r.get('categoria','') for r in ml_items_list if r.get('categoria','')))
        w('<div id="tab3" class="tab">')
        w(f'<div class="header"><h1>📦 Stock</h1><div class="meta">Fuente: ML órdenes ({len(ml_items_list)} ítems · {sum(r["units_period"] for r in ml_items_list):,}u) + stock STATUS</div></div>')
        w('<div id="stock-summary" class="kpi-grid"></div>')
        w('<div class="slider-row" style="margin-bottom:10px">')
        w('<label>Categoría:</label>')
        w('<select id="stk-cat-filter" onchange="renderStock()" style="background:#1a1a35;color:#e0e0f0;border:1px solid #2a2a4a;border-radius:6px;padding:4px 8px;font-size:13px">')
        w('<option value="">Todas</option>')
        for c in cats_ml:
            w(f'<option value="{c}">{c}</option>')
        w('</select>')
        w('<label style="margin-left:8px">Stock:</label>')
        w('<select id="stk-show-filter" onchange="renderStock()" style="background:#1a1a35;color:#e0e0f0;border:1px solid #2a2a4a;border-radius:6px;padding:4px 8px;font-size:13px">')
        w('<option value="all">Todos</option>')
        w('<option value="zero">Sin stock ML</option>')
        w('<option value="low">Stock bajo (&lt;10)</option>')
        w('<option value="critical">Días &lt; 7</option>')
        w('</select>')
        w('</div>')
        w('<div class="card"><div class="card-title">Ventas por ítem ML · stock disponible · días estimados</div>')
        w('<div class="card-body tbl-scroll">')
        w('<table><thead><tr>')
        w('<th>Producto</th><th>Categoría</th><th>Sub-cat</th><th>SKU</th>')
        w('<th>Vtas período</th><th>GMV período</th><th>Stock ML</th>')
        w('<th>Días stock</th><th>Dep.</th><th>Full</th><th>Aduana</th></tr></thead>')
        w('<tbody id="stock-tbody"></tbody></table></div></div>')
        w('</div>')

        # TAB 4: CANCELACIONES
        w('<div id="tab4" class="tab">')
        w(f'<div class="header"><h1>❌ Cancelaciones</h1><div class="meta">{period_cur} · {int(mc.get("cancelled",0)):,} canceladas · Tasa: {cr_c:.1f}%</div></div>')
        w('<div class="kpi-grid">')
        ar, ac_col = arrow(delta_pct(cr_c, cr_p), inv=True)
        w(f'<div class="kpi"><div class="kpi-label">Tasa cancelación</div><div class="kpi-val">{cr_c:.1f}%</div><div class="kpi-delta {ac_col}">{ar}</div><div class="kpi-pri">Ant: {cr_p:.1f}%</div></div>')
        w(f'<div class="kpi"><div class="kpi-label">Canceladas</div><div class="kpi-val" style="color:var(--red)">{int(mc.get("cancelled",0)):,}</div></div>')
        w(f'<div class="kpi"><div class="kpi-label">Pagadas</div><div class="kpi-val" style="color:var(--green)">{int(pd_c):,}</div></div>')
        w('</div>')
        w('<div class="card"><div class="card-title">Productos con más cancelaciones</div>')
        w('<div class="card-body tbl-scroll">')
        w('<table><thead><tr><th>#</th><th>Producto</th><th>Canceladas</th><th>Pagadas</th><th>Tasa</th></tr></thead><tbody>')
        for i, cx in enumerate(cancels[:20], 1):
            rate = cx.get('rate', 0)
            col = 'bad' if rate > 10 else ('neutral' if rate > 5 else 'good')
            w(f'<tr><td>{i}</td><td>{cx.get("title","")}</td><td style="color:var(--red)">{cx.get("c",0)}</td><td>{cx.get("p",0)}</td><td class="{col}">{rate:.1f}%</td></tr>')
        w('</tbody></table></div></div>')
        w('</div>')

        # TAB 5: REPUTACION
        w('<div id="tab5" class="tab">')
        w(f'<div class="header"><h1>🏅 Reputación</h1><div class="meta">Datos al {updated_at}</div></div>')
        w(f'<div class="card" style="border-left:4px solid {rep_col}"><div class="card-body">')
        w(f'<div style="font-size:22px;font-weight:700;color:{rep_col};margin-bottom:8px">{rep_lbl}</div>')
        w(f'<div style="font-size:13px;color:#888">Usuario: {rep.get("nickname","—")} &nbsp;|&nbsp; Nivel: {rep.get("level_id","—")}</div>')
        w('</div></div>')
        claims_pct  = (rep.get('claims_rate', 0) or 0) * 100
        delayed_pct = (rep.get('delayed_rate', 0) or 0) * 100
        canc_pct    = (rep.get('cancellations_rate', 0) or 0) * 100
        sales60     = rep.get('sales_60d', 0) or 0
        rat_pos     = (rep.get('ratings_positive', 0) or 0) * 100
        rat_neg     = (rep.get('ratings_negative', 0) or 0) * 100
        total_ord   = rep.get('total', 0) or 0
        completed   = rep.get('completed', 0) or 0
        canceled_h  = rep.get('canceled', 0) or 0
        w('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">')
        for lbl, val, col in [
            ('Ventas 60 días', f'{sales60:,}', '#fff'),
            ('Total histórico', f'{total_ord:,}', '#fff'),
            ('Completadas', f'{completed:,}', 'var(--green)'),
            ('Canceladas hist.', f'{canceled_h:,}', 'var(--red)'),
        ]:
            w(f'<div class="kpi"><div class="kpi-label">{lbl}</div><div class="kpi-val" style="color:{col}">{val}</div></div>')
        w('</div>')
        w('<div class="card"><div class="card-title">Métricas de calidad (60 días)</div><div class="card-body">')
        for lbl, val, warn, bad_thr in [('Reclamos', claims_pct, 1.0, 2.0),('Envíos tardíos', delayed_pct, 6.0, 10.0),('Cancelaciones', canc_pct, 0.5, 1.5)]:
            col = 'var(--red)' if val > bad_thr else ('var(--yellow)' if val > warn else 'var(--green)')
            w(f'<div class="rep-metric"><span class="rep-lbl">{lbl}</span><span class="rep-val" style="color:{col}">{val:.2f}%</span></div>')
        w(f'<div class="rep-metric"><span class="rep-lbl">Calificaciones positivas</span><span class="rep-val" style="color:var(--green)">{rat_pos:.1f}%</span></div>')
        w(f'<div class="rep-metric"><span class="rep-lbl">Calificaciones negativas</span><span class="rep-val" style="color:var(--red)">{rat_neg:.1f}%</span></div>')
        w('</div></div>')
        w(f'<div class="card" style="border-left:3px solid var(--cyan)"><div class="card-body" style="font-size:12px;color:#888">')
        w(f'Con {claims_pct:.2f}% reclamos · {delayed_pct:.2f}% tardíos · {canc_pct:.3f}% cancelaciones tu nivel ')
        w(f'<b style="color:{rep_col}">{rep_lbl}</b> se mantiene estable. MercadoLibre evalúa los últimos 60 días cada semana.')
        w('</div></div>')
        w('</div>')

        # TAB 6: ADS
        w('<div id="tab6" class="tab">')
        w(f'<div class="header"><h1>⚡ Ads & Costos</h1><div class="meta">Fuente: panel ML Ads (carga manual) · {ads.get("fecha","—")} · {ads.get("periodo","")}</div></div>')
        w('<div class="card" style="border-left:3px solid var(--yellow)"><div class="card-body" style="font-size:12px;color:#888">')
        w('ℹ️ Datos cargados manualmente desde el panel de ML Ads. ')
        w('Para ver el desglose diario, cargá los datos en <b style="color:#ccc">data/ads_manual.json</b> con el campo <b style="color:#ccc">dias</b>: ')
        w('[{"fecha":"2026-05-01","inversion":..., "ingresos":..., "clics":...}, ...]')
        w('</div></div>')
        w('<div class="card"><div class="card-title">KPIs Ads</div><div class="card-body">')
        w('<div class="ads-grid">')
        for lbl, val, col in [
            ('Inversión', fmt_money(a_inv), 'var(--purple)'),
            ('Ingresos ads', fmt_money(a_rev), 'var(--green)'),
            ('ROAS', a_roas, 'var(--green)'),
            ('TACOS', a_tacos, 'var(--yellow)'),
            ('CTR', a_ctr, 'var(--blue)'),
            ('CPC', a_cpc, 'var(--cyan)'),
            ('Conv. rate', a_conv, 'var(--green)'),
            ('Comisiones', fmt_money(fees_c), 'var(--red)'),
        ]:
            w(f'<div class="ads-kpi"><div class="lbl">{lbl}</div><div class="val" style="color:{col}">{val}</div></div>')
        w('</div></div></div>')
        w('<div class="card"><div class="card-title">Tráfico</div><div class="card-body">')
        w('<div class="ads-grid">')
        for lbl, val, col in [
            ('Impresiones', f'{int(a_impr):,}', 'var(--blue)'),
            ('Clics', f'{int(a_clics):,}', 'var(--cyan)'),
            ('Ventas ads', f'{int(a_ventas):,}', 'var(--green)'),
            ('GMV total', fmt_money(gmv_c), '#fff'),
        ]:
            w(f'<div class="ads-kpi"><div class="lbl">{lbl}</div><div class="val" style="color:{col}">{val}</div></div>')
        w('</div></div></div>')
        w('<div class="card"><div class="card-title">Distribución de costos sobre GMV</div><div class="card-body">')
        gmv_f = float(gmv_c) or 1
        for lbl, val, col in [('Comisiones ML', fees_c, 'var(--red)'),('Inversión Ads', a_inv, 'var(--purple)'),('Neto est.', max(0, float(net_c) - a_inv), 'var(--green)')]:
            pct = val / gmv_f * 100
            w(f'<div class="pct-row"><span class="pct-lbl">{lbl}</span><div class="pct-track"><div class="pct-fill" style="width:{min(100,int(pct))}%;background:{col}"></div></div><span class="pct-num" style="color:{col}">{fmt_money(val)} ({pct:.1f}%)</span></div>')
        w('</div></div>')
        w('</div>')

        # TAB 7: TOP ITEMS
        w('<div id="tab7" class="tab">')
        w(f'<div class="header"><h1>🏆 Top 25 Productos</h1><div class="meta">{period_cur}</div></div>')
        w('<div class="slider-row" style="margin-bottom:10px">')
        w('<label>Ordenar por:</label>')
        w('<select id="top-sort" onchange="renderTopItems()" style="background:#1a1a35;color:#e0e0f0;border:1px solid #2a2a4a;border-radius:6px;padding:4px 8px;font-size:13px">')
        w('<option value="gmv">GMV</option><option value="units">Unidades</option><option value="fee_rate">Comisión %</option></select>')
        w('</div>')
        w('<div class="card"><div class="card-body tbl-scroll">')
        w('<table><thead><tr><th>#</th><th>Producto</th><th>GMV</th><th>Unidades</th><th>Comisiones</th><th>Com. %</th></tr></thead>')
        w('<tbody id="top-tbody"></tbody></table></div></div>')
        w('</div>')
        w('</body>')

        f.write("""<script>
function showTab(n){
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',i===n));
  document.querySelectorAll('.nav-btn').forEach((b,i)=>b.classList.toggle('active',i===n));
  if(n===1) renderVentas();
  if(n===2) renderHorarios();
  if(n===3) renderStock();
  if(n===7) renderTopItems();
}
function fmtM(v){v=parseFloat(v||0);if(v>=1e6)return'$'+(v/1e6).toFixed(2)+'M';if(v>=1e3)return'$'+(v/1e3).toFixed(0)+'K';return'$'+Math.round(v).toLocaleString('es-AR');}
function fmtN(v){return Math.round(v||0).toLocaleString('es-AR');}
function dPct(c,p){if(!p)return null;return((c-p)/p)*100;}
function arrowHtml(pct,inv){
  if(pct===null)return'<span class="neutral">--</span>';
  let cls=(pct>0?(inv?'bad':'good'):(pct<0?(inv?'good':'bad'):'neutral'));
  let sym=pct>0?'▲':'▼';
  return'<span class="'+cls+'">'+sym+' '+Math.abs(pct).toFixed(1)+'%</span>';
}

// RESUMEN
function updateResumen(){
  const maxD=parseInt(document.getElementById('day-slider').value);
  document.getElementById('slider-lbl').textContent='1–'+maxD;
  let gc=0,uc=0,pc=0,cc=0;
  for(let d=1;d<=maxD;d++){const ds=DAILY_CUR[String(d)]||{};gc+=ds.gmv||0;uc+=ds.units||0;pc+=ds.paid||0;cc+=ds.canc||0;}
  let gp=0,up=0,pp=0,cp=0;
  for(let d=1;d<=maxD;d++){const ds=DAILY_PRI[String(d)]||{};gp+=ds.gmv||0;up+=ds.units||0;pp+=ds.paid||0;cp+=ds.canc||0;}
  const tkc=uc?gc/uc:0, tkp=up?gp/up:0;
  const crc=(pc+cc)?cc/(pc+cc)*100:0, crp=(pp+cp)?cp/(pp+cp)*100:0;
  const netc=gc*(1-FEE_RATE_C/100), netp=gp*(1-FEE_RATE_P/100);
  const kpis=[
    {lbl:'GMV',val:fmtM(gc),pri:fmtM(gp),pct:dPct(gc,gp)},
    {lbl:'Unidades',val:fmtN(uc),pri:fmtN(up),pct:dPct(uc,up)},
    {lbl:'Ord. pagadas',val:fmtN(pc),pri:fmtN(pp),pct:dPct(pc,pp)},
    {lbl:'Neto (est.)',val:fmtM(netc),pri:fmtM(netp),pct:dPct(netc,netp)},
    {lbl:'Ticket prom.',val:fmtM(tkc),pri:fmtM(tkp),pct:dPct(tkc,tkp)},
    {lbl:'Tasa cancel.',val:crc.toFixed(1)+'%',pri:crp.toFixed(1)+'%',pct:dPct(crc,crp),inv:true},
  ];
  document.getElementById('kpi-grid').innerHTML=kpis.map(k=>'<div class="kpi"><div class="kpi-label">'+k.lbl+'</div><div class="kpi-val">'+k.val+'</div><div class="kpi-delta">'+arrowHtml(k.pct,k.inv||false)+'</div><div class="kpi-pri">Ant: '+k.pri+'</div></div>').join('');
  renderPctBars('lt-section',LT_CUR,LT_PRI,['#3483FA','#7B2FF7','#00d4e4','#00A650']);
  renderPctBars('log-section',LOG_CUR,LOG_PRI,['#00A650','#7B2FF7','#FFE600','#F23D4F']);
  renderDailyChart(maxD);
}
function renderPctBars(id,data,dataPri,colors){
  const el=document.getElementById(id);
  const entries=Object.entries(data).sort((a,b)=>b[1].gmv-a[1].gmv);
  const tot=entries.reduce((s,[,v])=>s+v.gmv,0)||1;
  el.innerHTML=entries.map(([k,v],i)=>{
    const pct=v.gmv/tot*100;
    const col=colors[i%colors.length];
    const priGmv=(dataPri[k]||{}).gmv||0;
    const delta=priGmv?dPct(v.gmv,priGmv):null;
    const dlbl=delta===null?'':'<span class="'+(delta>=0?'good':'bad')+'" style="font-size:11px"> '+(delta>=0?'▲':'▼')+Math.abs(delta).toFixed(0)+'%</span>';
    const kn=k==='unknown'?'Colecta / Otro':k;
    return'<div class="pct-row"><span class="pct-lbl">'+kn+'</span><div class="pct-track"><div class="pct-fill" style="width:'+Math.min(100,Math.round(pct))+'%;background:'+col+'"></div></div><span class="pct-num">'+pct.toFixed(1)+'%'+dlbl+'</span></div>';
  }).join('');
}
let chartDaily=null;
function renderDailyChart(maxD){
  const labels=[],vals=[],unVals=[];
  for(let d=1;d<=maxD;d++){
    const ds=DAILY_CUR[String(d)]||{};
    labels.push(d);
    vals.push(ds.gmv||0);
    unVals.push(ds.units||0);
  }
  const ctx=document.getElementById('c-daily');if(!ctx)return;
  if(chartDaily)chartDaily.destroy();
  chartDaily=new Chart(ctx,{type:'bar',data:{labels,datasets:[
    {type:'bar',label:'GMV',data:vals,backgroundColor:'#3483FA88',borderColor:'#3483FA',borderWidth:1,borderRadius:3,yAxisID:'y'},
    {type:'line',label:'Unidades',data:unVals,borderColor:'#00A650',backgroundColor:'#00A65022',tension:.3,pointRadius:3,pointBackgroundColor:'#00A650',borderWidth:2,yAxisID:'y2'},
  ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aaa',font:{size:11}}},tooltip:{mode:'index',callbacks:{label:c=>c.datasetIndex===0?fmtM(c.raw):fmtN(c.raw)+'u'}}},scales:{
    x:{ticks:{color:'#666',font:{size:10}}},
    y:{position:'left',ticks:{color:'#3483FA',font:{size:10},callback:v=>fmtM(v)},grid:{color:'#1e1e3a'}},
    y2:{position:'right',ticks:{color:'#00A650',font:{size:10}},grid:{display:false}},
  }}});
}

// VENTAS
let chartMonthly=null;
function renderVentas(){
  const labels=MONTHLY.map(m=>m.label||'');
  const gmvVals=MONTHLY.map(m=>m.gmv||0);
  const unVals=MONTHLY.map(m=>m.units||0);
  const ctx=document.getElementById('c-monthly');
  if(ctx){
    if(chartMonthly)chartMonthly.destroy();
    chartMonthly=new Chart(ctx,{type:'bar',data:{labels,datasets:[
      {type:'bar',label:'GMV',data:gmvVals,backgroundColor:labels.map((_,i)=>i===labels.length-1?'#FFE60088':'#3483FA55'),borderColor:labels.map((_,i)=>i===labels.length-1?'#FFE600':'#3483FA'),borderWidth:1,borderRadius:4,yAxisID:'y'},
      {type:'line',label:'Unidades',data:unVals,borderColor:'#00A650',backgroundColor:'#00A65022',tension:.3,pointRadius:4,pointBackgroundColor:'#00A650',yAxisID:'y2'},
    ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aaa',font:{size:11}}},tooltip:{mode:'index'}},scales:{
      x:{ticks:{color:'#888',font:{size:11}}},
      y:{position:'left',ticks:{color:'#3483FA',callback:v=>fmtM(v)},grid:{color:'#1e1e3a'}},
      y2:{position:'right',ticks:{color:'#00A650'},grid:{display:false}},
    }}});
  }
  const totalGmv=Object.values(BY_INT_CUR).reduce((s,v)=>s+v.gmv,0)||1;
  const rows=Object.entries(BY_INT_CUR).sort((a,b)=>b[1].gmv-a[1].gmv);
  document.getElementById('cat-tbody').innerHTML=rows.map(([cat,cv])=>{
    const pctGmv=(cv.gmv/totalGmv*100).toFixed(1);
    const priV=(BY_INT_PRI[cat]||{}).gmv||0;
    const delta=priV?dPct(cv.gmv,priV):null;
    const avgTick=cv.units?Math.round(cv.gmv/cv.units):0;
    return'<tr><td style="font-weight:600">'+cat+'</td><td>'+fmtM(cv.gmv)+'</td><td>'+fmtN(cv.units)+'</td><td>'+fmtM(avgTick)+'</td><td style="color:#888">'+pctGmv+'%</td><td>'+arrowHtml(delta,false)+'</td></tr>';
  }).join('');
}

// HORARIOS
let chartHour=null, chartDow=null;
function renderHorarios(){
  const hours=Array.from({length:24},(_,i)=>i);
  const hourVals=hours.map(h=>(BY_HOUR[String(h)]||0)/UNIQUE_DAYS);
  const ctx1=document.getElementById('c-hour');
  if(ctx1){
    if(chartHour)chartHour.destroy();
    chartHour=new Chart(ctx1,{type:'bar',data:{labels:hours.map(h=>h+':00'),datasets:[{data:hourVals,backgroundColor:'#3483FA66',borderColor:'#3483FA',borderWidth:1,borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'Prom: '+fmtM(c.raw)}}},scales:{x:{ticks:{color:'#666',font:{size:10},maxRotation:45}},y:{ticks:{color:'#666',callback:v=>fmtM(v)}}}}});
  }
  const DOW_LABELS=['Lun','Mar','Mie','Jue','Vie','Sab','Dom'];
  const dowGmvAvg=DOW_RAW.map((v,i)=>DOW_COUNT[i]?v/DOW_COUNT[i]:0);
  const dowUnAvg=DOW_UNITS_RAW.map((v,i)=>DOW_COUNT[i]?v/DOW_COUNT[i]:0);
  const ctx2=document.getElementById('c-dow');
  if(ctx2){
    if(chartDow)chartDow.destroy();
    chartDow=new Chart(ctx2,{type:'bar',data:{labels:DOW_LABELS,datasets:[
      {type:'bar',label:'GMV prom',data:dowGmvAvg,backgroundColor:'#3483FA55',borderColor:'#3483FA',borderWidth:1,borderRadius:4,yAxisID:'y'},
      {type:'line',label:'Unidades prom',data:dowUnAvg,borderColor:'#00A650',backgroundColor:'#00A65022',tension:.3,pointRadius:5,pointBackgroundColor:'#00A650',yAxisID:'y2'},
    ]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aaa',font:{size:11}}},tooltip:{mode:'index'}},scales:{
      x:{ticks:{color:'#aaa'}},
      y:{position:'left',ticks:{color:'#3483FA',callback:v=>fmtM(v)},grid:{color:'#1e1e3a'}},
      y2:{position:'right',ticks:{color:'#00A650'},grid:{display:false}},
    }}});
  }
}
""")

        f.write("""
// STOCK
function renderStock(){
  const catF=document.getElementById('stk-cat-filter').value;
  const showF=document.getElementById('stk-show-filter').value;
  let data=[...ML_ITEMS_DATA];
  if(catF) data=data.filter(s=>(s.categoria||'')==catF);
  if(showF==='zero') data=data.filter(s=>!(s.available_qty>0));
  else if(showF==='low') data=data.filter(s=>s.available_qty>0&&s.available_qty<10);
  else if(showF==='critical') data=data.filter(s=>s.dias_stock!=null&&s.dias_stock<7);
  // KPI summary
  const total=ML_ITEMS_DATA.length;
  const totalUnits=ML_ITEMS_DATA.reduce((s,r)=>s+r.units_period,0);
  const zeros=ML_ITEMS_DATA.filter(s=>!(s.available_qty>0)).length;
  const critical=ML_ITEMS_DATA.filter(s=>s.dias_stock!=null&&s.dias_stock<7).length;
  const withStatus=ML_ITEMS_DATA.filter(s=>s.has_status).length;
  document.getElementById('stock-summary').innerHTML=
    '<div class="kpi"><div class="kpi-label">Ítems activos</div><div class="kpi-val">'+total+'</div></div>'+
    '<div class="kpi"><div class="kpi-label">Unidades vendidas</div><div class="kpi-val" style="color:var(--blue)">'+fmtN(totalUnits)+'</div></div>'+
    '<div class="kpi"><div class="kpi-label">Sin stock ML</div><div class="kpi-val" style="color:var(--red)">'+zeros+'</div></div>'+
    '<div class="kpi"><div class="kpi-label">Críticos (&lt;7d)</div><div class="kpi-val" style="color:var(--yellow)">'+critical+'</div></div>'+
    '<div class="kpi"><div class="kpi-label">Con SKU STATUS</div><div class="kpi-val" style="color:#888">'+withStatus+'</div></div>';
  let prevCat='';
  document.getElementById('stock-tbody').innerHTML=data.map(s=>{
    const dias=s.dias_stock;
    const diasTxt=dias!=null?dias+'d':'—';
    const diasCol=dias!=null?(dias<7?'var(--red)':dias<30?'var(--yellow)':'var(--green)'):'#555';
    const avail=s.available_qty||0;
    const availCol=avail<=0?'var(--red)':avail<10?'var(--yellow)':'var(--green)';
    const dep=s.stock_dep!=null?s.stock_dep:'—';
    const full=s.stock_full!=null?s.stock_full:'—';
    const aduana=s.stock_aduana!=null?s.stock_aduana:'—';
    const skuBadge=s.codigo?'<span class="badge b-ok" style="font-size:10px">'+s.codigo+'</span> ':'';
    let catHdr='';
    if(s.categoria!==prevCat){prevCat=s.categoria;catHdr='<tr class="cat-group-hdr"><td colspan="11">'+s.categoria+'</td></tr>';}
    return catHdr+'<tr>'+
      '<td style="max-width:200px;white-space:normal;font-size:12px">'+skuBadge+'<span title="'+s.item_id+'">'+s.title+'</span></td>'+
      '<td style="color:#666;font-size:11px">'+s.categoria+'</td>'+
      '<td style="color:#555;font-size:11px">'+(s.sub_cat||'—')+'</td>'+
      '<td style="color:#555;font-size:11px">'+(s.codigo||'—')+'</td>'+
      '<td style="color:var(--blue);font-weight:700">'+fmtN(s.units_period)+'u</td>'+
      '<td style="color:#888">'+fmtM(s.gmv_period)+'</td>'+
      '<td style="color:'+availCol+';font-weight:700">'+fmtN(avail)+'</td>'+
      '<td style="color:'+diasCol+';font-weight:700">'+diasTxt+'</td>'+
      '<td style="color:#666">'+dep+'</td>'+
      '<td style="color:var(--cyan)">'+full+'</td>'+
      '<td style="color:var(--yellow)">'+aduana+'</td>'+
      '</tr>';
  }).join('');
}

// TOP ITEMS
function renderTopItems(){
  const sortBy=document.getElementById('top-sort').value;
  let items=[...TOP_ITEMS];
  if(sortBy==='units') items.sort((a,b)=>b.units-a.units);
  else if(sortBy==='fee_rate') items.sort((a,b)=>((b.fees||0)/b.gmv)-((a.fees||0)/a.gmv));
  else items.sort((a,b)=>b.gmv-a.gmv);
  document.getElementById('top-tbody').innerHTML=items.map((it,i)=>{
    const feeRate=it.gmv?((it.fees||0)/it.gmv*100).toFixed(1):'--';
    return'<tr><td style="color:#555">'+(i+1)+'</td><td style="max-width:240px;white-space:normal;font-size:12px">'+(it.title||it.id)+'</td><td>'+fmtM(it.gmv)+'</td><td>'+fmtN(it.units)+'</td><td style="color:var(--red)">'+fmtM(it.fees||0)+'</td><td style="color:'+(parseFloat(feeRate)>15?'var(--red)':'#888')+'">'+feeRate+'%</td></tr>';
  }).join('');
}

// INIT
updateResumen();
renderTopItems();
</script>
</html>
""")

    return out_path


if __name__ == '__main__':
    out = build_dashboard()
    print(f"Dashboard: {out}")
