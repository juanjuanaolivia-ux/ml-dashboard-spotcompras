"""
ml_main.py — Orquestador principal del agente Mercado Libre
Corre automaticamente: fetch datos (mes actual + mes anterior) -> genera dashboard 360

Uso:
  python ml_main.py              -> pipeline completo
  python ml_main.py --only-dash  -> solo regenera el dashboard
  python ml_main.py --check      -> verifica conexion
"""
import sys, os, json, calendar
from datetime import datetime, date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)


def _save(name, data):
    with open(os.path.join(DATA_DIR, f'{name}.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def _load(name):
    p = os.path.join(DATA_DIR, f'{name}.json')
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def fetch_and_compute():
    """Descarga ordenes mes actual + mes anterior, evolutivo 2026, computa metricas."""
    sys.path.insert(0, SCRIPT_DIR)
    from ml_auth import MLSession
    from ml_data import (fetch_orders_range, fetch_items,
                         compute_metrics, enrich_metrics,
                         fetch_category_names, fetch_monthly_evolution_2026,
                         process_status_xlsx, load_sku_categories)

    session = MLSession()
    today   = date.today()

    cur_year, cur_month = today.year, today.month
    if cur_month == 1:
        pri_year, pri_month = cur_year - 1, 12
    else:
        pri_year, pri_month = cur_year, cur_month - 1

    cur_from = date(cur_year, cur_month, 1)
    cur_to   = today
    pri_from = date(pri_year, pri_month, 1)
    pri_day  = min(today.day, calendar.monthrange(pri_year, pri_month)[1])
    pri_to   = date(pri_year, pri_month, pri_day)

    def iso(d, end=False):
        t = "23:59:59" if end else "00:00:00"
        return f"{d.strftime('%Y-%m-%d')}T{t}.000-00:00"

    print(f"\n  Periodo actual:   {cur_from} -> {cur_to}")
    print(f"  Periodo anterior: {pri_from} -> {pri_to}")

    cur_raw = fetch_orders_range(session, iso(cur_from), iso(cur_to, True), "Mes actual")
    pri_raw = fetch_orders_range(session, iso(pri_from), iso(pri_to, True), "Mes anterior")

    _save('orders_current', cur_raw)
    _save('orders_prior',   pri_raw)

    mc = compute_metrics(cur_raw)
    mp = compute_metrics(pri_raw)
    _save('metrics_current', mc)
    _save('metrics_prior',   mp)

    items = fetch_items(session)
    _save('items', items)

    ec = enrich_metrics(cur_raw, items)
    ep = enrich_metrics(pri_raw, items)

    all_cats = set(list(ec.get('by_category', {}).keys()) +
                   list(ep.get('by_category', {}).keys()))
    cat_names = fetch_category_names(session, list(all_cats)[:30])
    for d in [ec, ep]:
        for cid, v in d.get('by_category', {}).items():
            v['name'] = cat_names.get(cid, cid)
    _save('enrich_current', ec)
    _save('enrich_prior',   ep)
    _save('cat_names',      cat_names)

    existing_monthly = _load('monthly_2026') or []
    fetch_monthly_evolution_2026(session, existing=existing_monthly)

    dash_dir = os.path.join(SCRIPT_DIR, 'dashboards')
    status_path = os.path.join(dash_dir, 'STATUS.xlsx')
    if os.path.exists(status_path):
        process_status_xlsx(status_path)

    cat_sku_path = os.path.join(dash_dir, 'Categoria y subcategoria por codigo.xlsx')
    if os.path.exists(cat_sku_path):
        sku_cats = load_sku_categories(cat_sku_path)
        _save('sku_categories', sku_cats)

    MONTH_ES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    summary = {
        'updated_at':       datetime.now().isoformat(),
        'period_cur':       f"{cur_from} -> {cur_to}",
        'period_pri':       f"{pri_from} -> {pri_to}",
        'period_cur_label': f"{MONTH_ES[cur_month]} {cur_year}",
        'period_pri_label': f"{MONTH_ES[pri_month]} {pri_year} (1-{pri_day})",
        'orders_current':   len(cur_raw),
        'orders_prior':     len(pri_raw),
        'items':            len(items),
    }
    _save('summary', summary)

    print(f"\n  OK Datos listos:")
    print(f"     Mes actual:   {len(cur_raw)} ordenes | GMV ${mc.get('gmv',0):,.0f}")
    print(f"     Mes anterior: {len(pri_raw)} ordenes | GMV ${mp.get('gmv',0):,.0f}")

    # ── Liquidaciones & Conciliación ────────────────────────────────────────
    try:
        from ml_liquidaciones import run as run_liquidaciones
        print("\n  Actualizando Liquidaciones...")
        run_liquidaciones(session=session)
    except Exception as e:
        print(f"\n  [liquidaciones] Error (no crítico): {e}")

    # ── Balance MP (dinero en cuenta / a cobrar / retenido) ──────────────────
    try:
        from fetch_mp_balance import run as run_mp_balance
        print("\n  Actualizando balance MP...")
        run_mp_balance()
    except Exception as e:
        print(f"\n  [mp_balance] Error (no crítico): {e}")

    return summary


def _push_dashboard_to_railway(dashboard_path):
    """
    Envia el HTML generado directamente a Railway via HTTP POST.
    Sin git, sin credenciales de GitHub.
    Lee de ml_email_config.json:
        railway_url:        https://spotcompras.up.railway.app
        railway_update_key: clave secreta (DASHBOARD_UPDATE_KEY en Railway)
    """
    import urllib.request, urllib.error

    cfg_path = os.path.join(SCRIPT_DIR, 'ml_email_config.json')
    if not os.path.exists(cfg_path):
        return
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)

    url = cfg.get('railway_url', '').rstrip('/')
    key = cfg.get('railway_update_key', '')
    if not url or not key:
        print("  [railway] railway_url / railway_update_key no configurados -- skip")
        return

    endpoint = f"{url}/update"
    with open(dashboard_path, 'rb') as f:
        html_bytes = f.read()

    req = urllib.request.Request(
        endpoint,
        data=html_bytes,
        headers={
            'X-Update-Key': key,
            'Content-Type': 'text/html; charset=utf-8',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode()
            print(f"  [railway] Dashboard subido a Railway OK | {body}")
    except urllib.error.HTTPError as e:
        print(f"  [railway] Error HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"  [railway] Error al subir dashboard: {e}")


def main():
    args      = sys.argv[1:]
    only_dash = '--only-dash' in args
    check     = '--check' in args
    send_mail = '--send-email' in args or '--email' in args
    no_email  = '--no-email' in args

    print(f"\n{'='*55}")
    print(f"  ML AGENT -- {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    if check:
        sys.path.insert(0, SCRIPT_DIR)
        from ml_setup import check_setup
        sys.exit(0 if check_setup() else 1)

    if not only_dash:
        fetch_and_compute()

    sys.path.insert(0, SCRIPT_DIR)
    from ml_dashboard import build_dashboard
    out = build_dashboard()

    # Post-process: calendar picker + global hover effects
    try:
        import importlib.util, sys as _sys
        _spec = importlib.util.spec_from_file_location(
            "postprocess_dashboard",
            os.path.join(SCRIPT_DIR, "postprocess_dashboard.py"))
        _pp = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_pp)
        _pp.run()
        print("  ✅ Post-procesado (calendar + hover) aplicado")
    except Exception as _e:
        print(f"  ⚠️  Post-procesado opcional falló: {_e}")

    print(f"\n  {'='*40}")
    print(f"  OK DASHBOARD ACTUALIZADO")
    print(f"  {out}")
    print(f"  {'='*40}\n")

    email_cfg = os.path.join(SCRIPT_DIR, 'ml_email_config.json')
    if not no_email and os.path.exists(email_cfg):
        with open(email_cfg, encoding='utf-8') as f:
            ecfg = json.load(f)
        if ecfg.get('smtp_user', '').endswith('@gmail.com') and \
           not ecfg['smtp_user'].startswith('TU_CUENTA') and \
           ecfg.get('smtp_password', '').replace('x', '').replace(' ', '') != '':
            from ml_email import run as send_report
            send_report()
        elif send_mail:
            print("  Configura ml_email_config.json con tus credenciales reales de Gmail.")

    _push_dashboard_to_railway(out)


if __name__ == '__main__':
    main()
