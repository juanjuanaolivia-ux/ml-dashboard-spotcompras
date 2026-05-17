#!/usr/bin/env python3
"""
ml_email.py — Envío automático del resumen diario ML 360°
Genera un email HTML mobile-friendly con KPIs del día y lo envía por SMTP.

Config: ml_email_config.json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "tu_cuenta@gmail.com",
  "smtp_password": "xxxx xxxx xxxx xxxx",   ← App Password de Google
  "from_name": "ML Dashboard SPOTCOMPRAS",
  "to": ["jsantiago@spotcompras.com"]
}
"""
import json, os, smtplib, math
from datetime import datetime, date
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
        return f"${v/1_000_000:.1f}M"
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


def build_email_html():
    mc = _load('metrics_current.json')
    mp = _load('metrics_prior.json')
    summary = _load('summary.json')
    reputation = _load('reputation.json')
    ads_manual = _load('ads_manual.json')
    monthly = _load('monthly_2026.json')

    period_cur = summary.get('period_cur_label', 'Mes actual')
    period_pri = summary.get('period_pri_label', 'Mes anterior')
    updated = summary.get('updated_at', '')[:16].replace('T', ' ')
    today_str = date.today().strftime('%d/%m/%Y')

    # KPIs
    gmv_c   = mc.get('gmv', 0) or 0
    gmv_p   = mp.get('gmv', 0) or 0
    units_c = mc.get('units', 0) or 0
    units_p = mp.get('units', 0) or 0
    paid_c  = mc.get('paid', 0) or 0
    paid_p  = mp.get('paid', 0) or 0
    net_c   = mc.get('net', 0) or 0
    net_p   = mp.get('net', 0) or 0
    fees_c  = mc.get('fees', 0) or 0
    tick_c  = mc.get('avg_ticket', 0) or 0
    tick_p  = mp.get('avg_ticket', 0) or 0
    crate_c = mc.get('cancel_rate', 0) or 0
    crate_p = mp.get('cancel_rate', 0) or 0

    gmv_pct,   gmv_col   = _arrow(_delta(gmv_c, gmv_p))
    units_pct, units_col = _arrow(_delta(units_c, units_p))
    paid_pct,  paid_col  = _arrow(_delta(paid_c, paid_p))
    net_pct,   net_col   = _arrow(_delta(net_c, net_p))
    tick_pct,  tick_col  = _arrow(_delta(tick_c, tick_p))
    cr_pct,    cr_col    = _arrow(_delta(crate_c, crate_p), inv=True)

    # Evolutivo mes actual
    months_label = [m.get('label', '') for m in (monthly or [])]
    months_gmv   = [m.get('gmv', 0) or 0 for m in (monthly or [])]

    # Reputation
    rep_status = reputation.get('power_seller_status', '')
    rep_label  = {'platinum': 'MercadoLíder Platinum', 'gold': 'MercadoLíder Gold',
                  'silver': 'MercadoLíder Silver'}.get(rep_status, rep_status.title() if rep_status else '—')
    rep_color  = {'platinum': '#00d4e4', 'gold': '#FFD700', 'silver': '#A0A0A0'}.get(rep_status, '#aaa')
    claims_pct = (reputation.get('claims_rate', 0) or 0) * 100
    delayed_pct = (reputation.get('delayed_rate', 0) or 0) * 100
    sales60    = reputation.get('sales_60d', 0) or 0

    # Ads (manual)
    roas_str, tacos_str, inv_str = '—', '—', '—'
    if ads_manual:
        _inv = ads_manual.get('inversion', 0) or 0
        _rev = ads_manual.get('ingresos', 0) or 0
        if _inv and _rev:
            roas_str  = f"{_rev/_inv:.1f}x"
            tacos_str = f"{_inv/_rev*100:.1f}%"
            inv_str   = _fmt_money(_inv)

    # --- HTML Email ---
    kpi_row = lambda label, val, prev, arr, col: f'''
      <tr>
        <td style="padding:10px 12px;color:#888;font-size:13px;border-bottom:1px solid #222;">{label}</td>
        <td style="padding:10px 12px;color:#fff;font-size:14px;font-weight:700;border-bottom:1px solid #222;">{val}</td>
        <td style="padding:10px 12px;color:#666;font-size:12px;border-bottom:1px solid #222;">{prev}</td>
        <td style="padding:10px 12px;color:{col};font-size:13px;font-weight:600;border-bottom:1px solid #222;">{arr}</td>
      </tr>'''

    # Build month bars (simple text chart)
    if months_gmv:
        max_gmv = max(months_gmv) or 1
        bars_html = '<table style="width:100%;border-collapse:collapse;">'
        for lbl, gv in zip(months_label, months_gmv):
            pct = int(gv / max_gmv * 100)
            color = '#3483FA' if lbl != months_label[-1] else '#FFE600'
            bars_html += f'''<tr>
              <td style="padding:3px 6px;font-size:11px;color:#aaa;white-space:nowrap;width:60px;">{lbl}</td>
              <td style="padding:3px 6px;"><div style="background:{color};height:14px;width:{pct}%;border-radius:3px;min-width:4px;"></div></td>
              <td style="padding:3px 6px;font-size:11px;color:#ccc;white-space:nowrap;">{_fmt_money(gv)}</td>
            </tr>'''
        bars_html += '</table>'
    else:
        bars_html = '<p style="color:#666;font-size:12px;">Sin datos de evolución</p>'

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ML 360° — {today_str}</title>
</head>
<body style="margin:0;padding:0;background:#0d0d1a;font-family:system-ui,-apple-system,sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:16px;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0d0d2e,#151540);border-radius:12px;padding:20px 24px;margin-bottom:16px;border:1px solid #1e1e3a;">
      <div style="font-size:22px;font-weight:700;color:#3483FA;">ML 360° — SPOTCOMPRAS</div>
      <div style="font-size:13px;color:#888;margin-top:4px;">Resumen {today_str} · {period_cur} vs {period_pri}</div>
      <div style="font-size:11px;color:#555;margin-top:2px;">Actualizado: {updated}</div>
    </div>

    <!-- KPIs principales -->
    <div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;overflow:hidden;">
      <div style="padding:14px 16px;font-size:13px;font-weight:700;color:#3483FA;border-bottom:1px solid #1e1e3a;text-transform:uppercase;letter-spacing:.5px;">
        📊 KPIs Principales
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <tr style="background:#0d0d2e;">
          <td style="padding:8px 12px;font-size:11px;color:#555;font-weight:600;">MÉTRICA</td>
          <td style="padding:8px 12px;font-size:11px;color:#555;font-weight:600;">HOY</td>
          <td style="padding:8px 12px;font-size:11px;color:#555;font-weight:600;">MES ANT.</td>
          <td style="padding:8px 12px;font-size:11px;color:#555;font-weight:600;">Δ</td>
        </tr>
        {kpi_row("GMV", _fmt_money(gmv_c), _fmt_money(gmv_p), gmv_pct, gmv_col)}
        {kpi_row("Unidades", f"{int(units_c):,}", f"{int(units_p):,}", units_pct, units_col)}
        {kpi_row("Órdenes pagadas", f"{int(paid_c):,}", f"{int(paid_p):,}", paid_pct, paid_col)}
        {kpi_row("Neto (GMV-Com.)", _fmt_money(net_c), _fmt_money(net_p), net_pct, net_col)}
        {kpi_row("Ticket promedio", _fmt_money(tick_c), _fmt_money(tick_p), tick_pct, tick_col)}
        {kpi_row("Tasa cancelación", f"{crate_c:.1f}%", f"{crate_p:.1f}%", cr_pct, cr_col)}
      </table>
    </div>

    <!-- Ads -->
    <div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;">
      <div style="font-size:13px;font-weight:700;color:#7B2FF7;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;">⚡ Ads del Período</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <div style="flex:1;min-width:120px;background:#0d0d2e;border-radius:8px;padding:12px;text-align:center;">
          <div style="font-size:11px;color:#666;">Inversión</div>
          <div style="font-size:18px;font-weight:700;color:#7B2FF7;">{inv_str}</div>
        </div>
        <div style="flex:1;min-width:120px;background:#0d0d2e;border-radius:8px;padding:12px;text-align:center;">
          <div style="font-size:11px;color:#666;">ROAS</div>
          <div style="font-size:18px;font-weight:700;color:#00A650;">{roas_str}</div>
        </div>
        <div style="flex:1;min-width:120px;background:#0d0d2e;border-radius:8px;padding:12px;text-align:center;">
          <div style="font-size:11px;color:#666;">TACOS</div>
          <div style="font-size:18px;font-weight:700;color:#FFE600;">{tacos_str}</div>
        </div>
        <div style="flex:1;min-width:120px;background:#0d0d2e;border-radius:8px;padding:12px;text-align:center;">
          <div style="font-size:11px;color:#666;">Comisiones</div>
          <div style="font-size:18px;font-weight:700;color:#F23D4F;">{_fmt_money(fees_c)}</div>
        </div>
      </div>
    </div>

    <!-- Reputación -->
    <div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;border-left:4px solid {rep_color};">
      <div style="font-size:13px;font-weight:700;color:{rep_color};margin-bottom:8px;">🏅 Reputación</div>
      <div style="font-size:16px;font-weight:700;color:{rep_color};margin-bottom:4px;">{rep_label}</div>
      <div style="font-size:12px;color:#888;">{sales60:,} ventas · Reclamos: {claims_pct:.2f}% · Envíos tardíos: {delayed_pct:.2f}%</div>
    </div>

    <!-- Evolución 2026 -->
    <div style="background:#151528;border-radius:12px;border:1px solid #1e1e3a;margin-bottom:16px;padding:16px;">
      <div style="font-size:13px;font-weight:700;color:#3483FA;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px;">📈 GMV Mensual 2026</div>
      {bars_html}
    </div>

    <!-- Footer -->
    <div style="text-align:center;padding:16px;font-size:11px;color:#444;">
      ML 360° Dashboard · SPOTCOMPRAS · Generado automáticamente<br>
      {today_str}
    </div>

  </div>
</body>
</html>"""
    return html


def send_email(html_body: str, config: dict) -> bool:
    """Envía el email usando la config SMTP."""
    to_list = config.get('to', [])
    if not to_list:
        print("  ❌ No hay destinatarios configurados en ml_email_config.json")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"ML 360° — Resumen {date.today().strftime('%d/%m/%Y')} · SPOTCOMPRAS"
    msg['From']    = f"{config.get('from_name','ML Dashboard')} <{config['smtp_user']}>"
    msg['To']      = ', '.join(to_list)

    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(config['smtp_host'], int(config['smtp_port'])) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(config['smtp_user'], config['smtp_password'])
            srv.sendmail(config['smtp_user'], to_list, msg.as_string())
        print(f"  ✅ Email enviado a: {', '.join(to_list)}")
        return True
    except Exception as e:
        print(f"  ❌ Error enviando email: {e}")
        return False


def run():
    """Entry point: genera HTML y envía el email."""
    if not os.path.exists(CFG_FILE):
        print(f"\n  ⚠️  Falta ml_email_config.json. Creá el archivo con:")
        print("""  {
    "smtp_host":     "smtp.gmail.com",
    "smtp_port":     587,
    "smtp_user":     "tu_cuenta@gmail.com",
    "smtp_password": "xxxx xxxx xxxx xxxx",
    "from_name":     "ML Dashboard SPOTCOMPRAS",
    "to":            ["jsantiago@spotcompras.com"]
  }""")
        print("\n  → Para Gmail: activá 2FA y generá un App Password en myaccount.google.com/apppasswords")
        return False

    with open(CFG_FILE, encoding='utf-8') as f:
        cfg = json.load(f)

    print("\n  📧 Generando email...")
    html = build_email_html()
    return send_email(html, cfg)


if __name__ == '__main__':
    import logging
    LOG_FILE = os.path.join(BASE_DIR, 'email_log.txt')
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
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
        input("\n  Presioná Enter para cerrar...")  # mantiene la ventana abierta si hay error
