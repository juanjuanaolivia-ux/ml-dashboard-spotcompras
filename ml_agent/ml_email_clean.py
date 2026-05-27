#!/usr/bin/env python3
"""
ml_email_clean.py — Resumen diario ML 360
Seccion 1: Ventas del dia anterior (cierre completo) vs mismo dia semana anterior
Seccion 2: Acumulado mes al CIERRE DE AYER (dias 1..ayer.day) vs mismo corte mes anterior
REGLA: jamas datos parciales de hoy. Siempre cierres completos.
"""
import json, os, smtplib, sys
from datetime import datetime, date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CFG_FILE = os.path.join(BASE_DIR, 'ml_email_config.json')


def _load(name):
    p = os.path.join(DATA_DIR, name)
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def _fmt_money(v):
    v = float(v or 0)
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"


def _delta(cur, pri):
    cur, pri = float(cur or 0), float(pri or 0)
    if not pri:
        return None
    return ((cur - pri) / pri) * 100


def _arrow(pct, inv=False):
    if pct is None:
        return "---", "#888"
    if pct > 0:
        return f"arriba {pct:.1f}%", ("#d33" if inv else "#00A650")
    elif pct < 0:
        return f"abajo {abs(pct):.1f}%", ("#00A650" if inv else "#d33")
    return "= 0%", "#888"


def _day_stats(orders, day_str):
    paid = [o for o in orders if o.get('date_created', '').startswith(day_str) and o.get('status') == 'paid']
    canc = [o for o in orders if o.get('date_created', '').startswith(day_str) and o.get('status') == 'cancelled']
    gmv   = sum(o.get('total_amount', 0) or 0 for o in paid)
    units = sum(i.get('quantity', 0) or 0 for o in paid for i in o.get('items', []))
    return {'gmv': gmv, 'orders': len(paid), 'units': units, 'cancelled': len(canc)}


def build_email_html():
    mp      = _load('metrics_prior.json')
    summary = _load('summary.json')
    rep     = _load('reputation.json')
    ads_m   = _load('ads_manual.json')
    monthly = _load('monthly_2026.json')
    orders  = _load('orders_current.json')
    if not isinstance(orders, list):
        orders = []

    today      = date.today()
    ayer       = today - timedelta(days=1)
    ayer_str   = ayer.strftime('%Y-%m-%d')
    ayer_label = ayer.strftime('%d/%m/%Y')
    semana_ant = (ayer - timedelta(days=7)).strftime('%Y-%m-%d')
    today_str  = today.strftime('%d/%m/%Y')

    period_cur = summary.get('period_cur_label', 'Mes actual')
    period_pri = summary.get('period_pri_label', 'Mes anterior')
    updated    = summary.get('updated_at', '')[:16].replace('T', ' ')

    # Corte de dias cerrados: ayer.day (e.g. 22 si ayer fue el dia 22)
    cutoff_day       = ayer.day
    period_cur_label = f"{period_cur} al {ayer_label}"
    period_pri_base  = period_pri.split(' (')[0]
    period_pri_label = f"{period_pri_base} (1-{cutoff_day})"

    # SECCION 1: Ventas de ayer (dia cerrado completo) vs mismo dia semana anterior
    ay = _day_stats(orders, ayer_str)
    sw = _day_stats(orders, semana_ant)
    ay_gmv_arr, ay_gmv_col = _arrow(_delta(ay['gmv'],       sw['gmv']))
    ay_ord_arr, ay_ord_col = _arrow(_delta(ay['orders'],    sw['orders']))
    ay_uni_arr, ay_uni_col = _arrow(_delta(ay['units'],     sw['units']))
    ay_can_arr, ay_can_col = _arrow(_delta(ay['cancelled'], sw['cancelled']), inv=True)

    # SECCION 2: Acumulado mes actual dias 1..cutoff_day (excluye hoy = parcial)
    orders_mtd = [o for o in orders if o.get('date_created', '')[:10] <= ayer_str]
    paid_mtd   = [o for o in orders_mtd if o.get('status') == 'paid']
    canc_mtd   = [o for o in orders_mtd if o.get('status') == 'cancelled']
    gmv_c   = sum(o.get('total_amount', 0) or 0 for o in paid_mtd)
    units_c = sum(i.get('quantity', 0) or 0 for o in paid_mtd for i in o.get('items', []))
    paid_c  = len(paid_mtd)
    fees_c  = sum(i.get('sale_fee', 0) or 0 for o in paid_mtd for i in o.get('items', []))
    net_c   = gmv_c - fees_c
    tick_c  = gmv_c / paid_c if paid_c else 0
    crate_c = len(canc_mtd) / (paid_c + len(canc_mtd)) * 100 if (paid_c + len(canc_mtd)) else 0

    # Mes anterior: mismo corte dias 1..cutoff_day para comparacion justa
    ds_p        = mp.get('daily_stats', {})
    prior_days  = [ds_p[k] for k in ds_p if 1 <= int(k) <= cutoff_day]
    gmv_p       = sum(d.get('gmv',   0) for d in prior_days)
    units_p     = sum(d.get('units', 0) for d in prior_days)
    paid_p      = sum(d.get('paid',  0) for d in prior_days)
    canc_p      = sum(d.get('canc',  0) for d in prior_days)
    fee_rate_p  = mp.get('fee_rate', 0) or 0
    net_p       = gmv_p * (1 - fee_rate_p / 100)
    tick_p      = gmv_p / paid_p if paid_p else 0
    crate_p     = canc_p / (paid_p + canc_p) * 100 if (paid_p + canc_p) else 0

    gmv_arr,   gmv_col   = _arrow(_delta(gmv_c,   gmv_p))
    units_arr, units_col = _arrow(_delta(units_c, units_p))
    paid_arr,  paid_col  = _arrow(_delta(paid_c,  paid_p))
    net_arr,   net_col   = _arrow(_delta(net_c,   net_p))
    tick_arr,  tick_col  = _arrow(_delta(tick_c,  tick_p))
    cr_arr,    cr_col    = _arrow(_delta(crate_c, crate_p), inv=True)

    # Reputacion
    rep_status  = rep.get('power_seller_status', '')
    rep_label   = {'platinum': 'MercadoLider Platinum', 'gold': 'MercadoLider Gold',
                   'silver': 'MercadoLider Silver'}.get(rep_status, rep_status.title() or '--')
    rep_color   = {'platinum': '#00d4e4', 'gold': '#FFD700', 'silver': '#A0A0A0'}.get(rep_status, '#aaa')
    claims_pct  = (rep.get('claims_rate', 0) or 0) * 100
    delayed_pct = (rep.get('delayed_rate', 0) or 0) * 100
    sales60     = rep.get('sales_60d', 0) or 0

    # Ads
    roas_str = tacos_str = inv_str = '--'
    if ads_m:
        _inv = ads_m.get('inversion', 0) or 0
        _rev = ads_m.get('ingresos',  0) or 0
        if _inv and _rev:
            roas_str  = f"{_rev / _inv:.1f}x"
            tacos_str = f"{_inv / _rev * 100:.1f}%"
            inv_str   = _fmt_money(_inv)

    # Barras GMV mensual
    if isinstance(monthly, list) and monthly:
        max_gmv = max(m.get('gmv', 0) for m in monthly) or 1
        bars = '<table style="width:100%;border-collapse:collapse;">'
        for m in monthly:
            lbl   = m.get('label', '')
            gv    = m.get('gmv', 0) or 0
            pct   = int(gv / max_gmv * 100)
            color = '#FFE600' if m == monthly[-1] else '#3483FA'
            bars += ('<tr>'
                     f'<td style="padding:3px 6px;font-size:11px;color:#aaa;white-space:nowrap;width:50px;">{lbl}</td>'
                     f'<td style="padding:3px 6px;width:100%;"><div style="background:{color};height:13px;width:{pct}%;border-radius:3px;min-width:4px;"></div></td>'
                     f'<td style="padding:3px 6px;font-size:11px;color:#ccc;white-space:nowrap;">{_fmt_money(gv)}</td>'
                     '</tr>')
        bars += '</table>'
    else:
        bars = '<p style="color:#666;font-size:12px;">Sin datos</p>'

    S = 'style="'; C = 'color:'

    def card(label, val, sub, col):
        return (f'<div {S}flex:1;min-width:120px;background:#0d0d2e;border-radius:8px;padding:14px 12px;text-align:center;border:1px solid #1e1e3a;">'
                f'<div {S}font-size:11px;{C}#666;margin-bottom:4px;">{label}</div>'
                f'<div {S}font-size:20px;font-weight:800;{C}{col};">{val}</div>'
                f'<div {S}font-size:11px;{C}{col};margin-top:3px;">{sub}</div>'
                f'</div>')

    def row(label, val, prev, arr, col):
        td = 'border-bottom:1px solid #1a1a2e;"'
        return (f'<tr>'
                f'<td {S}padding:9px 12px;{C}#888;font-size:13px;{td}>{label}</td>'
                f'<td {S}padding:9px 12px;{C}#fff;font-size:14px;font-weight:700;{td}>{val}</td>'
                f'<td {S}padding:9px 12px;{C}#555;font-size:12px;{td}>{prev}</td>'
                f'<td {S}padding:9px 12px;{C}{col};font-size:13px;font-weight:600;{td}>{arr}</td>'
                f'</tr>')

    h = []
    h.append('<!DOCTYPE html><html><head><meta charset="UTF-8">')
    h.append('<meta name="viewport" content="width=device-width,initial-scale=1.0">')
    h.append(f'<title>ML 360 Cierre {ayer_label}</title></head>')
    h.append('<body style="margin:0;padding:0;background:#0d0d1a;font-family:system-ui,-apple-system,sans-serif;">')
    h.append('<div style="max-width:600px;margin:0 auto;padding:16px;">')

    # Header
    h.append('<div style="background:linear-gradient(135deg,#0d0d2e,#1a1560);border-radius:12px;padding:20px 24px;margin-bottom:16px;border:1px solid #1e1e3a;">')
    h.append('<div style="font-size:22px;font-weight:800;color:#3483FA;">ML 360 SPOTCOMPRAS</div>')
    h.append(f'<div style="font-size:13px;color:#888;margin-top:4px;">Cierre {ayer_label} &middot; {period_cur_label} vs {period_pri_label}</div>')
    h.append(f'<div style="font-size:11px;color:#444;margin-top:2px;">Datos actualizados: {updated} hs</div>')
    h.append('</div>')

    # Seccion 1: Ventas de ayer
    h.append('<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;overflow:hidden;">')
    h.append('<div style="padding:12px 16px;background:linear-gradient(90deg,rgba(0,166,80,.15),transparent);border-bottom:1px solid #1e1e3a;display:flex;align-items:center;justify-content:space-between;">')
    h.append(f'<span style="font-size:13px;font-weight:700;color:#00A650;text-transform:uppercase;letter-spacing:.5px;">VENTAS DE AYER &mdash; {ayer_label}</span>')
    h.append('<span style="font-size:11px;color:#444;">vs mismo dia semana anterior</span>')
    h.append('</div>')
    h.append('<div style="display:flex;gap:10px;padding:14px;flex-wrap:wrap;">')
    h.append(card("GMV",           _fmt_money(ay['gmv']),  ay_gmv_arr, '#00A650'))
    h.append(card("Unidades",      f"{ay['units']:,}",     ay_uni_arr, '#3483FA'))
    h.append(card("Ordenes",       f"{ay['orders']:,}",    ay_ord_arr, '#FFE600'))
    cancelled_col = '#d33' if ay['cancelled'] > 0 else '#00A650'
    h.append(card("Cancelaciones", str(ay['cancelled']),   ay_can_arr, cancelled_col))
    h.append('</div></div>')

    # Seccion 2: Acumulado mes al cierre de ayer
    h.append('<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;overflow:hidden;">')
    h.append('<div style="padding:12px 16px;border-bottom:1px solid #1e1e3a;">')
    h.append(f'<span style="font-size:13px;font-weight:700;color:#3483FA;text-transform:uppercase;letter-spacing:.5px;">ACUMULADO {period_cur_label}</span>')
    h.append(f'<span style="font-size:11px;color:#444;margin-left:8px;">vs {period_pri_label}</span>')
    h.append('</div>')
    h.append('<table style="width:100%;border-collapse:collapse;">')
    h.append('<tr style="background:#0d0d2e;"><td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">METRICA</td>')
    h.append('<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">ACTUAL</td>')
    h.append('<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">ANT.</td>')
    h.append('<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">DELTA</td></tr>')
    h.append(row("GMV",              _fmt_money(gmv_c),   _fmt_money(gmv_p),   gmv_arr,   gmv_col))
    h.append(row("Unidades",         f"{int(units_c):,}", f"{int(units_p):,}", units_arr, units_col))
    h.append(row("Ordenes pagadas",  f"{int(paid_c):,}",  f"{int(paid_p):,}",  paid_arr,  paid_col))
    h.append(row("Neto (GMV-Com.)",  _fmt_money(net_c),   _fmt_money(net_p),   net_arr,   net_col))
    h.append(row("Ticket promedio",  _fmt_money(tick_c),  _fmt_money(tick_p),  tick_arr,  tick_col))
    h.append(row("Tasa cancelacion", f"{crate_c:.1f}%",   f"{crate_p:.1f}%",   cr_arr,    cr_col))
    h.append('</table></div>')

    # Ads
    h.append('<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;">')
    h.append('<div style="font-size:13px;font-weight:700;color:#7B2FF7;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;">ADS DEL PERIODO</div>')
    h.append('<div style="display:flex;gap:10px;flex-wrap:wrap;">')
    h.append(card("Inversion",  inv_str,            '', '#7B2FF7'))
    h.append(card("ROAS",       roas_str,           '', '#00A650'))
    h.append(card("TACOS",      tacos_str,          '', '#FFE600'))
    h.append(card("Comisiones", _fmt_money(fees_c), '', '#F23D4F'))
    h.append('</div></div>')

    # Reputacion
    h.append(f'<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;border-left:4px solid {rep_color};">')
    h.append(f'<div style="font-size:13px;font-weight:700;color:{rep_color};margin-bottom:6px;">REPUTACION</div>')
    h.append(f'<div style="font-size:17px;font-weight:800;color:{rep_color};margin-bottom:4px;">{rep_label}</div>')
    h.append(f'<div style="font-size:12px;color:#666;">{sales60:,} ventas 60d &middot; Reclamos: {claims_pct:.2f}% &middot; Tardios: {delayed_pct:.2f}%</div>')
    h.append('</div>')

    # GMV mensual
    h.append('<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;">')
    h.append('<div style="font-size:13px;font-weight:700;color:#3483FA;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;">GMV MENSUAL 2026</div>')
    h.append(bars)
    h.append('</div>')

    # Footer
    h.append(f'<div style="text-align:center;padding:14px;font-size:11px;color:#333;">')
    h.append(f'ML 360 Dashboard &mdash; SPOTCOMPRAS &mdash; {today_str}<br>')
    h.append('<a href="https://spotcompras.up.railway.app" style="color:#3483FA;text-decoration:none;">Ver dashboard completo</a>')
    h.append('</div>')
    h.append('</div></body></html>')
    return ''.join(h)


def send_email(html_body, config):
    to_list = config.get('to', [])
    if not to_list:
        print("  Sin destinatarios en ml_email_config.json")
        return False
    ayer_label = (date.today() - timedelta(days=1)).strftime('%d/%m/%Y')
    mes_label  = date.today().strftime('%B %Y').capitalize()
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"ML 360 - Cierre {ayer_label} | Acumulado {mes_label} - SPOTCOMPRAS"
    msg['From']    = f"{config.get('from_name', 'ML Dashboard')} <{config['smtp_user']}>"
    msg['To']      = ', '.join(to_list)
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    try:
        with smtplib.SMTP(config['smtp_host'], int(config['smtp_port'])) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(config['smtp_user'], config['smtp_password'])
            srv.sendmail(config['smtp_user'], to_list, msg.as_string())
        print(f"  Email enviado a: {', '.join(to_list)}")
        return True
    except Exception as e:
        print(f"  Error enviando email: {e}")
        return False


def run():
    if not os.path.exists(CFG_FILE):
        print("  Falta ml_email_config.json")
        return False
    with open(CFG_FILE, encoding='utf-8') as f:
        cfg = json.load(f)
    print("\n  Generando email...")
    html = build_email_html()
    return send_email(html, cfg)


if __name__ == '__main__':
    import logging
    LOG_FILE = os.path.join(BASE_DIR, 'email_log.txt')
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    class LogCapture:
        def write(self, msg):
            if msg.strip():
                logging.info(msg.strip())
                sys.__stdout__.write(msg)
        def flush(self):
            sys.__stdout__.flush()
    sys.stdout = LogCapture()
    ok = run()
    logging.info('RESULTADO: OK' if ok else 'RESULTADO: FALLO')
    sys.stdout = sys.__stdout__
    if not ok:
        input("\n  Presiona Enter para cerrar...")
