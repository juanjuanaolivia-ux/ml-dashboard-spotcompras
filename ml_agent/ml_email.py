#!/usr/bin/env python3
"""
ml_email.py — Resumen diario ML 360°
Sección 1: Ventas del día anterior (GMV, unidades, órdenes, cancelaciones)
Sección 2: Acumulado del mes vs mes anterior
Sección 3: Ads, Reputación, Evolución anual
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
        return "—", "#888"
    if pct > 0:
        return f"▲ {pct:.1f}%", ("#d33" if inv else "#00A650")
    elif pct < 0:
        return f"▼ {abs(pct):.1f}%", ("#00A650" if inv else "#d33")
    return "= 0%", "#888"


def _day_stats(orders, day_str):
    """GMV, unidades, ordenes pagadas y canceladas de un dia (prefijo YYYY-MM-DD)."""
    paid = [o for o in orders if o.get('date_created', '').startswith(day_str) and o.get('status') == 'paid']
    canc = [o for o in orders if o.get('date_created', '').startswith(day_str) and o.get('status') == 'cancelled']
    gmv   = sum(o.get('total_amount', 0) for o in paid)
    units = sum(sum(it.get('quantity', 1) for it in (o.get('items') or [])) for o in paid)
    return {'gmv': gmv, 'orders': len(paid), 'units': units, 'cancelled': len(canc)}


def build_email_html():
    mc      = _load('metrics_current.json')
    mp      = _load('metrics_prior.json')
    summary = _load('summary.json')
    rep     = _load('reputation.json')
    ads_m   = _load('ads_manual.json')
    monthly = _load('monthly_2026.json')
    orders  = _load('orders_current.json')
    if not isinstance(orders, list):
        orders = []

    # Fechas
    today      = date.today()
    ayer       = today - timedelta(days=1)
    ayer_str   = ayer.strftime('%Y-%m-%d')
    ayer_label = ayer.strftime('%d/%m/%Y')
    semana_ant = (ayer - timedelta(days=7)).strftime('%Y-%m-%d')
    today_str  = today.strftime('%d/%m/%Y')
    period_cur = summary.get('period_cur_label', 'Mes actual')
    period_pri = summary.get('period_pri_label', 'Mes anterior')
    period_cur_label = f"{period_cur} al {ayer_label}"  # siempre cierre de día
    updated    = summary.get('updated_at', '')[:16].replace('T', ' ')

    # Ventas de ayer
    ay = _day_stats(orders, ayer_str)
    sw = _day_stats(orders, semana_ant)
    ay_gmv_pct, ay_gmv_col   = _arrow(_delta(ay['gmv'],       sw['gmv']))
    ay_ord_pct, ay_ord_col   = _arrow(_delta(ay['orders'],    sw['orders']))
    ay_uni_pct, ay_uni_col   = _arrow(_delta(ay['units'],     sw['units']))
    ay_can_pct, ay_can_col   = _arrow(_delta(ay['cancelled'], sw['cancelled']), inv=True)

    # Acumulado mes al CIERRE DE AYER (excluir datos parciales de hoy)
    # Filtrar órdenes hasta ayer inclusive — siempre días cerrados
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

    gmv_p   = mp.get('gmv', 0) or 0
    units_p = mp.get('units', 0) or 0
    paid_p  = mp.get('paid', 0) or 0
    net_p   = mp.get('net', 0) or 0
    tick_p  = mp.get('avg_ticket', 0) or 0
    crate_p = mp.get('cancel_rate', 0) or 0

    gmv_pct,   gmv_col   = _arrow(_delta(gmv_c, gmv_p))
    units_pct, units_col = _arrow(_delta(units_c, units_p))
    paid_pct,  paid_col  = _arrow(_delta(paid_c, paid_p))
    net_pct,   net_col   = _arrow(_delta(net_c, net_p))
    tick_pct,  tick_col  = _arrow(_delta(tick_c, tick_p))
    cr_pct,    cr_col    = _arrow(_delta(crate_c, crate_p), inv=True)

    # Reputacion
    rep_status  = rep.get('power_seller_status', '')
    rep_label   = {'platinum': 'MercadoLider Platinum', 'gold': 'MercadoLider Gold',
                   'silver': 'MercadoLider Silver'}.get(rep_status, rep_status.title() or '-')
    rep_color   = {'platinum': '#00d4e4', 'gold': '#FFD700', 'silver': '#A0A0A0'}.get(rep_status, '#aaa')
    claims_pct  = (rep.get('claims_rate', 0) or 0) * 100
    delayed_pct = (rep.get('delayed_rate', 0) or 0) * 100
    sales60     = rep.get('sales_60d', 0) or 0

    # Ads
    roas_str = tacos_str = inv_str = '-'
    if ads_m:
        _inv = ads_m.get('inversion', 0) or 0
        _rev = ads_m.get('ingresos', 0) or 0
        if _inv and _rev:
            roas_str  = f"{_rev/_inv:.1f}x"
            tacos_str = f"{_inv/_rev*100:.1f}%"
            inv_str   = _fmt_money(_inv)

    # Barras GMV mensual
    if isinstance(monthly, list) and monthly:
        max_gmv = max(m.get('gmv', 0) for m in monthly) or 1
        bars_html = '<table style="width:100%;border-collapse:collapse;">'
        for m in monthly:
            lbl   = m.get('label', '')
            gv    = m.get('gmv', 0) or 0
            pct   = int(gv / max_gmv * 100)
            color = '#FFE600' if m == monthly[-1] else '#3483FA'
            bars_html += (
                '<tr>'
                f'<td style="padding:3px 6px;font-size:11px;color:#aaa;white-space:nowrap;width:50px;">{lbl}</td>'
                f'<td style="padding:3px 6px;width:100%;"><div style="background:{color};height:13px;width:{pct}%;border-radius:3px;min-width:4px;"></div></td>'
                f'<td style="padding:3px 6px;font-size:11px;color:#ccc;white-space:nowrap;">{_fmt_money(gv)}</td>'
                '</tr>'
            )
        bars_html += '</table>'
    else:
        bars_html = '<p style="color:#666;font-size:12px;">Sin datos</p>'

    # Helpers
    def kpi_card(label, val, sub, col='#fff'):
        return (
            '<div style="flex:1;min-width:120px;background:#0d0d2e;border-radius:8px;padding:14px 12px;text-align:center;border:1px solid #1e1e3a;">'
            f'<div style="font-size:11px;color:#666;margin-bottom:4px;">{label}</div>'
            f'<div style="font-size:20px;font-weight:800;color:{col};">{val}</div>'
            f'<div style="font-size:11px;color:#555;margin-top:3px;">{sub}</div>'
            '</div>'
        )

    def kpi_row(label, val, prev, arr, col):
        return (
            '<tr>'
            f'<td style="padding:9px 12px;color:#888;font-size:13px;border-bottom:1px solid #1a1a2e;">{label}</td>'
            f'<td style="padding:9px 12px;color:#fff;font-size:14px;font-weight:700;border-bottom:1px solid #1a1a2e;">{val}</td>'
            f'<td style="padding:9px 12px;color:#555;font-size:12px;border-bottom:1px solid #1a1a2e;">{prev}</td>'
            f'<td style="padding:9px 12px;color:{col};font-size:13px;font-weight:600;border-bottom:1px solid #1a1a2e;">{arr}</td>'
            '</tr>'
        )

    html = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        f'<title>ML 360 {today_str}</title>'
        '</head><body style="margin:0;padding:0;background:#0d0d1a;font-family:system-ui,-apple-system,sans-serif;">'
        '<div style="max-width:600px;margin:0 auto;padding:16px;">'

        # Header
        '<div style="background:linear-gradient(135deg,#0d0d2e,#1a1560);border-radius:12px;padding:20px 24px;margin-bottom:16px;border:1px solid #1e1e3a;">'
        '<div style="font-size:22px;font-weight:800;color:#3483FA;letter-spacing:-.3px;">ML 360 - SPOTCOMPRAS</div>'
        f'<div style="font-size:13px;color:#888;margin-top:4px;">Cierre {ayer_label} · {period_cur_label} vs {period_pri}</div>'
        f'<div style="font-size:11px;color:#444;margin-top:2px;">Datos actualizados: {updated} hs</div>'
        '</div>'

        # SECCION 1: Ventas de ayer
        '<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;overflow:hidden;">'
        '<div style="padding:12px 16px;background:linear-gradient(90deg,rgba(0,166,80,.15),transparent);border-bottom:1px solid #1e1e3a;display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="font-size:13px;font-weight:700;color:#00A650;text-transform:uppercase;letter-spacing:.5px;">VENTAS DE AYER - {ayer_label}</span>'
        '<span style="font-size:11px;color:#444;">vs mismo dia semana anterior</span>'
        '</div>'
        '<div style="display:flex;gap:10px;padding:14px;flex-wrap:wrap;">'
        + kpi_card("GMV", _fmt_money(ay['gmv']), ay_gmv_pct, '#00A650')
        + kpi_card("Unidades", f"{ay['units']:,}", ay_uni_pct, '#3483FA')
        + kpi_card("Ordenes", f"{ay['orders']:,}", ay_ord_pct, '#FFE600')
        + kpi_card("Cancelaciones", f"{ay['cancelled']}", ay_can_pct, '#d33' if ay['cancelled'] > 0 else '#00A650')
        + '</div></div>'

        # SECCION 2: Acumulado mes
        '<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;overflow:hidden;">'
        '<div style="padding:12px 16px;border-bottom:1px solid #1e1e3a;">'
        f'<span style="font-size:13px;font-weight:700;color:#3483FA;text-transform:uppercase;letter-spacing:.5px;">ACUMULADO {period_cur_label}</span>'
        f'<span style="font-size:11px;color:#444;margin-left:8px;">vs {period_pri}</span>'
        '</div>'
        '<table style="width:100%;border-collapse:collapse;">'
        '<tr style="background:#0d0d2e;">'
        '<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">METRICA</td>'
        '<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">ACTUAL</td>'
        '<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">ANT.</td>'
        '<td style="padding:8px 12px;font-size:11px;color:#444;font-weight:600;">DELTA</td>'
        '</tr>'
        + kpi_row("GMV", _fmt_money(gmv_c), _fmt_money(gmv_p), gmv_pct, gmv_col)
        + kpi_row("Unidades", f"{int(units_c):,}", f"{int(units_p):,}", units_pct, units_col)
        + kpi_row("Ordenes pagadas", f"{int(paid_c):,}", f"{int(paid_p):,}", paid_pct, paid_col)
        + kpi_row("Neto (GMV-Com.)", _fmt_money(net_c), _fmt_money(net_p), net_pct, net_col)
        + kpi_row("Ticket promedio", _fmt_money(tick_c), _fmt_money(tick_p), tick_pct, tick_col)
        + kpi_row("Tasa cancelacion", f"{crate_c:.1f}%", f"{crate_p:.1f}%", cr_pct, cr_col)
        + '</table></div>'

        # Ads
        '<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;">'
        '<div style="font-size:13px;font-weight:700;color:#7B2FF7;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;">ADS DEL PERIODO</div>'
        '<div style="display:flex;gap:10px;flex-wrap:wrap;">'
        + kpi_card("Inversion", inv_str, "", '#7B2FF7')
        + kpi_card("ROAS", roas_str, "", '#00A650')
        + kpi_card("TACOS", tacos_str, "", '#FFE600')
        + kpi_card("Comisiones", _fmt_money(fees_c), "", '#F23D4F')
        + '</div></div>'

        # Reputacion
        f'<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;border-left:4px solid {rep_color};">'
        f'<div style="font-size:13px;font-weight:700;color:{rep_color};margin-bottom:6px;">REPUTACION</div>'
        f'<div style="font-size:17px;font-weight:800;color:{rep_color};margin-bottom:4px;">{rep_label}</div>'
        f'<div style="font-size:12px;color:#666;">{sales60:,} ventas 60d - Reclamos: {claims_pct:.2f}% - Tardios: {delayed_pct:.2f}%</div>'
        '</div>'

        # GMV Mensual
        '<div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;">'
        '<div style="font-size:13px;font-weight:700;color:#3483FA;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;">GMV MENSUAL 2026</div>'
        + bars_html
        + '</div>'

        # Footer
        f'<div style="text-align:center;padding:14px;font-size:11px;color:#333;">'
        f'ML 360 Dashboard - SPOTCOMPRAS - {today_str}<br>'
        '<a href="https://spotcompras.up.railway.app" style="color:#3483FA;text-decoration:none;">Ver dashboard completo</a>'
        '</div>'

        '</div></body></html>'
    )
    return html


def send_email(html_body, config):
    to_list = config.get('to', [])
    if not to_list:
        print("  Sin destinatarios en ml_email_config.json")
        return False

    ayer = (date.today() - timedelta(days=1)).strftime('%d/%m/%Y')
    mes  = date.today().strftime('%B').capitalize()
    msg  = MIMEMultipart('alternative')
    msg['Subject'] = f"ML 360 - Ventas {ayer} - Acumulado {mes} - SPOTCOMPRAS"
    msg['From']    = f"{config.get('from_name','ML Dashboard')} <{config['smtp_user']}>"
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


def _refresh_data():
    """Refresca los datos desde la API de ML antes de generar el email."""
    import sys as _sys
    _sys.path.insert(0, BASE_DIR)
    try:
        from ml_main import fetch_and_compute
        print("  Actualizando datos desde ML API...")
        fetch_and_compute()
        print("  Datos actualizados OK")
        return True
    except Exception as e:
        print(f"  Advertencia: no se pudo actualizar datos: {e}")
        return False


def run():
    if not os.path.exists(CFG_FILE):
        print("  Falta ml_email_config.json")
        return False
    with open(CFG_FILE, encoding='utf-8') as f:
        cfg = json.load(f)
    _refresh_data()
    print("\n  Generando email...")
    html = build_email_html()
    return send_email(html, cfg)


if __name__ == '__main__':
    import logging
    LOG_FILE = os.path.join(BASE_DIR, 'email_log.txt')
    logging.basicConfig(
        filename=LOG_FILE, level=logging.INFO,
        format='%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    )
    class LogCapture:
        def write(self, msg):
            if msg.strip():
                logging.info(msg.strip())
                sys.__stdout__.write(msg)
        def flush(self): sys.__stdout__.flush()
    sys.stdout = LogCapture()
    ok = run()
    logging.info('RESULTADO: OK' if ok else 'RESULTADO: FALLO')
    sys.stdout = sys.__stdout__
    if not ok:
        input("\n  Presiona Enter para cerrar...")
