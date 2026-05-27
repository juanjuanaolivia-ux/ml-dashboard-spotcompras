#!/usr/bin/env python3
"""
run_daily.py  v3
Orquestador diario ML 360
Pipeline: fetch -> dashboard -> postprocess -> deploy Railway -> email

Timeout: watchdog thread daemon (Windows-compatible).
Lock file: evita runs concurrentes via fcntl (Linux) o msvcrt (Windows).
Logging granular: cada sub-paso de PASO 1 tiene su propia linea de log.
"""
import sys, os, json, signal, time
from datetime import datetime

BASE     = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE, 'ml_run.log')

def log(msg):
    ts   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"{ts}  {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


# --------------------------------------------------------------------------
# Lock file: evita ejecuciones concurrentes
# --------------------------------------------------------------------------

_LOCK_FILE = os.path.join(BASE, 'run.lock')
_lock_fh = None

def _acquire_lock():
    global _lock_fh
    _lock_fh = open(_LOCK_FILE, 'w')
    try:
        if sys.platform == 'win32':
            import msvcrt
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl as _fcntl
            _fcntl.flock(_lock_fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
    except (IOError, OSError):
        log("LOCK: otra instancia ya esta corriendo (PID en run.lock). Saliendo.")
        sys.exit(0)

def _release_lock():
    global _lock_fh
    if _lock_fh:
        try:
            if sys.platform == 'win32':
                import msvcrt
                _lock_fh.seek(0)
                msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl as _fcntl
                _fcntl.flock(_lock_fh, _fcntl.LOCK_UN)
            _lock_fh.close()
        except Exception:
            pass
        _lock_fh = None
    try:
        os.remove(_LOCK_FILE)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Timeout robusto: watchdog thread Windows-compatible
# --------------------------------------------------------------------------

import threading as _threading

def _timeout_watchdog(seconds, label="TIMEOUT"):
    """
    Lanza un timer daemon que mata el proceso si no se cancela a tiempo.
    Compatible con Windows y Linux (no usa SIGALRM).
    Uso:
        wd = _timeout_watchdog(1200, "PASO1 TIMEOUT")
        ... trabajo ...
        wd.cancel()
    """
    def _kill():
        log(f"{label}: timeout de {seconds}s alcanzado. Terminando proceso.")
        _release_lock()
        os._exit(1)
    t = _threading.Timer(seconds, _kill)
    t.daemon = True
    t.start()
    return t

def run_with_timeout(fn, timeout_secs, label=""):
    """
    Ejecuta fn() con un timeout via watchdog thread.
    Bloquea el hilo actual hasta que fn() termina o se agota el tiempo.
    """
    result = [None]; error = [None]
    def target():
        try: result[0] = fn()
        except Exception as e: error[0] = e
    t = _threading.Thread(target=target, daemon=True)
    wd = _timeout_watchdog(timeout_secs, f"{label} TIMEOUT")
    t.start()
    t.join(timeout_secs + 5)   # margen extra; el watchdog ya mato el proceso si colgo
    wd.cancel()
    if t.is_alive():
        raise TimeoutError(f"{label} excedio {timeout_secs//60}m{timeout_secs%60}s")
    if error[0]: raise error[0]
    return result[0]


# --------------------------------------------------------------------------
# PASO 1: fetch granular con logging por sub-paso
# --------------------------------------------------------------------------

def _fetch_all():
    """
    Reemplaza fetch_and_compute() con logging granular de cada sub-paso,
    para saber exactamente cual se cuelga.
    """
    sys.path.insert(0, BASE)
    import calendar
    from datetime import date
    from ml_auth import MLSession
    from ml_data import (fetch_orders_range, fetch_items, compute_metrics,
                         enrich_metrics, fetch_category_names,
                         fetch_monthly_evolution_2026, process_status_xlsx,
                         load_sku_categories, compute_postventa,
                         fetch_reputation, fetch_ads_data)
    import json as _json

    def _save(name, data):
        os.makedirs(os.path.join(BASE, 'data'), exist_ok=True)
        p = os.path.join(BASE, 'data', f'{name}.json')
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            _json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, p)  # atómico — evita truncación si el proceso muere mid-write

    def _load(name):
        p = os.path.join(BASE, 'data', f'{name}.json')
        if not os.path.exists(p): return None
        with open(p, encoding='utf-8') as f: return _json.load(f)

    t0 = time.time()
    log("  1.1 Autenticando con ML API...")
    session = MLSession()
    log(f"  1.1 OK token user={session.user_id} ({time.time()-t0:.0f}s)")

    today = date.today()
    cur_year, cur_month = today.year, today.month
    pri_year  = cur_year if cur_month > 1 else cur_year - 1
    pri_month = cur_month - 1 if cur_month > 1 else 12

    def iso(d, end=False):
        t = "23:59:59" if end else "00:00:00"
        return f"{d.strftime('%Y-%m-%d')}T{t}.000-00:00"

    from datetime import date as _date
    cur_from = _date(cur_year, cur_month, 1)
    cur_to   = today
    pri_from = _date(pri_year, pri_month, 1)
    pri_day  = min(today.day, calendar.monthrange(pri_year, pri_month)[1])
    pri_to   = _date(pri_year, pri_month, pri_day)

    log(f"  1.2 Fetching ordenes mes actual {cur_from} -> {cur_to}...")
    cur_raw = fetch_orders_range(session, iso(cur_from), iso(cur_to, True), "Mes actual")
    # Deduplicar por order_id (ML API puede retornar duplicados en paginación)
    _seen_ids = set(); _dedup_raw = []
    for _o in cur_raw:
        _oid = _o.get('order_id')
        if _oid not in _seen_ids:
            _seen_ids.add(_oid); _dedup_raw.append(_o)
    if len(_dedup_raw) < len(cur_raw):
        log(f"  1.2 DEDUP: {len(cur_raw)-len(_dedup_raw)} duplicados removidos de orders_current")
    cur_raw = _dedup_raw
    _save('orders_current', cur_raw)
    log(f"  1.2 OK {len(cur_raw)} ordenes ({time.time()-t0:.0f}s)")

    log(f"  1.3 Fetching ordenes mes anterior {pri_from} -> {pri_to}...")
    pri_raw = fetch_orders_range(session, iso(pri_from), iso(pri_to, True), "Mes anterior")
    _save('orders_prior', pri_raw)
    log(f"  1.3 OK {len(pri_raw)} ordenes ({time.time()-t0:.0f}s)")

    mc = compute_metrics(cur_raw); _save('metrics_current', mc)
    mp = compute_metrics(pri_raw); _save('metrics_prior', mp)

    log(f"  1.4 Fetching items catalogo...")
    try:
        items = fetch_items(session)
        _save('items', items)
        log(f"  1.4 OK {len(items)} items ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.4 WARN items: {e}")
        items = _load('items') or []

    log(f"  1.4b Actualizando shipments_map con IDs nuevos...")
    try:
        import os as _os
        from concurrent.futures import ThreadPoolExecutor, as_completed
        _sm_path = _os.path.join(BASE, 'data', 'shipments_map.json')
        ship_map = json.load(open(_sm_path)) if _os.path.exists(_sm_path) else {}
        # Identificar shipping_ids no mapeados aún (de ambos meses)
        all_orders = cur_raw + pri_raw
        new_sids = list({
            str(o.get('shipping_id',''))
            for o in all_orders
            if o.get('shipping_id') and str(o.get('shipping_id','')) not in ship_map
        })
        if new_sids:
            log(f"  1.4b Fetching logistic_type para {len(new_sids)} shipments nuevos...")
            LOG_NORM = {"fulfillment":"fulfillment","cross_docking":"cross_docking",
                        "self_service":"self_service","default_buying_flow":"cross_docking",
                        "drop_off":"cross_docking","xd_drop_off":"cross_docking"}
            def _fetch_sid(sid):
                try:
                    r = session.get(f"/shipments/{sid}", params={"fields":"id,logistic_type"})
                    lt = r.get("logistic_type") or ""
                    return sid, LOG_NORM.get(lt, lt) if lt else None
                except Exception:
                    return sid, None
            fetched = 0
            with ThreadPoolExecutor(max_workers=20) as pool:
                futs = {pool.submit(_fetch_sid, sid): sid for sid in new_sids}
                for fut in as_completed(futs):
                    sid, lt = fut.result()
                    if lt:
                        ship_map[sid] = lt
                        fetched += 1
            _sm_tmp = _sm_path + '.tmp'
            with open(_sm_tmp, 'w', encoding='utf-8') as _smf: import json as _jj; _jj.dump(ship_map, _smf, ensure_ascii=False)
            _os.replace(_sm_tmp, _sm_path)
            log(f"  1.4b OK: {fetched}/{len(new_sids)} nuevos mapeados. Total: {len(ship_map)}")
        else:
            log(f"  1.4b shipments_map al dia ({len(ship_map)} entradas)")
    except Exception as e:
        log(f"  1.4b WARN shipments_map: {e}")
        import os as _os
        _sm_path = _os.path.join(BASE, 'data', 'shipments_map.json')
        ship_map = json.load(open(_sm_path)) if _os.path.exists(_sm_path) else {}

    log(f"  1.5 Enriqueciendo metricas + categorias...")
    try:
        log(f"  1.5 ship_map: {len(ship_map)} entradas")
        ec = enrich_metrics(cur_raw, items, ship_map)
        ep = enrich_metrics(pri_raw, items, ship_map)
        all_cats = set(list(ec.get('by_category',{}).keys()) + list(ep.get('by_category',{}).keys()))
        cat_names = fetch_category_names(session, list(all_cats))  # FIX: sin limite de 30
        for d in [ec, ep]:
            for cid, v in d.get('by_category',{}).items():
                v['name'] = cat_names.get(cid, cid)
        _save('enrich_current', ec); _save('enrich_prior', ep); _save('cat_names', cat_names)
        log(f"  1.5 OK {len(all_cats)} cats ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.5 WARN enrich: {e}")

    # PASO 1.5b: Aplicar overrides manuales de categorias (cat_manual_override.json)
    log("  1.5b Aplicando cat_manual_override...")
    try:
        import importlib.util as _ilu15b
        _spec15b = _ilu15b.spec_from_file_location("apply_cat_override", os.path.join(BASE, "apply_cat_override.py"))
        _mod15b = _ilu15b.module_from_spec(_spec15b)
        _spec15b.loader.exec_module(_mod15b)
        log(f"  1.5b OK cat_override aplicado ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.5b WARN apply_cat_override: {e}")

    log(f"  1.6 Fetching evolucion mensual 2026...")
    try:
        existing = _load('monthly_2026') or []
        fetch_monthly_evolution_2026(session, existing=existing)
        log(f"  1.6 OK ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.6 WARN monthly: {e}")

    # SKUs y STATUS xlsx (locales, no dependen de API)
    dash_dir = os.path.join(BASE, 'dashboards')
    for fname, fn_name in [('STATUS.xlsx', process_status_xlsx),
                            ('Categoria y subcategoria por codigo.xlsx', None)]:
        fpath = os.path.join(dash_dir, fname)
        if os.path.exists(fpath):
            try:
                if fn_name:
                    fn_name(fpath)
                else:
                    cats = load_sku_categories(fpath)
                    _save('sku_categories', cats)
            except Exception as e:
                log(f"  1.x WARN {fname}: {e}")

    log(f"  1.7 Fetching liquidaciones y conciliacion...")
    try:
        from ml_liquidaciones import run as run_liq
        run_liq(session=session)
        log(f"  1.7 OK liquidaciones ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.7 WARN liquidaciones: {e}")

    log(f"  1.8 Fetching balance Mercado Pago...")
    try:
        # Timeout interno de 3 minutos para balance MP (puede ser lento)
        def _mp_balance():
            from fetch_mp_balance import run as run_mp
            return run_mp(full_api=True)
        run_with_timeout(_mp_balance, 3 * 60, "balance MP")
        log(f"  1.8 OK balance MP ({time.time()-t0:.0f}s)")
    except TimeoutError as e:
        log(f"  1.8 TIMEOUT balance MP: {e} - usando cache")
    except Exception as e:
        log(f"  1.8 WARN balance MP: {e}")

    log("  1.10 Reputacion del vendedor...")
    try:
        fetch_reputation(session)
        log(f"  1.10 OK reputacion ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.10 ERROR reputacion: {e}")

    log(f"  1.11 Postventa: cancelados + devueltos + mediaciones...")
    try:
        compute_postventa(cur_raw, pri_raw)
        log(f"  1.11 OK postventa ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.11 WARN postventa: {e}")

    log("  1.12 Ads daily (ml_ads_fetch, ultimos 30 dias)...")
    try:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("ml_ads_fetch", os.path.join(BASE, "ml_ads_fetch.py"))
        _maf  = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_maf)
        from datetime import timedelta as _td
        _d_to   = (date.today() - _td(days=1)).isoformat()   # ayer = dia cerrado
        _d_from = (date.today() - _td(days=30)).isoformat()
        _maf.fetch_all(_d_from, _d_to)
        log(f"  1.12 OK ads ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.12 ERROR ads: {e}")

    log("  1.13 Claims & mediaciones...")
    try:
        import importlib.util as _ilu2
        _spec13 = _ilu2.spec_from_file_location("fetch_claims_analysis", os.path.join(BASE, "fetch_claims_analysis.py"))
        _fca = _ilu2.module_from_spec(_spec13); _spec13.loader.exec_module(_fca)
        _fca.run(session=session)
        log(f"  1.13 OK claims")
    except Exception as e:
        log(f"  1.13 WARN claims: {e}")

    log("  1.14 Stock status desde ML API...")
    try:
        import importlib.util as _ilu14
        _spec14 = _ilu14.spec_from_file_location("fetch_stock_ml", os.path.join(BASE, "fetch_stock_ml.py"))
        _fsm = _ilu14.module_from_spec(_spec14); _spec14.loader.exec_module(_fsm)
        _fsm.run(session=session)
        log(f"  1.14 OK stock ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.14 WARN stock: {e}")

    log("  1.15 Resenas negativas...")
    try:
        import importlib.util as _ilu15
        _spec15 = _ilu15.spec_from_file_location("ml_fetch_reviews", os.path.join(BASE, "ml_fetch_reviews.py"))
        _mfr = _ilu15.module_from_spec(_spec15); _spec15.loader.exec_module(_mfr)
        _mfr.fetch_negative_reviews(session=session)
        log(f"  1.15 OK resenas ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.15 WARN resenas: {e}")

    log("  1.16 Desempeno en envios (Flex + Colecta)...")
    try:
        import importlib.util as _ilu16
        _spec16 = _ilu16.spec_from_file_location("fetch_ship_performance", os.path.join(BASE, "fetch_ship_performance.py"))
        _fsp = _ilu16.module_from_spec(_spec16); _spec16.loader.exec_module(_fsp)
        _fsp.run()
        log(f"  1.16 OK ship performance ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.16 WARN ship performance: {e}")

    log("  1.17 Retenciones reales (IDB + IIBB via payments/search)...")
    try:
        import importlib.util as _ilu17
        _spec17 = _ilu17.spec_from_file_location("fetch_retenciones", os.path.join(BASE, "fetch_retenciones.py"))
        _fret = _ilu17.module_from_spec(_spec17); _spec17.loader.exec_module(_fret)
        _month_str = f"{cur_year}-{cur_month:02d}"
        _fret.run(_month_str)
        log(f"  1.17 OK retenciones ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.17 WARN retenciones: {e}")

    log("  1.18 Envíos reales (Full + Cross-docking via payments/search)...")
    try:
        import importlib.util as _ilu18
        _spec18 = _ilu18.spec_from_file_location("fetch_envios", os.path.join(BASE, "fetch_envios.py"))
        _fenv = _ilu18.module_from_spec(_spec18); _spec18.loader.exec_module(_fenv)
        _month_str18 = f"{cur_year}-{cur_month:02d}"
        _fenv.run(_month_str18)
        log(f"  1.18 OK envios ({time.time()-t0:.0f}s)")
    except Exception as e:
        log(f"  1.18 WARN envios: {e}")

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
    log(f"  1.9 Summary guardado. Total PASO 1: {time.time()-t0:.0f}s")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    sys.path.insert(0, BASE)
    _acquire_lock()
    try:
        _main_body()
    finally:
        _release_lock()


def _main_body():
    log("=" * 50)
    log("=== RUN DAILY START ===")

    # PASO 1: Fetch datos ML (timeout 20 minutos)
    log("PASO 1: Fetching datos ML API...")
    paso1_ok = False
    try:
        run_with_timeout(_fetch_all, 20 * 60, "PASO 1")
        log("PASO 1 OK")
        paso1_ok = True
    except TimeoutError as e:
        log(f"PASO 1 TIMEOUT: {e}")
        log("=== RUN DAILY ABORTED - TIMEOUT ===")
        _try_send_qa_blocked_alert({'blocked': True, 'errors': 1, 'warnings': 0,
            'checks': [{'name': 'paso1.timeout', 'level': 'CRITICAL', 'passed': False,
                        'detail': str(e), 'icon': '🚨'}],
            'summary': 'PASO 1 TIMEOUT — datos no actualizados'})
        return
    except Exception as e:
        log(f"PASO 1 WARN: fetch parcial: {e}")
        # No abortamos — QA decidirá si los datos parciales son aceptables

    # ──────────────────────────────────────────────────────────────────────
    # PASO 6: QA PRE-DEPLOY — validar ANTES de construir y publicar
    # ──────────────────────────────────────────────────────────────────────
    log("PASO 6: QA pre-deploy — validando integridad de datos...")
    qa_result = None
    regression_result = None
    try:
        import importlib.util as _iluqa
        _spec_qa = _iluqa.spec_from_file_location(
            "qa_validator", os.path.join(BASE, "qa_validator.py"))
        _qa_mod = _iluqa.module_from_spec(_spec_qa)
        _spec_qa.loader.exec_module(_qa_mod)
        qa_result = _qa_mod.run_qa()
        log(f"PASO 6 QA: {qa_result['summary']}")
    except Exception as e:
        log(f"PASO 6 WARN: QA falló con excepción: {e} — continuando sin QA")
        qa_result = None

    # Verificar regresiones (comparar vs snapshot anterior)
    try:
        import importlib.util as _ilureg
        _spec_reg = _ilureg.spec_from_file_location(
            "regression_snapshots", os.path.join(BASE, "regression_snapshots.py"))
        _reg_mod = _ilureg.module_from_spec(_spec_reg)
        _spec_reg.loader.exec_module(_reg_mod)
        regression_result = _reg_mod.check_regression()
        if regression_result.get('anomaly_count', 0) > 0:
            log(f"PASO 6 REGRESSION: {regression_result['anomaly_count']} anomalías detectadas")
        else:
            log("PASO 6 REGRESSION: Sin regresiones detectadas OK")
    except Exception as e:
        log(f"PASO 6 WARN: regression check falló: {e}")
        regression_result = None

    # ── DECISIÓN DE BLOQUEO ──────────────────────────────────────────────────
    if qa_result and qa_result.get('blocked', False):
        log(f"PASO 6 BLOQUEADO: QA critico — no se publica")
        _try_send_qa_blocked_alert(qa_result)
        log("=== RUN DAILY ABORTED - QA BLOQUEADO ===")
        return

    # PASO 2: Build HTML
    log("PASO 2: Construyendo dashboard HTML...")
    t_build = time.time()
    try:
        import importlib.util as _ilud
        _spec_d = _ilud.spec_from_file_location("ml_dashboard", os.path.join(BASE, "ml_dashboard.py"))
        _dash_mod = _ilud.module_from_spec(_spec_d)
        _spec_d.loader.exec_module(_dash_mod)
        _dash_mod.build_dashboard()
        log(f"PASO 2 OK build ({time.time()-t_build:.0f}s)")
    except Exception as e:
        log(f"PASO 2 WARN build_dashboard: {e}")

    # PASO 3: Postprocess (auth + phishing + calendario — idempotente)
    log("PASO 3: Postprocess dashboard...")
    try:
        import importlib.util as _ilup
        _spec_p = _ilup.spec_from_file_location("postprocess_dashboard", os.path.join(BASE, "postprocess_dashboard.py"))
        _post_mod = _ilup.module_from_spec(_spec_p)
        _spec_p.loader.exec_module(_post_mod)
        _post_mod.run()  # postprocess_dashboard usa run(), no postprocess()
        log(f"PASO 3 OK postprocess ({time.time()-t_build:.0f}s)")
    except Exception as e:
        log(f"PASO 3 WARN postprocess: {e}")

    # PASO 3.5: Inyectar datos reales de retenciones + envios en LIQ_SUMMARY
    log("PASO 3.5: Patch LIQ_SUMMARY con datos reales (retenciones + envios)...")
    try:
        import importlib.util as _iluliq
        _spec_liq = _iluliq.spec_from_file_location("patch_liq_summary_html", os.path.join(BASE, "patch_liq_summary_html.py"))
        _liq_mod = _iluliq.module_from_spec(_spec_liq)
        _spec_liq.loader.exec_module(_liq_mod)
        log(f"PASO 3.5 OK LIQ_SUMMARY patcheado ({time.time()-t_build:.0f}s)")
    except Exception as e:
        log(f"PASO 3.5 WARN patch_liq_summary: {e}")

    # PASO 3.6: Patch nombres de categorias en HTML (remapea MLA IDs → nombres legibles)
    log("PASO 3.6: Patch nombres de categorias (cat_manual_override)...")
    try:
        import importlib.util as _ilu36
        _spec36 = _ilu36.spec_from_file_location("patch_cat_names_html", os.path.join(BASE, "patch_cat_names_html.py"))
        _mod36 = _ilu36.module_from_spec(_spec36)
        _spec36.loader.exec_module(_mod36)
        log(f"PASO 3.6 OK cat_names patcheado ({time.time()-t_build:.0f}s)")
    except Exception as e:
        log(f"PASO 3.6 WARN patch_cat_names_html: {e}")

    # PASO 3.7: Reestructurar columnas tabla Ventas (Venta$ | Share$ | Venta U | Share U | Ticket | Crec)
    log("PASO 3.7: Patch columnas tabla Ventas...")
    try:
        import importlib.util as _ilu37
        _spec37 = _ilu37.spec_from_file_location("patch_ventas_cols", os.path.join(BASE, "patch_ventas_cols.py"))
        _mod37 = _ilu37.module_from_spec(_spec37)
        _spec37.loader.exec_module(_mod37)
        log(f"PASO 3.7 OK ventas_cols patcheado ({time.time()-t_build:.0f}s)")
    except SystemExit as e:
        if str(e) != '0':
            log(f"PASO 3.7 WARN patch_ventas_cols sys.exit({e}) — posible: ya patcheado o string no encontrado")
    except Exception as e:
        log(f"PASO 3.7 WARN patch_ventas_cols: {e}")

    # PASO 3.8: Cambiar Crec de valor absoluto a porcentaje
    log("PASO 3.8: Patch Crec columna a % (vs absoluto)...")
    try:
        import importlib.util as _ilu38
        _spec38 = _ilu38.spec_from_file_location("patch_crec_pct", os.path.join(BASE, "patch_crec_pct.py"))
        _mod38 = _ilu38.module_from_spec(_spec38)
        _spec38.loader.exec_module(_mod38)
        log(f"PASO 3.8 OK crec_pct patcheado ({time.time()-t_build:.0f}s)")
    except SystemExit as e:
        if str(e) != '0':
            log(f"PASO 3.8 WARN patch_crec_pct sys.exit({e}) — posible: ya patcheado o string no encontrado")
    except Exception as e:
        log(f"PASO 3.8 WARN patch_crec_pct: {e}")

    # PASO 3.9: Pinear fila TOTAL PERÍODO de Ventas a DAILY_CUR (misma fuente que Resumen)
    log("PASO 3.9: Patch total row Ventas → DAILY_CUR (cross-tab consistency)...")
    try:
        import importlib.util as _ilu39
        _spec39 = _ilu39.spec_from_file_location("patch_total_row_ventas", os.path.join(BASE, "patch_total_row_ventas.py"))
        _mod39 = _ilu39.module_from_spec(_spec39)
        _spec39.loader.exec_module(_mod39)
        log(f"PASO 3.9 OK total_row_ventas patcheado ({time.time()-t_build:.0f}s)")
    except SystemExit as e:
        if str(e) != '0':
            log(f"PASO 3.9 WARN patch_total_row_ventas sys.exit({e})")
    except Exception as e:
        log(f"PASO 3.9 WARN patch_total_row_ventas: {e}")

    # PASO 4: Deploy a Railway
    log("PASO 4: Deploying a Railway...")
    try:
        import urllib.request
        html_path = os.path.join(BASE, 'dashboards', 'ml_dashboard_360.html')
        cfg_path  = os.path.join(BASE, 'ml_email_config.json')
        cfg = json.load(open(cfg_path))
        url = cfg['railway_url'].rstrip('/') + '/update'
        key = cfg['railway_update_key']
        html_bytes = open(html_path, 'rb').read()
        req = urllib.request.Request(url, data=html_bytes, method='POST',
              headers={'X-Update-Key': key, 'Content-Type': 'text/html; charset=utf-8'})
        resp = urllib.request.urlopen(req, timeout=30)
        resp_body = resp.read().decode()[:120]
        log(f"PASO 4 OK deploy: {resp.status} {resp_body}")
    except Exception as e:
        log(f"PASO 4 WARN deploy: {e}")

    # PASO 4b: Guardar snapshot de regresion post-deploy
    log("PASO 4b: Guardando regression snapshot...")
    try:
        if regression_result is not None:
            import importlib.util as _ilureg2
            _spec_r2 = _ilureg2.spec_from_file_location("regression_snapshots2", os.path.join(BASE, "regression_snapshots.py"))
            _reg2 = _ilureg2.module_from_spec(_spec_r2)
            _spec_r2.loader.exec_module(_reg2)
            _reg2.save_snapshot()
            log("PASO 4b OK snapshot guardado")
        else:
            log("PASO 4b SKIP: regression_result no disponible")
    except Exception as e:
        log(f"PASO 4b WARN snapshot: {e}")

    # PASO 5: Email diario
    log("PASO 5: Enviando email diario...")
    try:
        import importlib.util as _iluemail
        _spec_em = _iluemail.spec_from_file_location("ml_email_clean", os.path.join(BASE, "ml_email_clean.py"))
        _email_mod = _iluemail.module_from_spec(_spec_em)
        _spec_em.loader.exec_module(_email_mod)
        _email_mod.send_daily_email()
        log(f"PASO 5 OK email enviado ({time.time()-t_build:.0f}s)")
    except Exception as e:
        log(f"PASO 5 WARN email: {e}")

    # PASO 5b: Email QA warnings (si hay warnings)
    if qa_result and qa_result.get('warnings', 0) > 0:
        log("PASO 5b: Enviando email QA warnings...")
        try:
            _try_send_qa_blocked_alert(qa_result)
            log("PASO 5b OK QA warnings email")
        except Exception as e:
            log(f"PASO 5b WARN QA email: {e}")

    # PASO 5c: Health check post-deploy
    log("PASO 5c: Health check post-deploy...")
    try:
        import importlib.util as _iludhc
        _spec_dhc = _iludhc.spec_from_file_location("daily_health_check", os.path.join(BASE, "daily_health_check.py"))
        _dhc = _iludhc.module_from_spec(_spec_dhc)
        _spec_dhc.loader.exec_module(_dhc)
        hc_result = _dhc.run()
        if hc_result.failures > 0:
            log(f"PASO 5c HEALTH FAIL: {hc_result.failures} fallos, {hc_result.warnings} avisos")
            # Intentar enviar email de alerta
            try:
                _dhc.run_with_email()
            except Exception:
                pass
        elif hc_result.warnings > 0:
            log(f"PASO 5c HEALTH WARN: {hc_result.warnings} avisos (pipeline OK)")
        else:
            log(f"PASO 5c HEALTH OK: {hc_result.ok} checks pasados")
    except Exception as e:
        log(f"PASO 5c WARN health_check: {e}")

    log(f"=== RUN DAILY COMPLETED OK ({time.time()-t_build:.0f}s build+deploy) ===")



def _try_send_qa_blocked_alert(qa_result):
    """Envia alerta por email cuando QA bloquea o hay warnings criticos."""
    import smtplib, json as _json
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from datetime import date

    cfg_path = os.path.join(BASE, 'ml_email_config.json')
    if not os.path.exists(cfg_path):
        log("  _try_send_qa_blocked: sin ml_email_config.json, skip")
        return False
    try:
        with open(cfg_path, encoding='utf-8') as f:
            cfg = _json.load(f)
    except Exception as e:
        log(f"  _try_send_qa_blocked: error leyendo config: {e}")
        return False

    to_list = cfg.get('to', [])
    if not to_list:
        log("  _try_send_qa_blocked: sin destinatarios, skip")
        return False

    blocked  = qa_result.get('blocked', False)
    errors   = qa_result.get('errors', 0)
    warnings = qa_result.get('warnings', 0)
    summary  = qa_result.get('summary', 'QA resultado')
    checks   = qa_result.get('checks', [])

    status_label = "🚨 BLOQUEADO" if blocked else "⚠️ WARNINGS"
    color        = "#cc0000" if blocked else "#e67e00"
    today_str    = date.today().strftime('%d/%m/%Y')

    rows_html = ""
    for c in checks:
        icon    = c.get('icon', '•')
        name    = c.get('name', '')
        level   = c.get('level', '')
        detail  = c.get('detail', '')
        passed  = c.get('passed', True)
        bg      = "#fff5f5" if not passed else "#f5fff5"
        rows_html += (
            f"<tr style='background:{bg}'>"
            f"<td style='padding:4px 8px'>{icon}</td>"
            f"<td style='padding:4px 8px'><b>{name}</b></td>"
            f"<td style='padding:4px 8px'>{level}</td>"
            f"<td style='padding:4px 8px'>{detail}</td>"
            f"</tr>"
        )

    html_body = f"""
<html><body style="font-family:Arial,sans-serif;color:#333">
  <h2 style="color:{color}">ML Dashboard — QA {status_label} — {today_str}</h2>
  <p><b>Resumen:</b> {summary}</p>
  <p>Errores: <b>{errors}</b> &nbsp;|&nbsp; Warnings: <b>{warnings}</b></p>
  <table border="1" cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-size:13px">
    <tr style="background:#eee">
      <th style="padding:4px 8px"></th>
      <th style="padding:4px 8px">Check</th>
      <th style="padding:4px 8px">Nivel</th>
      <th style="padding:4px 8px">Detalle</th>
    </tr>
    {rows_html}
  </table>
  <p style="color:#999;font-size:11px">ML 360° SPOTCOMPRAS — reporte automático</p>
</body></html>
"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"ML 360 QA {status_label} — {today_str} — SPOTCOMPRAS"
        msg['From']    = f"{cfg.get('from_name', 'ML Dashboard')} <{cfg['smtp_user']}>"
        msg['To']      = ', '.join(to_list)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        with smtplib.SMTP(cfg['smtp_host'], int(cfg['smtp_port'])) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(cfg['smtp_user'], cfg['smtp_password'])
            srv.sendmail(cfg['smtp_user'], to_list, msg.as_string())
        log(f"  QA alert email enviado a: {', '.join(to_list)}")
        return True
    except Exception as e:
        log(f"  _try_send_qa_blocked: error enviando email: {e}")
        return False


if __name__ == '__main__':
    main()
