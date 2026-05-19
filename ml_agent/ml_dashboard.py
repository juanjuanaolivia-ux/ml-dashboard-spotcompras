#!/usr/bin/env python3
import json, os, math, unicodedata, re
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
    (['ESPUMADOR DE LECHE', 'PAVA ELECTRICA', 'PAVA TIVOLI', 'PAVA DIGITAL'], 'PEQUEÑOS ELECTRO'),
    # PEQUEÑO ELECTRO
    (['BATIDORA', 'AMASADORA', 'STAND MIXER'], 'PEQUEÑOS ELECTRO'),
    (['FREIDORA', 'AIR FRYER', 'HORNO FREIDOR'], 'PEQUEÑOS ELECTRO'),
    (['CAFETERA'], 'PEQUEÑOS ELECTRO'),
    (['MICROONDAS'], 'PEQUEÑOS ELECTRO'),
    (['ASPIRADORA', 'ASPIRADOR', 'LAVATAPIZADO'], 'PEQUEÑOS ELECTRO'),
    (['LICUADORA'], 'PEQUEÑOS ELECTRO'),
    (['TOSTADORA'], 'PEQUEÑOS ELECTRO'),
    (['WAFLERA', 'GOFRERA'], 'PEQUEÑOS ELECTRO'),
    (['YOGURTERA'], 'PEQUEÑOS ELECTRO'),
    (['EXPRIMIDOR'], 'PEQUEÑOS ELECTRO'),
    (['MULTIRALLADOR', 'RALLADOR'], 'PEQUEÑOS ELECTRO'),
    (['PROCESADORA', 'PROCESADOR ALIM'], 'PEQUEÑOS ELECTRO'),
    (['JUGUERA'], 'PEQUEÑOS ELECTRO'),
    (['SANDWICHERA', 'SANWICHERA'], 'PEQUEÑOS ELECTRO'),
    (['PARRILLA', 'PLANCHA GRILL'], 'PEQUEÑOS ELECTRO'),
    (['FABRICA DE MINI', 'FABRICA DE DONA', 'DONUTS', 'DONA MAKER'], 'PEQUEÑOS ELECTRO'),
    # AUDIO
    (['PARTY BOX', 'PARLANTE', 'ALTAVOZ'], 'AUDIO'),
    (['AURICULAR', 'VINCHA', 'HEADPHONE', 'EARPHONE'], 'AUDIO'),
    (['TRIPODE PARA PARLANTE', 'TRIPODE PARLANTE'], 'AUDIO'),
    (['RADIO AM', 'RADIO FM'], 'AUDIO'),
    # LUCES
    (['REFLECTOR'], 'ILUMINACION'),
    (['PLAFON', 'PANEL LED', 'PANEL 595', 'DOWNLIGHT'], 'ILUMINACION'),
    (['LUZ DE EMERGENCIA', 'LUZ EMERGENCIA'], 'ILUMINACION'),
    (['DRIVER', 'FUENTE 12W', 'FUENTE 6W', 'FUENTE 18W', 'FUENTE 24W'], 'ILUMINACION'),
    (['LISTON BAJO MESADA'], 'ILUMINACION'),
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
    'MLA10085': 'PEQUEÑOS ELECTRO',   # Batidoras planetarias
    'MLA456045': 'PEQUEÑOS ELECTRO',  # Freidoras de aire
    'MLA416847': 'PEQUEÑOS ELECTRO',  # Fábricas donuts
    'MLA1577':   'PEQUEÑOS ELECTRO',  # Microondas
    'MLA4340':   'PEQUEÑOS ELECTRO',  # Cafeteras de filtro
    'MLA4622':   'ARTICULOS PARA EL HOGAR',  # Máquinas de coser
    'MLA4339':   'PEQUEÑOS ELECTRO',  # Procesadoras / ralladores
    'MLA8618':   'AUDIO',            # Parlantes portátiles
    'MLA370796': 'ACCESORIOS BICICLETA',     # Compresores Cycplus
    'MLA4337':   'PEQUEÑOS ELECTRO',  # Aspiradoras de mano
    'MLA126142': 'PEQUEÑOS ELECTRO',  # Yogurteras
    'MLA1588':   'ILUMINACION',            # Plafones LED
    'MLA447782': 'GAMING',           # Sillas gamer
    'MLA409403': 'PEQUEÑOS ELECTRO',  # Wafleras
    'MLA74279':  'PEQUEÑOS ELECTRO',  # Exprimidores eléctricos
    'MLA5232':   'HERRAMIENTAS',     # Taladros inalámbricos
    'MLA10104':  'HERRAMIENTAS',     # Lijadoras
    'MLA401457': 'PEQUEÑOS ELECTRO',  # Aspiradoras robot
    'MLA104680': 'PEQUEÑOS ELECTRO',  # Licuadoras personales
    'MLA370486': 'PET',              # Aspiradoras mascotas
    'MLA373611': 'PEQUEÑOS ELECTRO',  # Parrillas / sandwicheras
    'MLA417723': 'BIENESTAR',        # Masajeadores
    'MLA371883': 'ACCESORIOS BICICLETA',     # GPS Cycplus
    'MLA30840':  'HERRAMIENTAS',     # Hidrolavadoras
    'MLA388313': 'JUGUETES',         # Burbujeros
    'MLA414164': 'JUGUETES',         # Kits de arte
    'MLA9554':   'SALUD',            # Balanzas digitales
    'MLA126135': 'PEQUEÑOS ELECTRO',  # Sandwicheras
    'MLA86840':  'PEQUEÑOS ELECTRO',  # Aspiradoras tapizados
    'MLA3697':   'AUDIO',            # Auriculares
    'MLA10068':  'PEQUEÑOS ELECTRO',  # Tostadoras
    'MLA30803':  'HERRAMIENTAS',     # Destornilladores
    'MLA407557': 'ARTICULOS PARA OFICINA',   # Contadoras de billetes
    'MLA10569':  'AUDIO',            # Trípodes parlante
    'MLA74278':  'PEQUEÑOS ELECTRO',  # Jugueras
    'MLA5229':   'HERRAMIENTAS',     # Amoladoras
    'MLA456969': 'HERRAMIENTAS',     # Taladros percutores
    'MLA418043': 'PC - INFORMATICA', # Soportes monitor doble
    'MLA373504': 'ILUMINACION',            # Reflectores LED
    'MLA5848':   'ILUMINACION',            # Drivers LED
    'MLA417835': 'CCTV',             # Cámaras seguridad
    'MLA455865': 'TEMPORADA',        # Ventiladores portátiles
    'MLA438177': 'BIENESTAR',        # Ejercitadores abdominales
    'MLA9760':   'ACCESORIOS BICICLETA',     # Receptor ANT+ Cycplus
    'MLA418042': 'PC - INFORMATICA', # Bases monitor
    'MLA90321':  'JUGUETES',         # Pistolas de agua
    'MLA417724': 'BIENESTAR',        # Masajeadores de mano
    'MLA417130': 'VARIOS',           # Limpialentes
    'MLA125102': 'ILUMINACION',            # Luces emergencia
    'MLA435473': 'PEQUEÑOS ELECTRO',  # Exprimidores manuales
    'MLA3098':   'BIENESTAR',        # Ejercitadores piso
    'MLA413405': 'PEQUEÑOS ELECTRO',  # Marcadores / sellos de carne
    'MLA417716': 'VARIOS',           # Aro de luz
}


def build_dashboard():
    mc    = load_json('metrics_current.json') or {}
    mp    = load_json('metrics_prior.json') or {}
    ec    = load_json('enrich_current.json') or {}
    ep    = load_json('enrich_prior.json') or {}
    sm    = load_json('summary.json') or {}
    rep   = load_json('reputation.json') or {}
    ads   = load_json('ads_manual.json') or {}
    costs = load_json('costs_manual.json') or {}
    mon   = load_json('monthly_2026.json') or []
    stk   = load_json('stock_status.json') or []
    items_list = load_json('items.json') or []

    today   = date.today()
    max_day = today.day

    # ── FUENTE MAESTRA: MLA → SKU (Excel maestro) ───────────────────────────
    mla_to_sku   = {}   # item_id → sku_code (authoritative)
    mla_es_combo = {}   # item_id → units_per_combo
    cat_excel    = {}   # sku_code → {categoria, sub_cat, descripcion}

    _excel_path = os.path.join(OUT_DIR, 'Categoría y subcategoría por código.xlsx')
    if os.path.exists(_excel_path):
        try:
            import openpyxl
            _wb = openpyxl.load_workbook(_excel_path, data_only=True)
            # Hoja MLA-Código → mapping MLA → SKU
            if 'MLA-Código' in _wb.sheetnames:
                _ws = _wb['MLA-Código']
                for _r in range(2, _ws.max_row + 1):
                    _mla  = str(_ws.cell(_r, 1).value or '').strip()
                    _cod  = str(_ws.cell(_r, 2).value or '').strip()
                    _cmb  = str(_ws.cell(_r, 3).value or '').strip().upper()
                    _unit = _ws.cell(_r, 5).value
                    if _mla and _cod:
                        mla_to_sku[_mla]   = _cod
                        if _cmb == 'SI':
                            mla_es_combo[_mla] = int(_unit) if _unit else 1
            # Hoja Sheet1 → SKU → categoria/sub_cat
            if 'Sheet1' in _wb.sheetnames:
                _ws2 = _wb['Sheet1']
                for _r in range(2, _ws2.max_row + 1):
                    _cod  = str(_ws2.cell(_r, 1).value or '').strip()
                    _desc = str(_ws2.cell(_r, 2).value or '').strip()
                    _cat  = str(_ws2.cell(_r, 3).value or '').strip()
                    _sub  = str(_ws2.cell(_r, 4).value or '').strip()
                    if _cod:
                        cat_excel[_cod] = {'descripcion': _desc, 'categoria': _cat, 'sub_cat': _sub}
        except Exception as _e:
            print(f'  [warning] Excel maestro: {_e}')

    # También cargar STATUS.xlsx para stock físico
    stk_by_code = {}
    for s in stk:
        cod = (s.get('codigo') or '').upper().strip()
        if cod:
            stk_by_code[cod] = s

    # ── Fallback matching (solo para items NO en Excel maestro) ──────────────
    _STOPW = {'DE','LA','EL','EN','CON','Y','A','E','O','POR','UN','UNA','LOS',
              'LAS','DEL','AL','SU','SE','LO','X','V','I','II','III','SUS'}
    _BRND  = {'TIVOLI','CYCPLUS','AIWA','ICSEE','ENERGY','SAFE','SUZUKI'}
    _COLR  = {'NEGRO','NEGRA','GRIS','BLANCO','BLANCA','AZUL','ROJO','ROJA',
              'ROSA','NARANJA','VIOLETA','AMARILLO','AMARILLA','BEIGE','INOX','VERDE','COLOR'}
    _GENR  = {'ELECTRICA','ELECTRICO','AUTOMATICO','AUTOMATICA','MANUAL','DIGITAL',
              'PORTATIL','MECANICA','MECANICO','INDUSTRIAL','PERSONAL','PREMIUM','PROFESIONAL'}

    def _norm_s(s):
        s = unicodedata.normalize('NFD', str(s).upper())
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^A-Z0-9 ]', ' ', s)

    def _mw(s):
        exc = _STOPW | _BRND | _COLR
        return {w for w in _norm_s(s).split()
                if w and w not in exc and not w.isdigit() and len(w) > 1}

    _sku_codes = [s.get('codigo','') for s in stk if s.get('codigo')]
    _sku_idx   = [(s.get('codigo',''), _mw(s.get('descripcion',''))) for s in stk if s.get('codigo')]

    def _match_fallback(title):
        tu = _norm_s(title)
        for cod in sorted(_sku_codes, key=lambda c: -len(c)):
            if re.search(r'(?<![A-Z0-9])' + re.escape(_norm_s(cod)) + r'(?![A-Z0-9])', tu):
                return cod
        tw = _mw(title)
        if not tw: return None
        best_s, best_c = 0.0, None
        for cod, sw in _sku_idx:
            if not sw: continue
            ov = tw & sw
            if not ov or not (ov - _GENR): continue
            sc = len(ov) / len(sw)
            if sc > best_s: best_s, best_c = sc, cod
        return best_c if best_s >= 0.5 else None

    def _get_sku(item_id, title):
        """Excel maestro primero; fallback semántico si no está mapeado."""
        if item_id in mla_to_sku:
            return mla_to_sku[item_id], 'master'
        fb = _match_fallback(title)
        return (fb, 'fallback') if fb else (item_id, 'unmapped')

    def _get_cat(sku_code, title_fallback):
        """Categoría desde Excel maestro / STATUS / TITLE_RULES."""
        CAT_REMAP = {'COOK': 'PEQUEÑOS ELECTRO', 'PEQUEÑO ELECTRO': 'PEQUEÑOS ELECTRO', 'LUCES': 'ILUMINACION'}
        if sku_code in cat_excel:
            cat = cat_excel[sku_code].get('categoria','') or ''
            return CAT_REMAP.get(cat, cat), cat_excel[sku_code].get('sub_cat','')
        if sku_code in stk_by_code:
            cat = stk_by_code[sku_code].get('categoria','') or ''
            return CAT_REMAP.get(cat, cat), stk_by_code[sku_code].get('sub_cat','')
        return classify_title(title_fallback), ''

    # ── SINGLE SOURCE OF TRUTH: computar TODOS los totales desde orders ──────
    orders_cur      = load_json('orders_current.json') or []
    orders_pri_data = load_json('orders_prior.json') or []

    # Computar daily_stats directamente desde orders (para reconciliación exacta)
    daily_cur_computed = {}
    daily_pri_computed = {}

    # Current period
    units_by_item = {}   # item_id → {units, gmv, title}
    dow_units_raw = [0.0] * 7

    for o in orders_cur:
        ds  = o.get('date_closed') or o.get('date_created') or ''
        st  = o.get('status', '')
        try:
            dobj = datetime.fromisoformat(ds[:19])
            day  = dobj.day
            dow  = dobj.weekday()
        except Exception:
            day, dow = 1, 0

        if day not in daily_cur_computed:
            daily_cur_computed[day] = {'gmv': 0.0, 'units': 0, 'paid': 0, 'canc': 0}

        for it in o.get('items', []):
            iid   = it.get('item_id', '?')
            qty   = it.get('quantity', 0) or 0
            price = float(it.get('unit_price', 0) or it.get('full_unit_price', 0) or 0)
            title = it.get('title', '')

            if st == 'cancelled':
                daily_cur_computed[day]['canc'] += qty
            else:
                daily_cur_computed[day]['gmv']   += qty * price
                daily_cur_computed[day]['units']  += qty
                daily_cur_computed[day]['paid']   += 1
                dow_units_raw[dow] += qty
                if iid not in units_by_item:
                    units_by_item[iid] = {'units': 0, 'gmv': 0.0, 'title': title}
                units_by_item[iid]['units'] += qty
                units_by_item[iid]['gmv']   += qty * price

    # Prior period daily
    for o in orders_pri_data:
        ds  = o.get('date_closed') or o.get('date_created') or ''
        st  = o.get('status', '')
        try:
            day = int(ds[8:10])
        except Exception:
            day = 1
        if day not in daily_pri_computed:
            daily_pri_computed[day] = {'gmv': 0.0, 'units': 0, 'paid': 0, 'canc': 0}
        for it in o.get('items', []):
            qty   = it.get('quantity', 0) or 0
            price = float(it.get('unit_price', 0) or 0)
            if st == 'cancelled':
                daily_pri_computed[day]['canc'] += qty
            else:
                daily_pri_computed[day]['gmv']   += qty * price
                daily_pri_computed[day]['units']  += qty
                daily_pri_computed[day]['paid']   += 1

    # Stringify keys for JS
    daily_cur = {str(k): {'gmv': round(v['gmv']), 'units': v['units'],
                           'paid': v['paid'], 'canc': v['canc']}
                 for k, v in daily_cur_computed.items()}
    daily_pri = {str(k): {'gmv': round(v['gmv']), 'units': v['units'],
                           'paid': v['paid'], 'canc': v['canc']}
                 for k, v in daily_pri_computed.items()}

    # Totales derivados de orders (fuente única)
    gmv_c  = round(sum(v['gmv'] for v in daily_cur_computed.values()))
    gmv_p  = round(sum(v['gmv'] for v in daily_pri_computed.values()))
    un_c   = sum(v['units'] for v in daily_cur_computed.values())
    un_p   = sum(v['units'] for v in daily_pri_computed.values())
    pd_c   = sum(v['paid']  for v in daily_cur_computed.values())
    pd_p   = sum(v['paid']  for v in daily_pri_computed.values())
    canc_c = sum(v['canc']  for v in daily_cur_computed.values())
    canc_p = sum(v['canc']  for v in daily_pri_computed.values())
    tk_c   = round(gmv_c / un_c) if un_c else 0
    tk_p   = round(gmv_p / un_p) if un_p else 0
    cr_c   = round(canc_c / (pd_c + canc_c) * 100, 2) if (pd_c + canc_c) else 0
    cr_p   = round(canc_p / (pd_p + canc_p) * 100, 2) if (pd_p + canc_p) else 0
    fees_c     = mc.get('fees', 0) or 0
    fee_rate_c = mc.get('fee_rate', 0) or 0
    fee_rate_p = mp.get('fee_rate', 0) or 0
    # Normalize: stored as percentage (19.25) → convert to decimal (0.1925)
    if fee_rate_c > 1: fee_rate_c = round(fee_rate_c / 100, 4)
    if fee_rate_p > 1: fee_rate_p = round(fee_rate_p / 100, 4)
    unique_days = mc.get('unique_days', 1) or 1

    # ── SKU-CONSOLIDATED aggregation (MASTER MAPPING FIRST) ──────────────────
    sku_agg_cur = {}   # sku_key → {id, title, categoria, sub_cat, units, gmv}
    item_to_sku = {}   # item_id → sku_key

    for iid, d in units_by_item.items():
        s_key, method = _get_sku(iid, d['title'])
        item_to_sku[iid] = s_key
        cat, sub_cat = _get_cat(s_key, d['title'])
        if s_key not in sku_agg_cur:
            sku_agg_cur[s_key] = {
                'id':        s_key,
                'title':     d['title'],
                'categoria': cat,
                'sub_cat':   sub_cat,
                'units':     0,
                'gmv':       0.0,
                'method':    method,
            }
        sku_agg_cur[s_key]['units'] += d['units']
        sku_agg_cur[s_key]['gmv']   += d['gmv']

    sku_top_items = sorted(sku_agg_cur.values(), key=lambda x: -x['gmv'])
    for x in sku_top_items:
        x['gmv'] = round(x['gmv'])

    # ── Prior period SKU aggregation ──────────────────────────────────────────
    _sku_pri = {}
    for _o in orders_pri_data:
        if _o.get('status') == 'cancelled': continue
        for _it in _o.get('items', []):
            _iid  = _it.get('item_id', '?')
            _sku, _ = _get_sku(_iid, _it.get('title',''))
            _qty  = _it.get('quantity', 0) or 0
            _g    = (_it.get('unit_price', 0) or 0) * _qty
            if _sku not in _sku_pri:
                _sku_pri[_sku] = {'gmv': 0.0, 'units': 0}
            _sku_pri[_sku]['gmv']   += _g
            _sku_pri[_sku]['units'] += _qty
    sku_top_pri = {k: {'gmv': round(v['gmv']), 'units': v['units']} for k, v in _sku_pri.items()}

    # ── Daily category breakdown (for Ventas range filter) ───────────────────
    # Build MLA→category lookup from sku_agg_cur + item_to_sku
    _iid_to_cat = {}
    for _iid_k, _sku_k in item_to_sku.items():
        _iid_to_cat[_iid_k] = sku_agg_cur.get(_sku_k, {}).get('categoria', 'OTROS')

    _daily_by_cat = {}   # day → cat → {gmv, units}
    for _o in orders_cur:
        _ds  = _o.get('date_closed') or _o.get('date_created') or ''
        _st  = _o.get('status', '')
        if _st == 'cancelled': continue
        try:
            _day = int(_ds[8:10])
        except Exception:
            _day = 0
        if not _day: continue
        for _it in _o.get('items', []):
            _iid  = _it.get('item_id','')
            _qty  = _it.get('quantity', 0) or 0
            _price = float(_it.get('unit_price', 0) or 0)
            _cat  = _iid_to_cat.get(_iid, 'OTROS')
            if _day not in _daily_by_cat:
                _daily_by_cat[_day] = {}
            if _cat not in _daily_by_cat[_day]:
                _daily_by_cat[_day][_cat] = {'gmv': 0.0, 'units': 0}
            _daily_by_cat[_day][_cat]['gmv']   += _qty * _price
            _daily_by_cat[_day][_cat]['units'] += _qty

    # Prior period daily by cat
    _daily_by_cat_pri = {}
    for _o in orders_pri_data:
        _ds  = _o.get('date_closed') or _o.get('date_created') or ''
        _st  = _o.get('status', '')
        if _st == 'cancelled': continue
        try:
            _day = int(_ds[8:10])
        except Exception:
            _day = 0
        if not _day: continue
        for _it in _o.get('items', []):
            _iid   = _it.get('item_id','')
            _qty   = _it.get('quantity', 0) or 0
            _price = float(_it.get('unit_price', 0) or 0)
            _sku_k, _ = _get_sku(_iid, _it.get('title',''))
            _cat2, _  = _get_cat(_sku_k, _it.get('title',''))
            _cat2 = _cat2 or 'OTROS'
            if _day not in _daily_by_cat_pri:
                _daily_by_cat_pri[_day] = {}
            if _cat2 not in _daily_by_cat_pri[_day]:
                _daily_by_cat_pri[_day][_cat2] = {'gmv': 0.0, 'units': 0}
            _daily_by_cat_pri[_day][_cat2]['gmv']   += _qty * _price
            _daily_by_cat_pri[_day][_cat2]['units'] += _qty

    daily_by_cat = {str(d): {c: {'gmv': round(v['gmv']), 'units': v['units']}
                              for c, v in cmap.items()}
                    for d, cmap in sorted(_daily_by_cat.items())}
    daily_by_cat_pri = {str(d): {c: {'gmv': round(v['gmv']), 'units': v['units']}
                                  for c, v in cmap.items()}
                        for d, cmap in sorted(_daily_by_cat_pri.items())}

    # ── Daily hour breakdown (for Horarios range filter) ─────────────────────
    _daily_hour = {}   # day → hour → gmv
    for _o in orders_cur:
        _ds  = _o.get('date_closed') or _o.get('date_created') or ''
        _st  = _o.get('status', '')
        if _st == 'cancelled': continue
        try:
            _day  = int(_ds[8:10])
            _hraw = int(_ds[11:13])
            _tz   = _ds[19:]  # e.g. "-04:00"
            _off  = 0
            if len(_tz) >= 6:
                _sign = 1 if _tz[0] == '+' else -1
                _off  = _sign * (int(_tz[1:3]) * 60 + int(_tz[4:6]))
            _hour = (_hraw * 60 + _off) // 60 % 24  # convert to UTC-0 local? keep local
            _hour = _hraw  # keep server hour, easier for user
        except Exception:
            continue
        if not _day: continue
        if _day not in _daily_hour: _daily_hour[_day] = {}
        if _hour not in _daily_hour[_day]: _daily_hour[_day][_hour] = 0.0
        for _it in _o.get('items', []):
            _daily_hour[_day][_hour] += (_it.get('quantity', 0) or 0) * float(_it.get('unit_price', 0) or 0)
    daily_hour = {str(d): {str(h): round(v) for h, v in hmap.items()}
                  for d, hmap in sorted(_daily_hour.items())}

    # ── Daily SKU breakdown (for Stock + TopItems range filter) ───────────────
    _daily_sku = {}   # day → sku → {gmv, units}
    for _o in orders_cur:
        _ds  = _o.get('date_closed') or _o.get('date_created') or ''
        _st  = _o.get('status', '')
        if _st == 'cancelled': continue
        try:
            _day = int(_ds[8:10])
        except Exception:
            _day = 0
        if not _day: continue
        for _it in _o.get('items', []):
            _iid   = _it.get('item_id', '')
            _qty   = _it.get('quantity', 0) or 0
            _price = float(_it.get('unit_price', 0) or 0)
            _sku_k, _ = _get_sku(_iid, _it.get('title', ''))
            if _day not in _daily_sku: _daily_sku[_day] = {}
            if _sku_k not in _daily_sku[_day]: _daily_sku[_day][_sku_k] = {'gmv': 0.0, 'units': 0}
            _daily_sku[_day][_sku_k]['gmv']   += _qty * _price
            _daily_sku[_day][_sku_k]['units'] += _qty
    daily_sku = {str(d): {s: {'gmv': round(v['gmv']), 'units': v['units']}
                           for s, v in smap.items()}
                 for d, smap in sorted(_daily_sku.items())}

    # ── Day-of-week mapping for current month ──────────────────────────────────
    from datetime import date as _date
    _yr, _mo = today.year, today.month
    day_to_dow = {str(d): _date(_yr, _mo, d).weekday()
                  for d in range(1, max_day + 1)}

    # ── Category breakdown for Ventas (with SKU drill-down) ──────────────────
    by_cat_cur = {}   # cat → {gmv, units, skus: {sku_key: {gmv, units, title, sub_cat}}}
    by_cat_pri = {}   # cat → {gmv, units}

    for s_key, agg in sku_agg_cur.items():
        cat = agg['categoria'] or 'OTROS'
        if cat not in by_cat_cur:
            by_cat_cur[cat] = {'gmv': 0, 'units': 0, 'skus': {}}
        by_cat_cur[cat]['gmv']   += agg['gmv']
        by_cat_cur[cat]['units'] += agg['units']
        by_cat_cur[cat]['skus'][s_key] = {
            'id':      s_key,
            'title':   agg['title'],
            'sub_cat': agg.get('sub_cat',''),
            'units':   agg['units'],
            'gmv':     agg['gmv'],
        }

    # Prior categories
    for _o in orders_pri_data:
        if _o.get('status') == 'cancelled': continue
        for _it in _o.get('items', []):
            _iid = _it.get('item_id','')
            _sku, _ = _get_sku(_iid, _it.get('title',''))
            _cat, _ = _get_cat(_sku, _it.get('title',''))
            _cat  = _cat or 'OTROS'
            _qty  = _it.get('quantity',0) or 0
            _g    = (_it.get('unit_price',0) or 0) * _qty
            if _cat not in by_cat_pri:
                by_cat_pri[_cat] = {'gmv': 0, 'units': 0}
            by_cat_pri[_cat]['gmv']   += round(_g)
            by_cat_pri[_cat]['units'] += _qty

    # ── SKU-consolidated cancelaciones ────────────────────────────────────────
    _sku_canc = {}
    for o in orders_cur:
        for it in o.get('items', []):
            iid   = it.get('item_id','')
            title = it.get('title','')
            s_key, _ = _get_sku(iid, title)
            cat, _   = _get_cat(s_key, title)
            qty      = it.get('quantity', 0) or 0
            st       = o.get('status','')
            if s_key not in _sku_canc:
                _sku_canc[s_key] = {'sku': s_key, 'title': title, 'categoria': cat, 'c': 0, 'p': 0}
            if st == 'cancelled': _sku_canc[s_key]['c'] += qty
            else:                 _sku_canc[s_key]['p'] += qty

    sku_cancels = []
    for d in _sku_canc.values():
        tot = d['c'] + d['p']
        d['rate'] = round(d['c'] / tot * 100, 1) if tot else 0.0
        if d['c'] > 0: sku_cancels.append(d)
    sku_cancels.sort(key=lambda x: (-x['c'], -x['rate']))

    # ── Stock table (SKU-consolidated, master mapping) ────────────────────────
    item_avail = {i['item_id']: (i.get('available_quantity') or 0) for i in items_list}
    _sku_stock = {}

    for iid, d in units_by_item.items():
        s_key, _ = _get_sku(iid, d['title'])
        cat, sub_cat = _get_cat(s_key, d['title'])
        avail_q = item_avail.get(iid, 0)

        if s_key not in _sku_stock:
            _st  = stk_by_code.get(s_key.upper(), {})
            _sku_stock[s_key] = {
                'item_id':      s_key,
                'title':        d['title'],
                'categoria':    cat,
                'sub_cat':      sub_cat,
                'codigo':       s_key if (s_key in cat_excel or s_key in stk_by_code) else '',
                'units_period': 0,
                'gmv_period':   0,
                'available_qty': 0,
                'stock_dep':    _st.get('stock_dep') if _st else None,
                'stock_full':   _st.get('stock_full') if _st else None,
                'stock_aduana': _st.get('stock_aduana') if _st else None,
                'has_status':   bool(_st),
                'dias_stock':   None,
            }
        _sku_stock[s_key]['units_period']  += d['units']
        _sku_stock[s_key]['gmv_period']    += round(d['gmv'])
        _sku_stock[s_key]['available_qty'] += avail_q

    for s_key, row in _sku_stock.items():
        dr = row['units_period'] / unique_days if unique_days else 0
        row['dias_stock'] = round(row['available_qty'] / dr) if dr > 0 and row['available_qty'] > 0 else None

    ml_items_list = sorted(_sku_stock.values(), key=lambda x: (x['categoria'], -x['gmv_period']))
    cats_ml = sorted(set(r.get('categoria','') for r in ml_items_list if r.get('categoria','')))

    # ── Other data ───────────────────────────────────────────────────────────
    dow_count   = mc.get('dow_count', [1]*7)
    dow_raw     = mc.get('dow', [0]*7)
    by_hour     = ec.get('by_hour', {})
    lt_cur      = ec.get('by_listing_type', {})
    lt_pri      = ep.get('by_listing_type', {})
    log_cur     = ec.get('by_logistic', {})
    log_pri     = ep.get('by_logistic', {})
    heatmap_data= ec.get('heatmap', [[0]*24 for _ in range(7)])
    daily_lt    = ec.get('daily_lt', {})
    daily_log   = ec.get('daily_log', {})
    daily_lt    = ec.get('daily_lt', {})
    daily_log   = ec.get('daily_log', {})

    import calendar as _cal
    _MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
              "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    _cm, _cy = today.month, today.year
    _pm, _py = (_cm - 1, _cy) if _cm > 1 else (12, _cy - 1)
    _pd = min(today.day, _cal.monthrange(_py, _pm)[1])
    period_cur = "{} {} (1-{})".format(_MESES[_cm], _cy, today.day)
    period_pri = "{} {} (1-{})".format(_MESES[_pm], _py, _pd)
    updated_at = (sm.get('updated_at','')[:16] or datetime.now().isoformat()[:16]).replace('T',' ')

    a_inv    = float(ads.get('inversion', 0) or 0)
    a_rev    = float(ads.get('ingresos', 0) or 0)
    a_impr   = float(ads.get('impresiones', 0) or 0)
    a_clics  = float(ads.get('clics', 0) or 0)
    a_ventas = float(ads.get('ventas', 0) or 0)
    a_roas   = f"{a_rev/a_inv:.2f}x" if a_inv else "—"
    a_tacos  = f"{a_inv/a_rev*100:.1f}%" if a_rev else "—"
    a_ctr    = f"{a_clics/a_impr*100:.2f}%" if a_impr else "—"
    a_cpc    = fmt_money(a_inv/a_clics) if a_clics else "—"
    a_conv   = f"{a_ventas/a_clics*100:.1f}%" if a_clics else "—"

    rep_st  = rep.get('power_seller_status', '')
    rep_lbl = {'platinum':'MercadoLíder Platinum','gold':'MercadoLíder Gold',
               'silver':'MercadoLíder Silver'}.get(rep_st, rep_st.title() if rep_st else '—')
    rep_col = {'platinum':'#00d4e4','gold':'#FFD700','silver':'#A0A0A0'}.get(rep_st, '#aaa')

    num_master  = len(mla_to_sku)
    num_skus    = len(sku_top_items)
    num_covered = sum(1 for x in sku_top_items if x.get('method') == 'master')
    pct_covered = round(sum(x['gmv'] for x in sku_top_items if x.get('method') == 'master') / max(gmv_c,1) * 100, 1)

    out_path = os.path.join(OUT_DIR, 'ml_dashboard_360.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        def w(s): f.write(s + '\n')

        # HEAD + CSS con dark/light mode
        w('<!DOCTYPE html><html lang="es" data-theme="dark">')
        w('<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">')
        w(f'<title>ML 360° · SPOTCOMPRAS · {updated_at}</title>')
        w('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>')
        f.write("""<style>
/* ── TOKENS DE COLOR ── */
[data-theme="dark"] {
  --bg:#0d0d1a; --surface:#151528; --surface2:#1a1a35; --border:#1e1e3a;
  --text:#e0e0f0; --text2:#999; --text3:#555;
  --blue:#3483FA; --yellow:#FFE600; --green:#00A650; --red:#F23D4F;
  --purple:#7B2FF7; --cyan:#00d4e4; --orange:#FF6B35;
  --kpi-bg:#151528; --nav-bg:#0d0d2e; --card-bg:#151528;
  --chart-grid:#1e1e3a; --chart-text:#666;
  --shadow:0 4px 20px rgba(0,0,0,.4);
  --transition:background .25s,color .25s,border-color .25s;
}
[data-theme="light"] {
  --bg:#f0f2f8; --surface:#ffffff; --surface2:#f7f8fc; --border:#e2e6f0;
  --text:#1a1a2e; --text2:#5a6380; --text3:#9aa0b4;
  --blue:#1a6ef5; --yellow:#d4a000; --green:#007a3c; --red:#d42b3a;
  --purple:#5b1fc8; --cyan:#0098ad; --orange:#d45000;
  --kpi-bg:#ffffff; --nav-bg:#ffffff; --card-bg:#ffffff;
  --chart-grid:#e8ecf4; --chart-text:#8892a8;
  --shadow:0 2px 12px rgba(0,0,80,.08);
  --transition:background .25s,color .25s,border-color .25s;
}
*{box-sizing:border-box;margin:0;padding:0;transition:var(--transition)}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;font-size:14px}
.nav{display:flex;gap:4px;padding:8px 12px;background:var(--nav-bg);border-bottom:1px solid var(--border);overflow-x:auto;flex-wrap:nowrap;position:sticky;top:0;z-index:100;align-items:center;box-shadow:var(--shadow)}
.nav-btn{background:var(--surface2);color:var(--text2);border:1px solid var(--border);border-radius:8px;padding:6px 12px;cursor:pointer;white-space:nowrap;font-size:13px;font-weight:500;letter-spacing:.2px}
.nav-btn:hover,.nav-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.nav-btn.active{font-weight:700}
.theme-btn{margin-left:auto;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:6px 12px;cursor:pointer;font-size:15px;line-height:1;color:var(--text2)}
.theme-btn:hover{border-color:var(--blue)}
.tab{display:none;padding:14px 16px}.tab.active{display:block}
.header{background:linear-gradient(135deg,var(--surface),var(--surface2));border-radius:12px;padding:14px 18px;margin-bottom:14px;border:1px solid var(--border);box-shadow:var(--shadow)}
.header h1{font-size:18px;font-weight:700;color:var(--blue)}
.header .meta{font-size:11px;color:var(--text3);margin-top:3px}
.badge-master{display:inline-block;background:#3483FA20;color:var(--blue);border:1px solid #3483FA44;border-radius:12px;padding:2px 8px;font-size:10px;font-weight:700;margin-top:4px}
.card{background:var(--card-bg);border-radius:12px;border:1px solid var(--border);margin-bottom:14px;overflow:hidden;box-shadow:var(--shadow)}
.card-title{padding:10px 16px;font-size:11px;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid var(--border)}
.card-body{padding:14px 16px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
.kpi{background:var(--kpi-bg);border-radius:12px;border:1px solid var(--border);padding:12px 14px;box-shadow:var(--shadow)}
.kpi-label{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.3px;margin-bottom:5px}
.kpi-val{font-size:20px;font-weight:700;color:var(--text)}
.kpi-delta{font-size:12px;margin-top:3px}.kpi-pri{font-size:11px;color:var(--text3);margin-top:2px}
.good{color:var(--green)}.bad{color:var(--red)}.neutral{color:var(--text3)}
.chart-wrap{position:relative;width:100%}
.tbl-scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{padding:8px 11px;text-align:left;font-size:11px;color:var(--text3);font-weight:600;text-transform:uppercase;border-bottom:2px solid var(--border);white-space:nowrap}
td{padding:8px 11px;border-bottom:1px solid var(--border);white-space:nowrap;color:var(--text)}
tr:hover td{background:var(--surface2)}
.cat-row{cursor:pointer;user-select:none}
.cat-row td{font-weight:700;color:var(--blue);background:var(--surface2)}
.cat-row:hover td{background:var(--border)}
.sku-row td{font-size:12px;padding-left:28px;color:var(--text2)}
.sku-row{display:none}
.sku-row.expanded{display:table-row}
.expand-icon{font-size:10px;margin-right:5px;display:inline-block;transition:transform .2s}
.slider-row{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--surface2);border-radius:8px;margin-bottom:12px;flex-wrap:wrap;border:1px solid var(--border)}
.slider-row label{font-size:12px;color:var(--text2);white-space:nowrap}
.slider-row input[type=range]{flex:1;min-width:100px;accent-color:var(--blue)}
.slider-val{font-size:14px;font-weight:700;color:var(--yellow);white-space:nowrap;min-width:90px}
[data-theme="light"] .slider-val{color:var(--blue)}
.pct-row{display:flex;align-items:center;gap:8px;margin-bottom:9px}
.pct-lbl{font-size:12px;color:var(--text);min-width:130px;flex-shrink:0}
.pct-track{flex:1;background:var(--surface2);border-radius:4px;height:11px;overflow:hidden;border:1px solid var(--border)}
.pct-fill{height:100%;border-radius:4px}
.pct-num{font-size:12px;color:var(--text2);min-width:100px;text-align:right;flex-shrink:0}
.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:700}
.b-ok{background:#00A65018;color:var(--green)}.b-low{background:#FFE60018;color:var(--yellow)}.b-zero{background:#F23D4F18;color:var(--red)}
[data-theme="light"] .b-ok{background:#00A65015}.b-low{background:#d4a00015}.b-zero{background:#d42b3a15}
.rep-metric{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border)}
.rep-metric:last-child{border-bottom:none}
.rep-lbl{font-size:12px;color:var(--text2)}.rep-val{font-size:13px;font-weight:700}
.ads-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.ads-kpi{background:var(--surface2);border-radius:10px;padding:12px;text-align:center;border:1px solid var(--border)}
.ads-kpi .lbl{font-size:11px;color:var(--text3);margin-bottom:6px}
.ads-kpi .val{font-size:20px;font-weight:700}
.recon-ok{background:#00A65012;color:var(--green);border:1px solid #00A65030;border-radius:8px;padding:8px 14px;font-size:12px;margin-bottom:10px}
.recon-warn{background:#F23D4F12;color:var(--red);border:1px solid #F23D4F30;border-radius:8px;padding:8px 14px;font-size:12px;margin-bottom:10px}
@media(max-width:900px){.kpi-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.kpi-grid{grid-template-columns:repeat(2,1fr)}.kpi-val{font-size:17px}.header h1{font-size:15px}}
@media(max-width:400px){.nav-btn{padding:5px 8px;font-size:11px}}
</style></head>""")

        w('<body>')
        w('<div class="nav">')
        for idx, lbl in enumerate(['📊 Resumen','📈 Ventas','🕐 Horarios','📦 Stock',
                                    '❌ Cancelaciones','🏅 Reputación','⚡ Ads','🏆 Top Items','📅 Anual']):
            ac = ' active' if idx == 0 else ''
            w(f'<button class="nav-btn{ac}" onclick="showTab({idx})">{lbl}</button>')
        w('<button class="theme-btn" onclick="toggleTheme()" id="theme-icon" title="Cambiar tema">☾</button>')
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
        w(f'const HEATMAP={jd(heatmap_data)};')
        w(f'const BY_CAT_CUR={jd(by_cat_cur)};')
        w(f'const BY_CAT_PRI={jd(by_cat_pri)};')
        w(f'const DAILY_BY_CAT={jd(daily_by_cat)};')
        w(f'const DAILY_BY_CAT_PRI={jd(daily_by_cat_pri)};')
        w(f'const DAILY_HOUR={jd(daily_hour)};')
        w(f'const DAILY_SKU={jd(daily_sku)};')
        w(f'const DAY_TO_DOW={jd(day_to_dow)};')
        w(f'const LT_CUR={jd(lt_cur)};')
        w(f'const LT_PRI={jd(lt_pri)};')
        w(f'const LOG_CUR={jd(log_cur)};')
        w(f'const LOG_PRI={jd(log_pri)};')
        w(f'const DAILY_LT={jd(daily_lt)};')
        w(f'const DAILY_LOG={jd(daily_log)};')
        w(f'const MONTHLY={jd(mon)};')
        w(f'const ML_ITEMS_DATA={jd(ml_items_list)};')
        w(f'const TOP_ITEMS={jd(sku_top_items)};')
        w(f'const TOP_ITEMS_PRI={jd(sku_top_pri)};')
        # SINGLE SOURCE OF TRUTH — totales derivados de orders_current.json
        w(f'const GMV_CUR={gmv_c};')
        w(f'const GMV_PRI={gmv_p};')
        w(f'const UNITS_CUR={un_c};')
        w(f'const UNITS_PRI={un_p};')
        w(f'const PAID_CUR={pd_c};')
        w(f'const PAID_PRI={pd_p};')
        w(f'const CANC_CUR={canc_c};')
        w(f'const CANC_PRI={canc_p};')
        w(f'const TK_CUR={tk_c};')
        w(f'const TK_PRI={tk_p};')
        w(f'const CR_CUR={cr_c};')
        w(f'const CR_PRI={cr_p};')
        w(f'const FEE_RATE_C={fee_rate_c};')
        w(f'const FEE_RATE_P={fee_rate_p};')
        w(f'const MAX_DAY={max_day};')
        w(f'const PERIOD_CUR={jd(period_cur)};')
        w(f'const PERIOD_PRI={jd(period_pri)};')
        w('</script>')

        # ── GLOBAL PERIOD BAR (visible en todos los tabs) ───────────────────
        w('<div class="period-bar">')
        w('<div class="period-presets">')
        w('<span class="period-custom-lbl">Per&iacute;odo</span>')
        w(f'<button class="period-chip active" id="chip-mes" onclick="setRange(1,{max_day})">Mes completo</button>')
        w('<button class="period-chip" id="chip-s1" onclick="setRange(1,7)">Sem 1</button>')
        w('<button class="period-chip" id="chip-s2" onclick="setRange(8,14)">Sem 2</button>')
        w(f'<button class="period-chip" id="chip-s3" onclick="setRange(15,{max_day})">Sem 3</button>')
        w('<button class="period-chip hot" id="chip-hot" onclick="setRange(11,17)">Hot Sale</button>')
        w('</div>')
        w('<div class="period-divider"></div>')
        w('<div class="period-custom">')
        w('<span class="period-custom-lbl">Rango</span>')
        w(f'<input type="number" class="period-input" id="day-from" min="1" max="{max_day}" value="1" oninput="applyRange()">')
        w('<span class="period-sep">&#8211;</span>')
        w(f'<input type="number" class="period-input" id="day-to" min="1" max="{max_day}" value="{max_day}" oninput="applyRange()">')
        w(f'<span class="period-info" id="range-lbl">1–{max_day} ({max_day} d&iacute;as)</span>')
        w('</div>')
        w('</div>')

        # ── TAB 0: RESUMEN ───────────────────────────────────────────────────
        w('<div id="tab0" class="tab active">')
        w(f'<div class="header"><h1>📊 Dashboard ML 360° · SPOTCOMPRAS</h1>')
        w(f'<div class="meta">Actualizado: {updated_at} &nbsp;|&nbsp; {period_cur} vs {period_pri}</div>')
        w('</div>')
        w('<div class="kpi-grid" id="kpi-grid"></div>')
        w('<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">')
        w('<div class="card"><div class="card-title">Tipo de publicación</div>')
        w('<div class="card-body" id="lt-section"></div></div>')
        w('<div class="card"><div class="card-title">Tipo de envío</div>')
        w('<div class="card-body" id="log-section"></div></div>')
        w('</div>')
        w('<div class="card"><div class="card-title">GMV diario · mes actual vs anterior</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:200px">')
        w('<canvas id="c-daily"></canvas></div></div></div>')
        w('</div>')

        # ── TAB 1: VENTAS con drill-down por SKU ─────────────────────────────
        w('<div id="tab1" class="tab">')
        w(f'<div class="header"><h1>📈 Ventas por Categoría → SKU</h1><div class="meta">{period_cur} vs {period_pri} · Click en categoría para expandir SKUs</div></div>')
        w('<div class="card"><div class="card-body tbl-scroll">')
        w('<table id="ventas-table"><thead><tr>')
        w('<th>Categoría / SKU</th><th>GMV</th><th>Unidades</th><th>Ticket Prom.</th><th>% GMV</th><th>vs Ant.</th></tr></thead>')
        w('<tbody id="cat-tbody"></tbody></table></div></div>')
        w('</div>')

        # ── TAB 2: HORARIOS ──────────────────────────────────────────────────
        w('<div id="tab2" class="tab">')
        w(f'<div class="header"><h1>🕐 Horarios</h1><div class="meta">{period_cur} · {unique_days} días activos</div></div>')
        w('<div class="card"><div class="card-title">Promedio GMV por hora del día</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:240px"><canvas id="c-hour"></canvas></div></div></div>')
        w('<div class="card"><div class="card-title">Promedio por día de semana</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:240px"><canvas id="c-dow"></canvas></div></div></div>')
        w('<div class="card"><div class="card-title">Heatmap GMV · día × hora</div>')
        w('<div class="card-body" id="heatmap-wrap" style="overflow-x:auto"></div></div>')
        w('<div class="card" style="border-left:3px solid var(--yellow)"><div class="card-title">Insights</div>')
        w('<div class="card-body" id="hora-insights" style="font-size:12px;line-height:2"></div></div>')
        w('</div>')

        # ── TAB 3: STOCK ─────────────────────────────────────────────────────
        w('<div id="tab3" class="tab">')
        w(f'<div class="header"><h1>📦 Stock por SKU</h1>')
        w(f'<div class="meta">{len(ml_items_list)} SKUs consolidados · {num_master} mapeados vía archivo maestro</div></div>')
        w('<div id="stock-summary" class="kpi-grid"></div>')
        w('<div class="slider-row">')
        w('<label>Categoría:</label>')
        w('<select id="stk-cat-filter" onchange="renderStock()" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px">')
        w('<option value="">Todas</option>')
        for c in cats_ml:
            w(f'<option value="{c}">{c}</option>')
        w('</select>')
        w('<label style="margin-left:8px">Cobertura:</label>')
        w('<select id="stk-show-filter" onchange="renderStock()" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px">')
        w('<option value="all">Todos</option><option value="zero">Sin stock</option>')
        w('<option value="low">Bajo (&lt;10)</option><option value="critical">&lt;7 días</option>')
        w('</select></div>')
        w('<div class="card"><div class="card-title">SKU · ventas período · stock · cobertura</div>')
        w('<div class="card-body tbl-scroll">')
        w('<table><thead><tr><th>SKU</th><th>Descripción</th><th>Categoría</th>')
        w('<th>Vtas</th><th>GMV</th><th>Stock ML</th><th>Cobertura</th><th>Dep.</th><th>Full</th><th>Aduana</th></tr></thead>')
        w('<tbody id="stock-tbody"></tbody></table></div></div></div>')

        # ── TAB 4: CANCELACIONES ─────────────────────────────────────────────
        w('<div id="tab4" class="tab">')
        w(f'<div class="header"><h1>❌ Cancelaciones por SKU</h1><div class="meta">{period_cur} vs {period_pri}</div></div>')
        w('<div class="kpi-grid" id="canc-kpi-grid">')
        ar, ac_col = arrow(delta_pct(cr_c, cr_p), inv=True)
        w(f'<div class="kpi"><div class="kpi-label">Tasa cancelación</div><div class="kpi-val">{cr_c:.1f}%</div><div class="kpi-delta {ac_col}">{ar}</div><div class="kpi-pri">Ant: {cr_p:.1f}%</div></div>')
        w(f'<div class="kpi"><div class="kpi-label">Unidades canceladas</div><div class="kpi-val" style="color:var(--red)">{canc_c:,}</div><div class="kpi-pri">Ant: {canc_p:,}</div></div>')
        w(f'<div class="kpi"><div class="kpi-label">Órdenes pagadas</div><div class="kpi-val" style="color:var(--green)">{pd_c:,}</div><div class="kpi-pri">Ant: {pd_p:,}</div></div>')
        gmv_perdido = canc_c * tk_c
        w(f'<div class="kpi"><div class="kpi-label">GMV perdido est.</div><div class="kpi-val" style="color:var(--red)">{fmt_money(gmv_perdido)}</div><div class="kpi-pri">Ticket prom: {fmt_money(tk_c)}</div></div>')
        w('</div>')
        w('<div class="card"><div class="card-title">Cancelaciones diarias</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:200px"><canvas id="c-canc-daily"></canvas></div></div></div>')
        top_cancel_rate = max((cx.get('rate',0) for cx in sku_cancels[:5]), default=0)
        w('<div class="card" style="border-left:3px solid var(--yellow)"><div class="card-title">Insights automáticos</div><div class="card-body" style="font-size:12px;line-height:1.9">')
        if cr_c > 5:
            w(f'<div>⚠️ Tasa {cr_c:.1f}% por encima del umbral saludable (5%). Revisar causas por SKU.</div>')
        if top_cancel_rate > 15:
            w(f'<div>⚠️ Hay SKUs con tasa &gt;{int(top_cancel_rate)}% — revisar stock publicado vs real.</div>')
        dp2 = delta_pct(cr_c, cr_p)
        if dp2 and dp2 > 20:
            ar_c, _ = arrow(dp2)
            w(f'<div>📈 Tasa subió {ar_c} vs período anterior.</div>')
        if cr_c <= 3:
            w(f'<div style="color:var(--green)">✅ Tasa {cr_c:.1f}% dentro del rango óptimo para MercadoLíder.</div>')
        w(f'<div style="color:var(--text3);font-size:11px;margin-top:8px">ℹ️ Devoluciones y reclamos requieren consulta adicional a la API de ML. Los datos actuales corresponden a cancelaciones antes de despacho.</div>')
        w('</div></div>')
        w('<div class="card"><div class="card-title">SKUs con más cancelaciones</div>')
        w('<div class="card-body tbl-scroll"><table><thead><tr>')
        w('<th>#</th><th>SKU</th><th>Categoría</th><th>Canceladas</th><th>Pagadas</th><th>Tasa</th><th>Riesgo</th></tr></thead><tbody>')
        for i, cx in enumerate(sku_cancels[:25], 1):
            rate   = cx.get('rate', 0)
            col    = 'bad' if rate > 10 else ('neutral' if rate > 5 else 'good')
            riesgo = '🔴 Alto' if rate > 10 else ('🟡 Medio' if rate > 5 else '🟢 OK')
            s_key  = cx.get('sku','')
            disp   = s_key if (not s_key.isdigit() and len(s_key) < 20) else cx.get('title','')[:28]
            w(f'<tr><td style="color:var(--text3)">{i}</td>'
              f'<td style="font-weight:700;color:var(--cyan);font-size:12px">{disp}</td>'
              f'<td style="color:var(--text2);font-size:11px">{cx.get("categoria","")}</td>'
              f'<td style="color:var(--red);font-weight:700">{cx.get("c",0)}</td>'
              f'<td>{cx.get("p",0)}</td><td class="{col}">{rate:.1f}%</td><td>{riesgo}</td></tr>')
        w('</tbody></table></div></div></div>')

        # ── TAB 5: REPUTACIÓN ────────────────────────────────────────────────
        claims_pct  = (rep.get('claims_rate', 0) or 0) * 100
        delayed_pct = (rep.get('delayed_rate', 0) or 0) * 100
        canc_rep    = (rep.get('cancellations_rate', 0) or 0) * 100
        sales60     = rep.get('sales_60d', 0) or 0
        rat_pos     = (rep.get('ratings_positive', 0) or 0) * 100
        rat_neg     = (rep.get('ratings_negative', 0) or 0) * 100
        total_ord   = rep.get('total', 0) or 0
        completed   = rep.get('completed', 0) or 0
        canceled_h  = rep.get('canceled', 0) or 0
        w('<div id="tab5" class="tab">')
        w(f'<div class="header"><h1>🏅 Reputación</h1><div class="meta">Datos al {updated_at}</div></div>')
        w(f'<div class="card" style="border-left:4px solid {rep_col}"><div class="card-body">')
        w(f'<div style="font-size:24px;font-weight:700;color:{rep_col};margin-bottom:6px">{rep_lbl}</div>')
        w(f'<div style="font-size:13px;color:var(--text2)">Usuario: {rep.get("nickname","—")} &nbsp;|&nbsp; Nivel: {rep.get("level_id","—")}</div>')
        w('</div></div>')
        w('<div class="kpi-grid">')
        for lbl, val, col in [
            ('Ventas 60 días',   f'{sales60:,}',   'var(--text)'),
            ('Total histórico',  f'{total_ord:,}',  'var(--text)'),
            ('Completadas',      f'{completed:,}',  'var(--green)'),
            ('Canceladas hist.', f'{canceled_h:,}', 'var(--red)'),
        ]:
            w(f'<div class="kpi"><div class="kpi-label">{lbl}</div><div class="kpi-val" style="color:{col}">{val}</div></div>')
        w('</div>')
        w('<div class="card"><div class="card-title">Métricas de calidad · últimos 60 días</div><div class="card-body">')
        for lbl, val, warn_t, bad_t in [
            ('Reclamos',      claims_pct,  1.0, 2.0),
            ('Envíos tardíos',delayed_pct, 6.0, 10.0),
            ('Cancelaciones', canc_rep,    0.5, 1.5),
        ]:
            col  = 'var(--red)' if val > bad_t else ('var(--yellow)' if val > warn_t else 'var(--green)')
            desc = '🔴 Crítico' if val > bad_t else ('🟡 Atención' if val > warn_t else '🟢 OK')
            w(f'<div class="rep-metric">'
              f'<span class="rep-lbl">{lbl} <span style="font-size:10px;color:var(--text3)">(alerta {warn_t}% / crítico {bad_t}%)</span></span>'
              f'<span><span class="rep-val" style="color:{col}">{val:.2f}%</span> '
              f'<span style="font-size:11px;color:{col}">{desc}</span></span></div>')
        w(f'<div class="rep-metric"><span class="rep-lbl">Calificaciones positivas</span><span class="rep-val" style="color:var(--green)">{rat_pos:.1f}%</span></div>')
        w(f'<div class="rep-metric"><span class="rep-lbl">Calificaciones negativas</span><span class="rep-val" style="color:var(--red)">{rat_neg:.1f}%</span></div>')
        w('</div></div>')
        issues = []
        if claims_pct > 2.0:   issues.append(f'🔴 Reclamos {claims_pct:.2f}% — supera límite ML. Revisar motivos y responder abiertos.')
        if delayed_pct > 10.0: issues.append(f'🔴 Tardíos {delayed_pct:.2f}% — impacto directo en MercadoLíder.')
        if canc_rep > 1.5:     issues.append(f'🟡 Cancelaciones hist. {canc_rep:.3f}% — revisar SKUs críticos.')
        if rat_neg > 5:        issues.append(f'🔴 Calificaciones negativas {rat_neg:.1f}% — revisar publicaciones problemáticas.')
        if not issues:
            issues.append(f'✅ Todos los indicadores dentro de umbrales. Nivel <b style="color:{rep_col}">{rep_lbl}</b> estable.')
        w(f'<div class="card" style="border-left:3px solid var(--cyan)"><div class="card-title">Diagnóstico ejecutivo</div>')
        w('<div class="card-body" style="font-size:12px;line-height:2">')
        for msg in issues: w(f'<div>{msg}</div>')
        w('</div></div>')
        w('<div class="card"><div class="card-title">SKUs con mayor riesgo reputacional</div>')
        w('<div class="card-body tbl-scroll"><table><thead><tr><th>SKU</th><th>Categoría</th><th>Tasa cancel.</th><th>Canceladas</th><th>Riesgo</th></tr></thead><tbody>')
        for cx in sorted(sku_cancels[:15], key=lambda x: -x.get('rate',0))[:10]:
            rate  = cx.get('rate',0)
            col2  = 'var(--red)' if rate > 10 else ('var(--yellow)' if rate > 5 else 'var(--green)')
            risk  = '🔴 Alto' if rate > 10 else ('🟡 Monitorear' if rate > 5 else '🟢 Estable')
            s_key = cx.get('sku','')
            disp  = s_key if (not s_key.isdigit() and len(s_key) < 20) else cx.get('title','')[:28]
            w(f'<tr><td style="font-weight:700;color:var(--cyan)">{disp}</td>'
              f'<td style="color:var(--text2);font-size:11px">{cx.get("categoria","")}</td>'
              f'<td style="color:{col2};font-weight:700">{rate:.1f}%</td>'
              f'<td style="color:var(--red)">{cx.get("c",0)}</td><td style="color:{col2}">{risk}</td></tr>')
        w('</tbody></table></div></div>')
        w('</div>')

        # ── TAB 6: ADS ───────────────────────────────────────────────────────
        ads_per = ads.get('periodo','') or ads.get('fecha','') or period_cur
        w('<div id="tab6" class="tab">')
        w(f'<div class="header"><h1>⚡ Ads & Costos</h1><div class="meta">Período: {ads_per}</div></div>')
        w('<div class="card"><div class="card-title">KPIs Ads</div><div class="card-body"><div class="ads-grid">')
        for lbl, val, col in [
            ('Inversión',    fmt_money(a_inv),  'var(--purple)'),
            ('Ingresos ads', fmt_money(a_rev),  'var(--green)'),
            ('ROAS',         a_roas,             'var(--green)'),
            ('TACOS',        a_tacos,            'var(--yellow)'),
            ('CTR',          a_ctr,              'var(--blue)'),
            ('CPC',          a_cpc,              'var(--cyan)'),
            ('Conv. rate',   a_conv,             'var(--green)'),
            ('Comisiones',   fmt_money(fees_c),  'var(--red)'),
        ]:
            w(f'<div class="ads-kpi"><div class="lbl">{lbl}</div><div class="val" style="color:{col}">{val}</div></div>')
        w('</div></div></div>')
        w('<div class="card"><div class="card-title">Tráfico</div><div class="card-body"><div class="ads-grid">')
        for lbl, val, col in [
            ('Impresiones', f'{int(a_impr):,}',   'var(--blue)'),
            ('Clics',       f'{int(a_clics):,}',  'var(--cyan)'),
            ('Ventas ads',  f'{int(a_ventas):,}', 'var(--green)'),
            ('GMV total',   fmt_money(gmv_c),     'var(--text)'),
        ]:
            w(f'<div class="ads-kpi"><div class="lbl">{lbl}</div><div class="val" style="color:{col}">{val}</div></div>')
        w('</div></div></div>')
        w('<div class="card"><div class="card-title">Distribución de costos</div><div class="card-body">')
        gmv_f   = float(gmv_c) or 1
        c_comis = float(costs.get('comisiones') or fees_c)
        c_env   = float(costs.get('envios') or 0)
        c_ret   = float(costs.get('retenciones') or 0) + float(costs.get('percepciones') or 0)
        neto_r  = max(0, float(gmv_c) - c_comis - a_inv - c_env - c_ret)
        for lbl, val, col in [
            ('Comisiones ML',  c_comis, 'var(--red)'),
            ('Inversión Ads',  a_inv,   'var(--purple)'),
            ('Envíos',         c_env,   'var(--cyan)'),
            ('Ret. / Percep.', c_ret,   'var(--yellow)'),
            ('Neto estimado',  neto_r,  'var(--green)'),
        ]:
            pct = val / gmv_f * 100
            w(f'<div class="pct-row"><span class="pct-lbl">{lbl}</span>'
              f'<div class="pct-track"><div class="pct-fill" style="width:{min(100,int(pct))}%;background:{col}"></div></div>'
              f'<span class="pct-num" style="color:{col}">{fmt_money(val)} ({pct:.1f}%)</span></div>')
        w('</div></div>')
        if not a_inv:
            w('<div class="card" style="border-left:3px solid var(--border)"><div class="card-body" style="color:var(--text3);font-size:13px">')
            w('No hay datos de Ads disponibles para el período seleccionado.</div></div>')
        w('</div>')

        # ── TAB 7: TOP ITEMS ─────────────────────────────────────────────────
        w('<div id="tab7" class="tab">')
        w(f'<div class="header"><h1>🏆 Top Productos · SKU Consolidado</h1>')
        w(f'<div class="meta">{period_cur} · {num_skus} SKUs únicos · fuente: orders_current.json</div></div>')
        w('<div class="slider-row">')
        w('<label>Ordenar por:</label>')
        w('<select id="top-sort" onchange="renderTopItems()" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px">')
        w('<option value="gmv">GMV</option><option value="units">Unidades</option></select>')
        w('<label style="margin-left:10px">Categoría:</label>')
        w('<select id="top-cat-filter" onchange="renderTopItems()" style="background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:4px 8px">')
        w('<option value="">Todas</option>')
        for c in cats_ml:
            w(f'<option value="{c}">{c}</option>')
        w('</select></div>')
        w('<div class="kpi-grid" id="top-kpis"></div>')
        w('<div class="card"><div class="card-body tbl-scroll">')
        w('<table><thead><tr><th>#</th><th>SKU</th><th>Categoría</th><th>GMV</th>')
        w('<th>% GMV</th><th>Unidades</th><th>% Units</th><th>vs Ant. GMV</th><th>vs Ant. Units</th></tr></thead>')
        w('<tbody id="top-tbody"></tbody></table></div></div></div>')

        # ── TAB 8: ANUAL ─────────────────────────────────────────────────────
        w('<div id="tab8" class="tab">')
        total_gmv_y   = sum(m.get('gmv',0) for m in mon if m.get('complete'))
        total_units_y = sum(m.get('units',0) for m in mon if m.get('complete'))
        best_m     = max((m for m in mon if m.get('complete')), key=lambda m: m.get('gmv',0), default={})
        months_done = sum(1 for m in mon if m.get('complete'))
        avg_monthly = total_gmv_y / months_done if months_done else 0
        cur_m       = next((m for m in mon if not m.get('complete')), None)
        # Inject current period GMV if monthly data doesn't include it
        if not cur_m and gmv_c > 0:
            cur_m = {'label': today.strftime('%b %Y'), 'gmv': gmv_c, 'units': un_c,
                     'paid': pd_c, 'cancelled': canc_c,
                     'cancel_rate': cr_c, 'avg_ticket': tk_c, 'complete': False}
            mon = list(mon) + [cur_m]
        elif cur_m and cur_m.get('gmv', 0) == 0 and gmv_c > 0:
            cur_m['gmv'] = gmv_c; cur_m['units'] = un_c
            cur_m['paid'] = pd_c; cur_m['cancelled'] = canc_c
            cur_m['cancel_rate'] = cr_c; cur_m['avg_ticket'] = tk_c
        cur_daily_r = (cur_m.get('gmv',0) / today.day) if cur_m and today.day else 0
        cur_proj30  = cur_daily_r * 30
        proj_year   = total_gmv_y + (cur_m.get('gmv',0) if cur_m else 0) + max(0, 11 - months_done) * avg_monthly
        w(f'<div class="header"><h1>📅 Evolución Anual {today.year}</h1><div class="meta">{months_done} meses cerrados + mes en curso</div></div>')
        w('<div class="kpi-grid">')
        for lbl, val, col, sub in [
            ('GMV acumulado',   fmt_money(total_gmv_y),  'var(--text)',   f'{months_done} meses cerrados'),
            ('Promedio mensual',fmt_money(avg_monthly),   'var(--blue)',   ''),
            ('Mejor mes',       best_m.get('label','—') if best_m else '—', 'var(--yellow)', fmt_money(best_m.get('gmv',0)) if best_m else '—'),
            ('Proyección anual',fmt_money(proj_year),     'var(--green)',  f'Pace: {fmt_money(cur_daily_r)}/día'),
            ('Unidades acum.',  f'{total_units_y:,}',     'var(--text)',   ''),
            ('Mes actual proj.',fmt_money(cur_proj30),    'var(--cyan)',   f'Actual: {fmt_money(cur_m.get("gmv",0) if cur_m else 0)}'),
        ]:
            w(f'<div class="kpi"><div class="kpi-label">{lbl}</div><div class="kpi-val" style="color:{col}">{val}</div>'
              + (f'<div class="kpi-pri">{sub}</div>' if sub else '') + '</div>')
        w('</div>')
        w('<div class="card"><div class="card-title">GMV mensual · evolución y ticket promedio</div>')
        w('<div class="card-body"><div class="chart-wrap" style="height:280px"><canvas id="c-anual"></canvas></div></div></div>')
        w('<div class="card"><div class="card-title">Detalle mensual</div><div class="card-body tbl-scroll">')
        w('<table><thead><tr><th>Mes</th><th>GMV</th><th>MoM</th><th>Unidades</th><th>Pagadas</th><th>Canceladas</th><th>Tasa Canc.</th><th>Ticket</th><th>Acumulado</th></tr></thead><tbody>')
        running_total = 0.0
        for mi, m in enumerate(mon):
            gmv_m = m.get('gmv',0)
            running_total += gmv_m
            prev_g = mon[mi-1].get('gmv',0) if mi > 0 else 0
            d_pct  = delta_pct(gmv_m, prev_g)
            ar_m, ar_col = arrow(d_pct)
            is_cur = not m.get('complete')
            cr_row = m.get('cancel_rate',0)
            w(f'<tr style="{"background:var(--surface2)" if is_cur else ""}">'
              f'<td style="font-weight:700;color:var(--blue)">{m.get("label","")}{" ●" if is_cur else ""}</td>'
              f'<td style="font-weight:700">{fmt_money(gmv_m)}</td>'
              f'<td class="{ar_col}">{ar_m}</td>'
              f'<td>{m.get("units",0):,}</td>'
              f'<td style="color:var(--green)">{m.get("paid",0):,}</td>'
              f'<td style="color:var(--red)">{m.get("cancelled",0):,}</td>'
              f'<td class="{"bad" if cr_row>5 else "good"}">{cr_row:.1f}%</td>'
              f'<td>{fmt_money(m.get("avg_ticket",0))}</td>'
              f'<td style="color:var(--text3)">{fmt_money(running_total)}</td></tr>')
        w('</tbody></table></div></div></div>')

        # Extra CSS for JS-rendered elements
        w('<style>')
        w(".badge-share{display:inline-block;background:#3483FA20;color:var(--blue);border:1px solid #3483FA44;border-radius:10px;padding:1px 6px;font-size:11px;font-weight:700} .badge-sku{display:inline-block;background:#00d4e418;color:var(--cyan);border:1px solid #00d4e433;border-radius:10px;padding:1px 6px;font-size:11px} .cat-toggle{display:inline-block;width:16px;margin-right:4px;font-size:11px} .sku-row td{background:var(--surface2)!important;font-size:12px;border-bottom:1px solid var(--border)} .heatmap-tbl{border-collapse:collapse;font-size:10px;width:100%} .heatmap-tbl th{color:var(--text3);padding:2px 3px;text-align:center;font-weight:500} .heatmap-lbl{color:var(--text2);font-weight:700;padding:2px 6px;white-space:nowrap} .hm-cell{width:3.8%;text-align:center;padding:3px 1px;border-radius:3px;cursor:default;font-size:9px} .period-bar{display:flex;align-items:center;gap:0;background:var(--surface);border:1px solid var(--border);border-radius:12px;margin-bottom:14px;box-shadow:var(--shadow);overflow:hidden;flex-wrap:wrap} .period-presets{display:flex;align-items:center;gap:6px;padding:10px 14px;flex-wrap:wrap} .period-divider{width:1px;min-height:40px;background:var(--border);flex-shrink:0} .period-custom{display:flex;align-items:center;gap:8px;padding:10px 14px} .period-custom-lbl{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.5px;white-space:nowrap;font-weight:600} .period-chip{height:30px;padding:0 13px;border-radius:20px;border:1px solid var(--border);background:transparent;color:var(--text2);font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;line-height:28px;transition:all .15s ease;font-family:inherit} .period-chip:hover{border-color:var(--blue);color:var(--blue);background:#3483FA10} .period-chip.active{background:var(--blue);color:#fff;border-color:var(--blue);box-shadow:0 2px 8px #3483FA44} .period-chip.hot{border-color:#FF6B3566;color:var(--orange)} .period-chip.hot:hover{background:#FF6B3510} .period-chip.hot.active{background:var(--orange);color:#fff;border-color:var(--orange);box-shadow:0 2px 8px rgba(255,107,53,.35)} .period-input{width:46px;height:30px;padding:0 6px;border:1px solid var(--border);border-radius:8px;background:var(--surface2);color:var(--text);font-size:13px;font-weight:700;text-align:center;-moz-appearance:textfield;appearance:textfield;font-family:inherit} .period-input::-webkit-inner-spin-button,.period-input::-webkit-outer-spin-button{-webkit-appearance:none} .period-input:focus{outline:none;border-color:var(--blue);box-shadow:0 0 0 3px #3483FA22} .period-sep{color:var(--text3);font-size:15px;font-weight:300;padding:0 2px} .period-info{font-size:12px;font-weight:700;color:var(--blue);background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:5px 11px;white-space:nowrap;min-width:90px;text-align:center}")
        w('</style>')

        # Chart.js CDN
        w('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>')

        # Main JS block
        w('<script>')
        w("(function(){")
        w("  var t=localStorage.getItem(\"sp-theme\")||\"dark\";")
        w("  document.documentElement.setAttribute(\"data-theme\",t);")
        w("  var btn=document.getElementById(\"theme-icon\");")
        w("  if(btn)btn.textContent=t===\"dark\"?\"\u2600\":\"\u263e\";")
        w("})();")
        w("")
        w("function toggleTheme(){")
        w("  var cur=document.documentElement.getAttribute(\"data-theme\");")
        w("  var next=cur===\"dark\"?\"light\":\"dark\";")
        w("  document.documentElement.setAttribute(\"data-theme\",next);")
        w("  localStorage.setItem(\"sp-theme\",next);")
        w("  var btn=document.getElementById(\"theme-icon\");")
        w("  if(btn)btn.textContent=next===\"dark\"?\"\u2600\":\"\u263e\";")
        w("  Object.keys(_charts).forEach(function(k){if(_charts[k]){_charts[k].destroy();_charts[k]=null;}});")
        w("  _initTab(_activeTab);")
        w("}")
        w("")
        w("var _activeTab=0;")
        w("var _charts={};")
        w("")
        w("function showTab(n){")
        w("  document.querySelectorAll(\".tab\").forEach(function(t,i){t.classList.toggle(\"active\",i===n);});")
        w("  document.querySelectorAll(\".nav-btn\").forEach(function(b,i){b.classList.toggle(\"active\",i===n);});")
        w("  _activeTab=n;")
        w("  _initTab(n);")
        w("}")
        w("")
        w("function _rng(){var fe=document.getElementById('day-from'),te=document.getElementById('day-to');return[parseInt((fe||{}).value)||1,parseInt((te||{}).value)||MAX_DAY];}")
        w("function _initTab(n){")
        w("  var r=_rng(),f=r[0],t=r[1];")
        w("  if(n===0)applyRange();")
        w("  if(n===1)renderVentas(f,t);")
        w("  if(n===2)renderHorarios(f,t);")
        w("  if(n===3)renderStock(f,t);")
        w("  if(n===4)renderCancChart(f,t);")
        w("  if(n===7)renderTopItems(f,t);")
        w("  if(n===8)renderAnual();")
        w("}")
        w("")
        w("function fmtM(n){")
        w("  n=Math.round(n||0);")
        w("  if(n>=1e9)return\"$\"+(n/1e9).toFixed(2)+\"B\";")
        w("  if(n>=1e6)return\"$\"+(n/1e6).toFixed(2)+\"M\";")
        w("  if(n>=1e3)return\"$\"+(n/1e3).toFixed(1)+\"K\";")
        w("  return\"$\"+n.toLocaleString(\"es-AR\");")
        w("}")
        w("function fmtN(n){return(n||0).toLocaleString(\"es-AR\");}")
        w("function dPct(a,b){return(b&&b!==0)?((a-b)/Math.abs(b))*100:null;}")
        w("function arrH(pct,inv){")
        w("  if(pct===null||pct===undefined)return'<span style=\"color:var(--text3)\">&#8212;</span>';")
        w("  var pos=inv?(pct<0):(pct>0);")
        w("  var col=pos?\"var(--green)\":\"var(--red)\";")
        w("  var sym=pct>0?\"&#9650;\":\"&#9660;\";")
        w("  return'<span style=\"color:'+col+'\">'+sym+\" \"+Math.abs(pct).toFixed(1)+\"%</span>\";")
        w("}")
        w("function cssV(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim();}")
        w("function cc(){return{")
        w("  blue:cssV(\"--blue\"),green:cssV(\"--green\"),red:cssV(\"--red\"),yellow:cssV(\"--yellow\"),")
        w("  cyan:cssV(\"--cyan\"),purple:cssV(\"--purple\"),text:cssV(\"--text\"),text2:cssV(\"--text2\"),")
        w("  text3:cssV(\"--text3\"),grid:cssV(\"--chart-grid\"),ctxt:cssV(\"--chart-text\"),")
        w("};}")
        w("function mkChart(id,cfg){")
        w("  if(_charts[id]){_charts[id].destroy();}")
        w("  var el=document.getElementById(id);if(!el)return null;")
        w("  _charts[id]=new Chart(el,cfg);return _charts[id];")
        w("}")
        w("function bAxes(){")
        w("  var c=cc();")
        w("  return{")
        w("    x:{grid:{color:c.grid},ticks:{color:c.ctxt,font:{size:11}}},")
        w("    y:{grid:{color:c.grid},ticks:{color:c.ctxt,font:{size:11},callback:function(v){return fmtM(v);}}},")
        w("  };")
        w("}")
        w("")
        w("function applyRange(){")
        w("  var fe=document.getElementById('day-from'),te=document.getElementById('day-to');")
        w("  var f=parseInt(fe?fe.value:1)||1;")
        w("  var t=parseInt(te?te.value:MAX_DAY)||MAX_DAY;")
        w("  f=Math.max(1,Math.min(f,MAX_DAY));t=Math.max(f,Math.min(t,MAX_DAY));")
        w("  if(fe)fe.value=f;if(te)te.value=t;")
        w("  var days=t-f+1;")
        w("  var lbl=document.getElementById('range-lbl');")
        w("  if(lbl)lbl.textContent=f+'\u2013'+t+' ('+days+' d\xedas)';")
        w("  document.querySelectorAll('.period-chip').forEach(function(b){b.classList.remove('active');});")
        w("  updateResumen(f,t);")
        w("  renderVentas(f,t);")
        w("  if(_activeTab===2)renderHorarios(f,t);")
        w("  if(_activeTab===3)renderStock(f,t);")
        w("  if(_activeTab===4)renderCancChart(f,t);")
        w("  if(_activeTab===7)renderTopItems(f,t);")
        w("}")
        w("function setRange(f,t){")
        w("  var fe=document.getElementById('day-from'),te=document.getElementById('day-to');")
        w("  if(fe)fe.value=f;if(te)te.value=t;")
        w("  applyRange();")
        w("}")
        w("function updateResumen(dayFrom,dayTo){")
        w("  var f=dayFrom||1,t=dayTo||MAX_DAY;")
        w("  var gmv=0,units=0,paid=0,canc=0,dArr=[],pArr=[];")
        w("  var gmvP=0,unitsP=0,paidP=0,cancP=0;")  
        w("  for(var day=1;day<=MAX_DAY;day++){")
        w("    var dc=DAILY_CUR[String(day)]||{};var dp=DAILY_PRI[String(day)]||{};")
        w("    if(day>=f&&day<=t){")
        w("      gmv+=dc.gmv||0;units+=dc.units||0;paid+=dc.paid||0;canc+=dc.canc||0;")
        w("      gmvP+=dp.gmv||0;unitsP+=dp.units||0;paidP+=dp.paid||0;cancP+=dp.canc||0;")
        w("    }")
        w("    dArr.push(dc.gmv||0);pArr.push(dp.gmv||0);")
        w("  }")
        w("  var cr=(paid+canc)>0?canc/(paid+canc)*100:0;")
        w("  var tk=paid>0?gmv/paid:0;")
        w("  var crP=(paidP+cancP)>0?cancP/(paidP+cancP)*100:0;")
        w("  var tkP=paidP>0?gmvP/paidP:0;")
        w("  var kg=document.getElementById(\"kpi-grid\");")
        w("  if(kg){")
        w("    var rows=[")
        w("      {lbl:\"GMV Periodo\",val:fmtM(gmv),col:\"var(--blue)\",dp:dPct(gmv,gmvP),pri:\"Ant: \"+fmtM(gmvP)},")
        w("      {lbl:\"Unidades\",val:fmtN(units),col:\"var(--text)\",dp:dPct(units,unitsP),pri:\"Ant: \"+fmtN(unitsP)},")
        w("      {lbl:\"Ticket prom.\",val:fmtM(tk),col:\"var(--cyan)\",dp:dPct(tk,tkP),pri:\"Ant: \"+fmtM(tkP)},")
        w("      {lbl:\"Tasa cancel.\",val:cr.toFixed(1)+\"%\",col:cr>5?\"var(--red)\":\"var(--green)\",dp:dPct(cr,crP),inv:true,pri:\"Ant: \"+crP.toFixed(1)+\"%\"},")
        w("      {lbl:\"Pagadas\",val:fmtN(paid),col:\"var(--green)\",dp:dPct(paid,paidP),pri:\"Canc: \"+fmtN(canc)},")
        w(f"      {{lbl:\"Comisiones ML\",val:\"{fmt_money(fees_c)}\",col:\"var(--red)\",dp:null,pri:\"~{round(fee_rate_c*100,1)}% GMV\"}},")
        w("    ];")
        w("    kg.innerHTML=rows.map(function(k){")
        w("      var da=k.dp!==null?'<div class=\"kpi-delta\">'+arrH(k.dp,k.inv||false)+\"</div>\":\"\";")
        w("      return'<div class=\"kpi\"><div class=\"kpi-label\">'+k.lbl+'</div><div class=\"kpi-val\" style=\"color:'+k.col+'\">'+k.val+\"</div>\"+da+'<div class=\"kpi-pri\">'+k.pri+\"</div></div>\";")
        w("    }).join(\"\");")
        w("  }")
        w("  function renderPctList(elId,data,accent){")
        w("    var el=document.getElementById(elId);if(!el)return;")
        w("    var entries=Object.entries(data||{}).sort(function(a,b){return(b[1].gmv||0)-(a[1].gmv||0);});")
        w("    var tot=entries.reduce(function(s,e){return s+(e[1].gmv||0);},0)||1;")
        w("    el.innerHTML=entries.map(function(e){")
        w("      var p=(e[1].gmv/tot*100).toFixed(1);")
        w("      return'<div class=\"pct-row\"><span class=\"pct-lbl\">'+e[0]+'</span><div class=\"pct-track\"><div class=\"pct-fill\" style=\"width:'+p+'%;background:'+accent+'\"></div></div><span class=\"pct-num\">'+fmtM(e[1].gmv)+\" (\"+p+\"%)</span></div>\";")
        w("    }).join(\"\");")
        w("  }")
        w("  // Compute listing_type and logistic from DAILY_LT/LOG for selected range")
        w("  function buildRangeBreakdown(dailyData,f,t,baseFull,skipLbls){")
        w("    var merged={};")
        w("    if(baseFull){Object.keys(baseFull).forEach(function(lbl){")
        w("      if(!skipLbls||skipLbls.indexOf(lbl)<0)merged[lbl]=0;")
        w("    });}")
        w("    for(var d=f;d<=t;d++){")
        w("      var dd=dailyData[String(d)]||{};")
        w("      Object.keys(dd).forEach(function(lbl){")
        w("        if(skipLbls&&skipLbls.indexOf(lbl)>=0)return;")
        w("        merged[lbl]=(merged[lbl]||0)+dd[lbl];")
        w("      });")
        w("    }")
        w("    return merged;")
        w("  }")
        w("  function renderBarList(elId,data,accent){")
        w("    var el=document.getElementById(elId);if(!el)return;")
        w("    var entries=Object.entries(data).sort(function(a,b){return b[1]-a[1];});")
        w("    var tot=entries.reduce(function(s,e){return s+e[1];},0)||1;")
        w("    el.innerHTML=entries.map(function(e){")
        w("      var p=(e[1]/tot*100).toFixed(1);")
        w("      return'<div class=\"pct-row\"><span class=\"pct-lbl\">'+e[0]+'</span>'") 
        w("        +'<div class=\"pct-track\"><div class=\"pct-fill\" style=\"width:'+p+'%;background:'+accent+'\">'+'</div></div>'") 
        w("        +'<span class=\"pct-num\">'+fmtM(e[1])+' ('+p+'%)</span></div>';") 
        w("    }).join('');")
        w("  }")
        w("  renderBarList('lt-section',buildRangeBreakdown(DAILY_LT,f,t,LT_CUR,['Sin clasificar']),'var(--blue)');") 
        w("  renderBarList('log-section',buildRangeBreakdown(DAILY_LOG,f,t,LOG_CUR,[]),'var(--cyan)');") 
        w("  var c=cc();")
        w("  var lbl=Array.from({length:MAX_DAY},function(_,i){return i+1;});")
        w("  var bgCur=lbl.map(function(d){return(d>=f&&d<=t)?c.blue+'cc':c.text3+'33';});")
        w("  var bgPri=lbl.map(function(d){return(d>=f&&d<=t)?c.text2+'55':c.text3+'22';});")
        w("  mkChart(\"c-daily\",{type:\"bar\",")
        w("    data:{labels:lbl,datasets:[")
        w("      {label:\"Mes actual (\"+PERIOD_CUR+\")\",data:dArr,backgroundColor:bgCur,borderRadius:4},")
        w("      {label:\"Mes anterior (\"+PERIOD_PRI+\")\",data:pArr,backgroundColor:bgPri,borderRadius:4},")
        w("    ]},")
        w("    options:{responsive:true,maintainAspectRatio:false,")
        w("      plugins:{legend:{labels:{color:c.ctxt,font:{size:11}}}},scales:bAxes()}")
        w("  });")
        w("}")
        w("")
        w("var _expCats={};")
        w("function renderVentas(dayFrom,dayTo){")
        w("  var f=dayFrom||parseInt((document.getElementById('day-from')||{}).value)||1;")
        w("  var t=dayTo||parseInt((document.getElementById('day-to')||{}).value)||MAX_DAY;")
        w("  var tb=document.getElementById('cat-tbody');if(!tb)return;")
        w("  var filtCat={},filtCatPri={};")
        w("  for(var d=f;d<=t;d++){")
        w("    var dc=DAILY_BY_CAT[String(d)]||{};")
        w("    var dp=DAILY_BY_CAT_PRI[String(d)]||{};")
        w("    Object.keys(dc).forEach(function(c){")
        w("      if(!filtCat[c])filtCat[c]={gmv:0,units:0};")
        w("      filtCat[c].gmv+=dc[c].gmv||0;filtCat[c].units+=dc[c].units||0;")
        w("    });")
        w("    Object.keys(dp).forEach(function(c){")
        w("      if(!filtCatPri[c])filtCatPri[c]={gmv:0,units:0};")
        w("      filtCatPri[c].gmv+=dp[c].gmv||0;filtCatPri[c].units+=dp[c].units||0;")
        w("    });")
        w("  }")
        w("  [filtCat,filtCatPri].forEach(function(fc){")
        w("    ['PEQUEÑO ELECTRO','PEQUEÑO ELECTROS'].forEach(function(b){")
        w("      if(fc[b]){if(!fc['PEQUEÑOS ELECTRO'])fc['PEQUEÑOS ELECTRO']={gmv:0,units:0};")
        w("        fc['PEQUEÑOS ELECTRO'].gmv+=fc[b].gmv;fc['PEQUEÑOS ELECTRO'].units+=fc[b].units;delete fc[b];}")
        w("    });")
        w("    if(fc['LUCES']){if(!fc['ILUMINACION'])fc['ILUMINACION']={gmv:0,units:0};")
        w("      fc['ILUMINACION'].gmv+=fc['LUCES'].gmv;fc['ILUMINACION'].units+=fc['LUCES'].units;delete fc['LUCES'];}")
        w("  });")
        w("  var totalG=Object.values(filtCat).reduce(function(s,c){return s+c.gmv;},0)||1;")
        w("  var cats=Object.entries(filtCat).filter(function(e){return e[1].gmv>0;}).sort(function(a,b){return b[1].gmv-a[1].gmv;});")
        w("  _CAT_KEYS=cats.map(function(e){return e[0];});")
        w("  var html='';")
        w("  cats.forEach(function(entry,idx){")
        w("    var cat=entry[0],fData=entry[1];")
        w("    var priData=filtCatPri[cat]||{};")
        w("    var fullData=BY_CAT_CUR[cat]||{gmv:0,units:0,skus:{}};")
        w("    var ratio=fullData.gmv>0?fData.gmv/fullData.gmv:1;")
        w("    var share=(fData.gmv/totalG*100).toFixed(1);")
        w("    var dpG=dPct(fData.gmv,priData.gmv);")
        w("    var tk=fData.units>0?fData.gmv/fData.units:0;")
        w("    var exp=!!_expCats[cat];")
        w("    var skuN=Object.keys(fullData.skus||{}).length;")
        w("    html+='<tr class=\"cat-row\" onclick=\"toggleCat('+idx+')\">'+''")
        w("    html+='<td><span class=\"cat-toggle\">'+(exp?'&#9660;':'&#9654;')+'</span><strong>'+cat+'</strong>'")
        w("    html+='<span style=\"color:var(--text3);font-size:11px;margin-left:6px\">'+skuN+' SKUs</span></td>'")
        w("    html+='<td style=\"font-weight:700;color:var(--blue);text-align:right\">'+fmtM(fData.gmv)+'</td>'")
        w("    html+='<td style=\"text-align:right\">'+fmtN(fData.units)+'</td>'")
        w("    html+='<td style=\"text-align:right\">'+fmtM(tk)+'</td>'")
        w("    html+='<td style=\"text-align:center\"><span class=\"badge-share\">'+share+'%</span></td>'")
        w("    html+='<td style=\"text-align:center\">'+arrH(dpG)+'</td></tr>'")
        w("    if(exp){")
        w("      var skus=Object.values(fullData.skus||{}).sort(function(a,b){return b.gmv-a.gmv;});")
        w("      skus.forEach(function(s){")
        w("        var sGmv=Math.round(s.gmv*ratio);")
        w("        var sU=Math.round(s.units*ratio);")
        w("        var sS=fData.gmv>0?(sGmv/fData.gmv*100).toFixed(1):'0.0';")
        w("        var sT=sU>0?sGmv/sU:0;")
        w("        var priSku=TOP_ITEMS_PRI[s.id]||{};")
        w("        var dpSku=priSku.gmv?dPct(sGmv,priSku.gmv):null;")
        w("        html+='<tr class=\"sku-row expanded\">';")
        w("        html+='<td style=\"padding-left:32px\"><span style=\"color:var(--cyan);font-weight:700;font-size:12px\">'+s.id+'</span> ';")
        w("        html+='<span style=\"color:var(--text2);font-size:11px\">'+(s.title||'').slice(0,45)+'</span></td>';")
        w("        html+='<td style=\"color:var(--cyan);text-align:right\">'+fmtM(sGmv)+'</td>';")
        w("        html+='<td style=\"text-align:right\">'+fmtN(sU)+'</td>';")
        w("        html+='<td style=\"text-align:right\">'+fmtM(sT)+'</td>';")
        w("        html+='<td style=\"text-align:center\"><span class=\"badge-sku\">'+sS+'%</span></td>';")
        w("        html+='<td style=\"text-align:center\">'+arrH(dpSku)+'</td></tr>';")
        w("      });")
        w("    }")
        w("  });")
        w("  tb.innerHTML=html;")
        w("}")
        w("var _CAT_KEYS=[];")
        w("function toggleCat(idx){var cat=_CAT_KEYS[idx];if(cat!==undefined){_expCats[cat]=!_expCats[cat];var fe=document.getElementById('day-from'),te=document.getElementById('day-to');renderVentas(parseInt((fe||{}).value)||1,parseInt((te||{}).value)||MAX_DAY);}}")
        w("")
        w("function renderHorarios(dayFrom,dayTo){")
        w("  var f=dayFrom||1,t=dayTo||MAX_DAY;")
        w("  var c=cc();")
        w("  var hourArr=Array(24).fill(0),hourCnt=Array(24).fill(0);")
        w("  var dowArr=Array(7).fill(0),dowCnt=Array(7).fill(0);")
        w("  var hmArr=Array(7).fill(null).map(function(){return Array(24).fill(0);});")
        w("  for(var d=f;d<=t;d++){")
        w("    var dh=DAILY_HOUR[String(d)]||{};")
        w("    var dayTot=0;")
        w("    Object.keys(dh).forEach(function(h){var hh=parseInt(h),v=dh[h]||0;hourArr[hh]+=v;hourCnt[hh]++;dayTot+=v;});")
        w("    var dow=DAY_TO_DOW[String(d)];")
        w("    if(dow!==undefined){dowArr[dow]+=dayTot;dowCnt[dow]++;}") 
        w("    Object.keys(dh).forEach(function(h){if(dow!==undefined)hmArr[dow][parseInt(h)]+=(dh[h]||0);});")
        w("  }")
        w("  hourArr=hourArr.map(function(v,i){return hourCnt[i]?Math.round(v/hourCnt[i]):0;});")
        w("  dowArr=dowArr.map(function(v,i){return dowCnt[i]?Math.round(v/dowCnt[i]):0;});")
        w("  var l24=Array.from({length:24},function(_,i){return String(i).padStart(2,\"00\")+\":00\";});")
        w("  mkChart(\"c-hour\",{type:\"bar\",")
        w("    data:{labels:l24,datasets:[{label:\"GMV prom/hora\",data:hourArr,backgroundColor:c.blue+\"cc\",borderRadius:4}]},")
        w("    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:c.ctxt}}},scales:bAxes()}")
        w("  });")
        w("  var DOW=[\"Lun\",\"Mar\",\"Mie\",\"Jue\",\"Vie\",\"Sab\",\"Dom\"];")
        w("  mkChart(\"c-dow\",{type:\"bar\",")
        w("    data:{labels:DOW,datasets:[{label:\"GMV prom/dia\",data:dowArr,")
        w("      backgroundColor:DOW.map(function(_,i){return(i>=5?c.cyan:c.blue)+\"cc\";}),borderRadius:6}]},")
        w("    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:c.ctxt}}},scales:bAxes()}")
        w("  });")
        w("  renderHeatmap(hmArr);")
        w("  var ins=document.getElementById(\"hora-insights\");")
        w("  if(ins&&hourArr.some(function(v){return v>0;})){")
        w("    var mxH=hourArr.indexOf(Math.max.apply(null,hourArr));")
        w("    var valH=hourArr.filter(function(v){return v>0;});")
        w("    var mnH=valH.length?hourArr.indexOf(Math.min.apply(null,valH)):0;")
        w("    var mxD=dowArr.indexOf(Math.max.apply(null,dowArr));")
        w("    ins.innerHTML=\"<div>Hora pico: <b>\"+String(mxH).padStart(2,\"0\")+\":00</b> &mdash; \"+fmtM(hourArr[mxH])+\"/hora prom.</div>\"")
        w("      +\"<div>Hora valle: <b>\"+String(mnH).padStart(2,\"0\")+\":00</b> &mdash; \"+fmtM(hourArr[mnH]||0)+\"/hora</div>\"")
        w("      +\"<div>Mejor dia: <b>\"+(DOW[mxD]||\"?\")+\"</b> &mdash; \"+fmtM(dowArr[mxD]||0)+\"/dia prom.</div>\"")
        w("      +\"<div>Tip: Concentra Ads entre \"+String(Math.max(0,mxH-1)).padStart(2,\"0\")+\":00-\"+String(Math.min(23,mxH+2)).padStart(2,\"0\")+\":00 los <b>\"+(DOW[mxD]||\"?\")+\"</b>.</div>\";")
        w("  }")
        w("}")
        w("function renderHeatmap(hmData){")
        w("  var wrap=document.getElementById(\"heatmap-wrap\");if(!wrap||!HEATMAP||!HEATMAP.length)return;")
        w("  var DOW=[\"Lun\",\"Mar\",\"Mie\",\"Jue\",\"Vie\",\"Sab\",\"Dom\"];")
        w("  var flat=HEATMAP.reduce(function(a,r){return a.concat(r.filter(function(v){return v>0;}));;},[]);")
        w("  var maxV=flat.length?Math.max.apply(null,flat):1;")
        w("  var html='<table class=\"heatmap-tbl\"><thead><tr><th></th>';")
        w("  for(var h=0;h<24;h++)html+=\"<th>\"+String(h).padStart(2,\"0\")+\"</th>\";")
        w("  html+=\"</tr></thead><tbody>\";")
        w("  hm.forEach(function(row,di){")
        w("    html+=\"<tr><td class=\\\"heatmap-lbl\\\">\"+(DOW[di]||di)+\"</td>\";")
        w("    (row||[]).forEach(function(v){")
        w("      var p=v>0?v/maxV:0;")
        w("      var bg=v>0?\"rgba(52,131,250,\"+(p*0.8+0.12).toFixed(2)+\")\":\"transparent\";")
        w("      var tc=p>0.5?\"#ffffff\":\"var(--text3)\";")
        w("      html+='<td class=\"hm-cell\" style=\"background:'+bg+\";color:\"+tc+'\" title=\"'+fmtM(v)+'\">'+(v>0?fmtM(v).replace(\"$\",\"\"):\"\")+\"</td>\";")
        w("    });")
        w("    html+=\"</tr>\";")
        w("  });")
        w("  html+=\"</tbody></table>\";")
        w("  wrap.innerHTML=html;")
        w("}")
        w("")
        w("function renderStock(dayFrom,dayTo){")
        w("  var f=dayFrom||1,t=dayTo||MAX_DAY;")
        w("  var filtSku={};") 
        w("  for(var d=f;d<=t;d++){var ds=DAILY_SKU[String(d)]||{};Object.keys(ds).forEach(function(sk){if(!filtSku[sk])filtSku[sk]={gmv:0,units:0};filtSku[sk].gmv+=ds[sk].gmv||0;filtSku[sk].units+=ds[sk].units||0;});}")
        w("  var catF=(document.getElementById(\"stk-cat-filter\")?document.getElementById(\"stk-cat-filter\").value:\"\").toLowerCase();")
        w("  var showF=document.getElementById(\"stk-show-filter\")?document.getElementById(\"stk-show-filter\").value:\"all\";")
        w("  var data=ML_ITEMS_DATA.filter(function(r){")
        w("    if(catF&&!(r.categoria||\"\").toLowerCase().includes(catF))return false;")
        w("    var st=r.stock_total||0,vs=r.vta_semana||0;")
        w("    var cov=vs>0?st/(vs/7):9999;")
        w("    if(showF===\"zero\")return st===0;")
        w("    if(showF===\"low\")return st<10;")
        w("    if(showF===\"critical\")return cov<7;")
        w("    return true;")
        w("  }).slice().sort(function(a,b){var fa=filtSku[a.codigo||a.sku||""],fb=filtSku[b.codigo||b.sku||""];return(fb?fb.gmv:b.gmv_period||0)-(fa?fa.gmv:a.gmv_period||0);});")
        w("  var sm=document.getElementById(\"stock-summary\");")
        w("  if(sm){")
        w("    var tot=data.length;")
        w("    var zero=data.filter(function(r){return(r.stock_total||0)===0;}).length;")
        w("    var crit=data.filter(function(r){var v=r.vta_semana||0,s=r.stock_total||0;return s>0&&v>0&&(s/(v/7))<7;}).length;")
        w("    var full=data.reduce(function(s,r){return s+(r.stock_full||0);},0);")
        w("    sm.innerHTML=[")
        w("      {lbl:\"SKUs analizados\",val:tot,col:\"var(--text)\"},")
        w("      {lbl:\"Sin stock\",val:zero,col:zero>0?\"var(--red)\":\"var(--green)\"},")
        w("      {lbl:\"Cobertura &lt;7d\",val:crit,col:crit>0?\"var(--yellow)\":\"var(--green)\"},")
        w("      {lbl:\"Stock Full\",val:fmtN(full),col:\"var(--cyan)\"},")
        w("    ].map(function(k){return'<div class=\"kpi\"><div class=\"kpi-label\">'+k.lbl+'</div><div class=\"kpi-val\" style=\"color:'+k.col+'\">'+k.val+\"</div></div>\";}).join(\"\");")
        w("  }")
        w("  var tb=document.getElementById(\"stock-tbody\");if(!tb)return;")
        w("  tb.innerHTML=data.map(function(r){")
        w("    var vs=r.vta_semana||0,st=r.stock_total||0;")
        w("    var covD=vs>0?(st/(vs/7)).toFixed(0):\"inf\";")
        w("    var covN=parseFloat(covD);")
        w("    var covC=isNaN(covN)?\"var(--text3)\":covN<7?\"var(--red)\":covN<15?\"var(--yellow)\":\"var(--green)\";")
        w("    return\"<tr>\"")
        w("      +'<td style=\"font-weight:700;color:var(--cyan);font-size:12px\">'+(r.codigo||r.sku||\"&mdash;\")+\"</td>\"")
        w("      +'<td style=\"font-size:11px;color:var(--text2)\">'+(r.descripcion||r.title||\"\").slice(0,42)+\"</td>\"")
        w("      +'<td style=\"font-size:11px;color:var(--text3)\">'+(r.categoria||\"\")+\"</td>\"")
        w("      +\"<td>\"+(filtSku[r.codigo||r.sku||""]?(filtSku[r.codigo||r.sku||""].units):(r.units_period||0))+\"</td>\"")
        w("      +'<td style=\"color:var(--blue)\">'+fmtM(filtSku[r.codigo||r.sku||""]?(filtSku[r.codigo||r.sku||""].gmv):(r.gmv_period||0))+\"</td>\"")
        w("      +'<td style=\"font-weight:700;color:'+(st===0?\"var(--red)\":\"var(--text)\")+'\">'+fmtN(st)+\"</td>\"")
        w("      +'<td style=\"color:'+covC+';font-weight:700\">'+(covD===\"inf\"?\"&infin;\":covD+\"d\")+\"</td>\"")
        w("      +'<td style=\"color:var(--text3)\">'+fmtN(r.stock_dep||0)+\"</td>\"")
        w("      +'<td style=\"color:var(--cyan)\">'+fmtN(r.stock_full||0)+\"</td>\"")
        w("      +'<td style=\"color:var(--text3)\">'+fmtN(r.stock_aduana||0)+\"</td>\"")
        w("      +\"</tr>\";")
        w("  }).join(\"\");")
        w("}")
        w("")
        w("function renderCancChart(dayFrom,dayTo){")
        w("  var f=dayFrom||1,t=dayTo||MAX_DAY;")
        w("  var c=cc();")
        w("  var totPaid=0,totCanc=0,totGmv=0,totPaidP=0,totCancP=0;")
        w("  for(var d=f;d<=t;d++){")
        w("    var dc=DAILY_CUR[String(d)]||{},dp=DAILY_PRI[String(d)]||{};")
        w("    totPaid+=dc.paid||0;totCanc+=dc.canc||0;totGmv+=dc.gmv||0;")
        w("    totPaidP+=dp.paid||0;totCancP+=dp.canc||0;")
        w("  }")
        w("  var cr=(totPaid+totCanc)>0?totCanc/(totPaid+totCanc)*100:0;")
        w("  var crP=(totPaidP+totCancP)>0?totCancP/(totPaidP+totCancP)*100:0;")
        w("  var tk=totPaid>0?totGmv/totPaid:0;")
        w("  var gmvPerd=totCanc*tk;")
        w("  var kg=document.getElementById('canc-kpi-grid');")
        w("  if(kg){")
        w("    var rows=[")
        w("      {lbl:'Tasa cancelación',val:cr.toFixed(1)+'%',col:'var(--text)',dp:dPct(cr,crP),pri:'Ant: '+crP.toFixed(1)+'%'},")
        w("      {lbl:'Unidades canceladas',val:fmtN(totCanc),col:'var(--red)',pri:'Ant: '+fmtN(totCancP)},")
        w("      {lbl:'Órdenes pagadas',val:fmtN(totPaid),col:'var(--green)',pri:'Ant: '+fmtN(totPaidP)},")
        w("      {lbl:'GMV perdido est.',val:fmtM(gmvPerd),col:'var(--red)',pri:'Ticket: '+fmtM(tk)},")
        w("    ];")
        w("    kg.innerHTML=rows.map(function(r){")
        w("      return '<div class=\"kpi\"><div class=\"kpi-label\">'+r.lbl+'</div>'")
        w("             +'<div class=\"kpi-val\" style=\"color:'+r.col+'\">'+r.val+'</div>'")
        w("             +(r.dp!==null&&r.dp!==undefined?'<div class=\"kpi-delta '+(r.dp>=0?'good':'bad')+'\">'+arrH(r.dp)+'</div>':'')") 
        w("             +'<div class=\"kpi-pri\">'+(r.pri||'')+'</div></div>';")
        w("    }).join('');")
        w("  }")
        w("  var lbl=Array.from({length:t-f+1},function(_,i){return f+i;});")
        w("  var cArr=lbl.map(function(d){return(DAILY_CUR[String(d)]||{}).canc||0;});")
        w("  var pArr=lbl.map(function(d){return(DAILY_CUR[String(d)]||{}).paid||0;});")
        w("  mkChart('c-canc-daily',{type:'bar',")
        w("    data:{labels:lbl,datasets:[")
        w("      {label:'Pagadas',data:pArr,backgroundColor:c.green+'99',borderRadius:3},")
        w("      {label:'Canceladas',data:cArr,backgroundColor:c.red+'cc',borderRadius:3},")
        w("    ]},")
        w("    options:{responsive:true,maintainAspectRatio:false,")
        w("      plugins:{legend:{labels:{color:c.ctxt}}},")
        w("      scales:{")
        w("        x:{grid:{color:c.grid},ticks:{color:c.ctxt,font:{size:10}}},")
        w("        y:{grid:{color:c.grid},ticks:{color:c.ctxt,font:{size:10}}},")
        w("      }}")
        w("  });")
        w("}")

        w("")
        w("function renderTopItems(dayFrom,dayTo){")
        w("  var f=dayFrom||1,t=dayTo||MAX_DAY;")
        w("  var filtSku={};") 
        w("  for(var d=f;d<=t;d++){var ds=DAILY_SKU[String(d)]||{};Object.keys(ds).forEach(function(sk){if(!filtSku[sk])filtSku[sk]={gmv:0,units:0};filtSku[sk].gmv+=ds[sk].gmv||0;filtSku[sk].units+=ds[sk].units||0;});}")
        w("  var sort=document.getElementById(\"top-sort\")?document.getElementById(\"top-sort\").value:\"gmv\";")
        w("  var catF=(document.getElementById(\"top-cat-filter\")?document.getElementById(\"top-cat-filter\").value:\"\").toLowerCase();")
        w("  var items=[];  // set below by allItems.filter")
        w("  items=allItems.filter(function(x){return!catF||(x.categoria||\"\").toLowerCase().includes(catF);});items=items.slice().sort(function(a,b){return(b[sort]||0)-(a[sort]||0);});")
        w("  var totG=allItems.reduce(function(s,x){return s+(x.gmv||0);},0)||1;")
        w("  var totU=allItems.reduce(function(s,x){return s+(x.units||0);},0)||1;")
        w("  var kpis=document.getElementById(\"top-kpis\");")
        w("  if(kpis){")
        w("    var mC=items.filter(function(x){return x.method===\"master\";}).length;")
        w("    var fC=items.filter(function(x){return x.method===\"fallback\";}).length;")
        w("    var uC=items.filter(function(x){return x.method===\"unmapped\";}).length;")
        w("    kpis.innerHTML=[")
        w("      {lbl:\"SKUs mostrados\",val:items.length,col:\"var(--text)\"},")
        w("      {lbl:\"Via maestro\",val:mC,col:\"var(--green)\"},")
        w("      {lbl:\"Via fallback\",val:fC,col:\"var(--yellow)\"},")
        w("      {lbl:\"Sin mapear\",val:uC,col:\"var(--red)\"},")
        w("    ].map(function(k){return'<div class=\"kpi\"><div class=\"kpi-label\">'+k.lbl+'</div><div class=\"kpi-val\" style=\"color:'+k.col+'\">'+k.val+\"</div></div>\";}).join(\"\");")
        w("  }")
        w("  var allItems=TOP_ITEMS.map(function(x){var fs=filtSku[x.sku]||{};return Object.assign({},x,{gmv:fs.gmv||x.gmv,units:fs.units||x.units});});")
        w("  var totG=allItems.reduce(function(s,x){return s+(x.gmv||0);},0)||1;")
        w("  var totU=allItems.reduce(function(s,x){return s+(x.units||0);},0)||1;")
        w("  var tb=document.getElementById(\"top-tbody\");if(!tb)return;")
        w("  tb.innerHTML=items.slice(0,50).map(function(x,i){")
        w("    var pri=TOP_ITEMS_PRI[x.sku]||{};")
        w("    var dpG=dPct(x.gmv,pri.gmv);var dpU=dPct(x.units,pri.units);")
        w("    var gSh=(x.gmv/totG*100).toFixed(1);")
        w("    var uSh=(x.units/totU*100).toFixed(1);")
        w("    var mCol=x.method===\"master\"?\"var(--green)\":x.method===\"fallback\"?\"var(--yellow)\":\"var(--red)\";")
        w("    var mIco=x.method===\"master\"?\"OK\":x.method===\"fallback\"?\"~\":\"?\";")
        w("    return\"<tr>\"")
        w("      +'<td style=\"color:var(--text3)\">'+(i+1)+\"</td>\"")
        w("      +\"<td>\"")
        w("        +'<span style=\"color:'+mCol+';font-size:10px;font-weight:700;border:1px solid '+mCol+';border-radius:3px;padding:1px 3px\">'+mIco+\"</span> \"")
        w("        +'<span style=\"font-weight:700;color:var(--cyan);font-size:12px\">'+(x.sku||\"\")+\"</span><br>\"")
        w("        +'<span style=\"color:var(--text2);font-size:10px\">'+(x.title||\"\").slice(0,40)+\"</span>\"")
        w("      +\"</td>\"")
        w("      +'<td style=\"font-size:11px;color:var(--text3)\">'+(x.categoria||\"\")+\"</td>\"")
        w("      +'<td style=\"font-weight:700;color:var(--blue)\">'+fmtM(x.gmv)+\"</td>\"")
        w("      +'<td><span class=\"badge-share\">'+gSh+\"%</span></td>\"")
        w("      +\"<td>\"+fmtN(x.units||0)+\"</td>\"")
        w("      +'<td><span class=\"badge-share\">'+uSh+\"%</span></td>\"")
        w("      +\"<td>\"+arrH(dpG)+\"</td>\"")
        w("      +\"<td>\"+arrH(dpU)+\"</td>\"")
        w("      +\"</tr>\";")
        w("  }).join(\"\");")
        w("}")
        w("")
        w("function renderAnual(){")
        w("  var c=cc();")
        w("  var lbl=MONTHLY.map(function(m){return m.label||\"\";});")
        w("  var gmvs=MONTHLY.map(function(m){return m.gmv||0;});")
        w("  var tkts=MONTHLY.map(function(m){return m.avg_ticket||0;});")
        w("  mkChart(\"c-anual\",{type:\"bar\",")
        w("    data:{labels:lbl,datasets:[")
        w("      {label:\"GMV mensual\",data:gmvs,yAxisID:\"y\",")
        w("       backgroundColor:gmvs.map(function(_,i){return(MONTHLY[i]&&MONTHLY[i].complete?c.blue:c.cyan)+\"cc\";}),")
        w("       borderRadius:6,order:2},")
        w("      {label:\"Ticket prom.\",data:tkts,type:\"line\",yAxisID:\"y2\",")
        w("       borderColor:c.yellow,backgroundColor:\"transparent\",")
        w("       borderWidth:2,pointBackgroundColor:c.yellow,pointRadius:4,order:1},")
        w("    ]},")
        w("    options:{responsive:true,maintainAspectRatio:false,")
        w("      plugins:{legend:{labels:{color:c.ctxt,font:{size:11}}}},")
        w("      scales:{")
        w("        x:{grid:{color:c.grid},ticks:{color:c.ctxt}},")
        w("        y:{grid:{color:c.grid},ticks:{color:c.ctxt,callback:function(v){return fmtM(v);}},")
        w("           title:{display:true,text:\"GMV\",color:c.ctxt}},")
        w("        y2:{position:\"right\",grid:{display:false},")
        w("            ticks:{color:c.yellow,callback:function(v){return fmtM(v);}},")
        w("            title:{display:true,text:\"Ticket\",color:c.yellow}},")
        w("      }}")
        w("  });")
        w("}")
        w("")
        w("document.addEventListener(\"DOMContentLoaded\",function(){")
        w("  var t=localStorage.getItem(\"sp-theme\")||\"dark\";")
        w("  var btn=document.getElementById(\"theme-icon\");")
        w("  if(btn)btn.textContent=t===\"dark\"?\"☀\":\"☾\";")
        w("  applyRange();")
        w("});")
        w("")
        w('</script>')
        w('</body></html>')
    return out_path
