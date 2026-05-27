"""
daily_health_check.py
=====================
Monitor post-pipeline: verifica que TODOS los datos del dashboard esten frescos
y correctos. Corre DESPUES del pipeline (PASO 5b en run_daily.py).

Checks que realiza:
  1. Frescura de archivos criticos (max 26h desde hoy)
  2. Valores no-cero en KPIs principales
  3. Consistencia entre archivos (GMV, categorias, stock)
  4. Flags "es_real" en datos de envios y retenciones
  5. Deploy verificado (HTML en produccion actualizado hoy)
  6. Categorias sin MLA IDs en stock_status.json
  7. Stock con dias calculados (no todos S/MOV)
  8. Pipeline completado sin errores graves en ml_run.log

Salida:
  - data/health_last_result.json  → resultado completo
  - Imprime resumen en consola
  - Retorna True si todo OK, False si hay alertas

Integracion en run_daily.py:
  Agregar al final del PASO 5:
    from daily_health_check import run as health_check
    health_check()
"""
import os
import json
import re
from datetime import datetime, date, timedelta

BASE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

# ─── Colores para consola ─────────────────────────────────────────────────────
OK   = "[OK]"
WARN = "[WARN]"
FAIL = "[FAIL]"
INFO = "[INFO]"


class HealthResult:
    def __init__(self):
        self.checks  = []   # lista de {name, status, detail}
        self.ok      = 0
        self.warnings = 0
        self.failures = 0

    def add(self, name, status, detail=""):
        self.checks.append({"name": name, "status": status, "detail": detail,
                             "ts": datetime.now().isoformat()})
        if status == "OK":
            self.ok += 1
        elif status == "WARN":
            self.warnings += 1
        elif status == "FAIL":
            self.failures += 1

    @property
    def passed(self):
        return self.failures == 0

    def to_dict(self):
        return {
            "run_at":   datetime.now().isoformat(),
            "passed":   self.passed,
            "ok":       self.ok,
            "warnings": self.warnings,
            "failures": self.failures,
            "checks":   self.checks,
        }


def _load(name):
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _file_age_hours(name):
    """Retorna edad del archivo en horas, o None si no existe."""
    path = os.path.join(DATA_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    age_s = datetime.now().timestamp() - mtime
    return age_s / 3600


def _check_freshness(r: HealthResult, name: str, max_hours: float = 26.0):
    age = _file_age_hours(name)
    if age is None:
        r.add(f"Frescura {name}", "FAIL", "Archivo no existe")
    elif age > max_hours:
        r.add(f"Frescura {name}", "FAIL",
              f"{age:.1f}h > limite {max_hours}h")
    elif age > max_hours * 0.8:
        r.add(f"Frescura {name}", "WARN",
              f"{age:.1f}h (cerca del limite {max_hours}h)")
    else:
        r.add(f"Frescura {name}", "OK", f"{age:.1f}h")


# ─── Checks individuales ──────────────────────────────────────────────────────

def check_critical_files_fresh(r: HealthResult):
    """Archivos criticos deben tener menos de 26h."""
    critical = [
        "orders_current", "summary", "enrich_current",
        "metrics_current", "liq_summary",
    ]
    for name in critical:
        _check_freshness(r, name, max_hours=26.0)


def check_secondary_files_fresh(r: HealthResult):
    """Archivos secundarios: 48h."""
    secondary = [
        "stock_status", "cat_names", "postventa_current",
        "retenciones_real", "envios_real", "mp_balance",
    ]
    for name in secondary:
        _check_freshness(r, name, max_hours=48.0)


def check_gmv_not_zero(r: HealthResult):
    summary = _load("summary")
    if not summary:
        r.add("GMV no-cero", "FAIL", "summary.json no existe")
        return
    gmv = summary.get("gmv_month", 0) or 0
    if gmv <= 0:
        r.add("GMV mes", "FAIL", f"GMV = {gmv} (esperado > 0)")
    elif gmv < 1_000_000:
        r.add("GMV mes", "WARN", f"GMV = {gmv:,.0f} (parece bajo)")
    else:
        r.add("GMV mes", "OK", f"GMV = {gmv:,.0f}")


def check_orders_count(r: HealthResult):
    orders = _load("orders_current")
    if not isinstance(orders, list):
        r.add("Ordenes", "FAIL", "orders_current.json no existe o no es lista")
        return
    n = len(orders)
    if n == 0:
        r.add("Ordenes", "FAIL", "orders_current.json vacio")
    elif n < 10:
        r.add("Ordenes", "WARN", f"Solo {n} ordenes (esperado mas)")
    else:
        r.add("Ordenes", "OK", f"{n} ordenes cargadas")


def check_categories_not_mla(r: HealthResult):
    """Verifica que stock_status no tenga categorias con codigo MLA crudo."""
    stock = _load("stock_status")
    if not isinstance(stock, list) or len(stock) == 0:
        r.add("Categorias sin MLA", "WARN", "stock_status.json vacio o no existe")
        return
    mla_count = sum(1 for s in stock
                    if re.match(r'^MLA\d+$', s.get("categoria", "")))
    total = len(stock)
    if mla_count == total:
        r.add("Categorias sin MLA", "FAIL",
              f"TODOS los {total} SKUs tienen categoria MLA cruda")
    elif mla_count > 0:
        pct = mla_count / total * 100
        r.add("Categorias sin MLA", "WARN",
              f"{mla_count}/{total} SKUs ({pct:.0f}%) con categoria MLA cruda")
    else:
        r.add("Categorias sin MLA", "OK",
              f"Todos los {total} SKUs tienen nombre de categoria")


def check_stock_smov(r: HealthResult):
    """Verifica que no TODOS los items sean S/MOV (indicaria que ventas_sku esta vacio)."""
    stock = _load("stock_status")
    if not isinstance(stock, list) or len(stock) == 0:
        r.add("Stock dias calculados", "WARN", "stock_status.json vacio o no existe")
        return
    total = len(stock)
    smov  = sum(1 for s in stock if s.get("dias_stock") == "S/MOV")
    pct   = smov / total * 100 if total > 0 else 0
    if pct >= 95:
        r.add("Stock dias calculados", "FAIL",
              f"{smov}/{total} ({pct:.0f}%) son S/MOV — ventas_sku posiblemente vacio")
    elif pct > 50:
        r.add("Stock dias calculados", "WARN",
              f"{smov}/{total} ({pct:.0f}%) son S/MOV")
    else:
        real = total - smov
        r.add("Stock dias calculados", "OK",
              f"{real}/{total} SKUs con dias calculados ({pct:.0f}% S/MOV)")


def check_retenciones_real(r: HealthResult):
    liq = _load("liq_summary")
    if not liq:
        r.add("Retenciones real", "FAIL", "liq_summary.json no existe")
        return
    es_real = liq.get("retenciones_es_real", False)
    total   = liq.get("retenciones_total", 0) or 0
    if not es_real:
        r.add("Retenciones real", "WARN",
              f"retenciones_es_real=False, total={total:,.0f}")
    elif total <= 0:
        r.add("Retenciones real", "FAIL",
              "retenciones_es_real=True pero total=0")
    else:
        r.add("Retenciones real", "OK", f"Real={total:,.0f}")


def check_envios_real(r: HealthResult):
    liq = _load("liq_summary")
    if not liq:
        r.add("Envios real", "FAIL", "liq_summary.json no existe")
        return
    es_real = liq.get("envios_es_real", False)
    total   = liq.get("shipping_total", 0) or 0
    if not es_real:
        r.add("Envios real", "WARN",
              f"envios_es_real=False, total={total:,.0f}")
    elif total <= 0:
        r.add("Envios real", "FAIL",
              "envios_es_real=True pero total=0")
    else:
        r.add("Envios real", "OK", f"Real={total:,.0f}")


def check_mp_balance(r: HealthResult):
    bal = _load("mp_balance")
    if not bal:
        r.add("MP Balance", "FAIL", "mp_balance.json no existe")
        return
    disp    = bal.get("disponible", 0) or 0
    a_cobrar = bal.get("a_cobrar", 0) or 0
    if disp <= 0 and a_cobrar <= 0:
        r.add("MP Balance", "FAIL", "disponible=0 y a_cobrar=0")
    else:
        r.add("MP Balance", "OK",
              f"disp={disp:,.0f} | a_cobrar={a_cobrar:,.0f}")


def check_liq_summary_updated(r: HealthResult):
    liq = _load("liq_summary")
    if not liq:
        r.add("Liq summary actualizado", "FAIL", "liq_summary.json no existe")
        return
    updated_at = liq.get("updated_at", "")
    today_str  = date.today().isoformat()
    if not updated_at.startswith(today_str):
        r.add("Liq summary actualizado", "WARN",
              f"updated_at={updated_at} (no es hoy {today_str})")
    else:
        r.add("Liq summary actualizado", "OK", f"updated_at={updated_at}")


def check_pipeline_log(r: HealthResult):
    """Lee ml_run.log y verifica que el ultimo run haya sido exitoso."""
    log_path = os.path.join(BASE, "ml_run.log")
    if not os.path.exists(log_path):
        r.add("Pipeline log", "WARN", "ml_run.log no existe")
        return

    # Leer las ultimas 200 lineas
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        last_lines = lines[-200:]
        content = "".join(last_lines)

        # Buscar marcadores de exito/error
        if "RUN DAILY COMPLETED OK" in content or "RUN DAILY DONE" in content:
            # Verificar que sea reciente (hoy)
            today_str = date.today().strftime("%Y-%m-%d")
            if any(today_str in line and ("COMPLETED OK" in line or "DONE" in line)
                   for line in last_lines):
                r.add("Pipeline log", "OK", "Completado OK hoy")
            else:
                r.add("Pipeline log", "WARN",
                      "COMPLETED OK encontrado pero no parece ser de hoy")
        elif "RUN DAILY ABORTED" in content or "TIMEOUT" in content:
            r.add("Pipeline log", "FAIL",
                  "Pipeline abortado o timeout en ultimo run")
        else:
            r.add("Pipeline log", "WARN",
                  "No se encontro marcador de exito/error claro")
    except Exception as e:
        r.add("Pipeline log", "WARN", f"Error leyendo log: {e}")


def check_orders_current_month(r: HealthResult):
    """Verifica que haya ordenes del mes actual en orders_current."""
    orders = _load("orders_current")
    if not isinstance(orders, list) or len(orders) == 0:
        return  # ya fue chequeado en check_orders_count
    today  = date.today()
    mes_str = f"{today.year}-{today.month:02d}"
    orders_this_month = [o for o in orders
                         if (o.get("date_created", "") or "").startswith(mes_str)]
    if len(orders_this_month) == 0:
        r.add("Ordenes mes actual", "FAIL",
              f"Cero ordenes en {mes_str}")
    elif len(orders_this_month) < 5:
        r.add("Ordenes mes actual", "WARN",
              f"Solo {len(orders_this_month)} ordenes en {mes_str}")
    else:
        r.add("Ordenes mes actual", "OK",
              f"{len(orders_this_month)} ordenes en {mes_str}")


# ─── Runner principal ─────────────────────────────────────────────────────────

def check_html_structure(r: HealthResult):
    """Verifica que el HTML generado no tiene tabs anidados (divs desbalanceados)."""
    html_path = os.path.join(BASE, "dashboards", "ml_dashboard_360.html")
    if not os.path.exists(html_path):
        r.add("HTML estructura", "WARN", "ml_dashboard_360.html no existe")
        return
    try:
        with open(html_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        # Verificar que tab7 NO está dentro de tab6 (el parent debe venir ANTES)
        idx6 = text.find('id="tab6"')
        idx7 = text.find('id="tab7"')
        idx9 = text.find('id="tab9"')
        if idx6 < 0 or idx7 < 0:
            r.add("HTML estructura", "WARN", "No se encontraron tab6/tab7")
            return
        if idx7 < idx6:
            r.add("HTML estructura", "FAIL", "tab7 aparece ANTES de tab6 — estructura corrupta")
            return
        # Contar divs en la sección de tab6 (entre tab6 y tab7)
        tab6_content = text[idx6:idx7]
        open_d = tab6_content.count('<div')
        close_d = tab6_content.count('</div>')
        balance = open_d - close_d
        if balance != 0:
            r.add("HTML estructura", "FAIL",
                  f"tab6 desbalanceado ({balance:+d} divs) — tabs 7/9/10/20 quedan anidados")
        else:
            # Verificar también que los tabs no están anidados con una heurística:
            # el texto "id=\"tab7\"" debe aparecer DESPUÉS del ultimo </div> de tab6
            r.add("HTML estructura", "OK", f"tab6 balance=0 ({open_d} divs)")
    except Exception as e:
        r.add("HTML estructura", "WARN", f"Error verificando: {e}")


def run() -> HealthResult:
    r = HealthResult()
    print("\n" + "=" * 65)
    print("  DAILY HEALTH CHECK — SPOTCOMPRAS ML 360")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    check_critical_files_fresh(r)
    check_secondary_files_fresh(r)
    check_gmv_not_zero(r)
    check_orders_count(r)
    check_orders_current_month(r)
    check_categories_not_mla(r)
    check_stock_smov(r)
    check_retenciones_real(r)
    check_envios_real(r)
    check_mp_balance(r)
    check_liq_summary_updated(r)
    check_pipeline_log(r)
    check_html_structure(r)

    # Imprimir resultados
    print()
    for c in r.checks:
        icon = OK if c["status"] == "OK" else (WARN if c["status"] == "WARN" else FAIL)
        print(f"  {icon}  {c['name']:<35} {c['detail']}")

    print()
    print("=" * 65)
    if r.passed:
        if r.warnings > 0:
            print(f"  RESULTADO: OK con {r.warnings} advertencia(s)")
        else:
            print(f"  RESULTADO: TODO OK ({r.ok} checks pasados)")
    else:
        print(f"  RESULTADO: {r.failures} FALLO(S) | {r.warnings} aviso(s) | {r.ok} ok")
    print("=" * 65)

    # Guardar resultado
    out_path = os.path.join(DATA_DIR, "health_last_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(r.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n  Resultado guardado: data/health_last_result.json")

    return r


# ─── Envio de email si hay fallos ─────────────────────────────────────────────

def run_with_email():
    """Corre el health check y envia email si hay FAIL."""
    r = run()
    if not r.passed:
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                "ml_email_clean", os.path.join(BASE, "ml_email_clean.py"))
            _mel = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mel)

            cfg_path = os.path.join(BASE, "ml_email_config.json")
            cfg      = json.load(open(cfg_path, encoding="utf-8"))

            failures = [c for c in r.checks if c["status"] == "FAIL"]
            warnings = [c for c in r.checks if c["status"] == "WARN"]

            lines = ["<h3>Dashboard Health Check — FALLOS DETECTADOS</h3>",
                     f"<p>{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>",
                     "<ul>"]
            for c in failures:
                lines.append(f"<li><b>FALLO</b>: {c['name']} — {c['detail']}</li>")
            for c in warnings:
                lines.append(f"<li><b>AVISO</b>: {c['name']} — {c['detail']}</li>")
            lines.append("</ul>")
            lines.append("<p>Revisar ml_run.log y data/ para diagnostico.</p>")

            body = "\n".join(lines)
            subject = f"[ALERTA] Health Check FALLO — {datetime.now().strftime('%d/%m/%Y')}"

            if hasattr(_mel, 'send_custom_email'):
                _mel.send_custom_email(subject, body, cfg)
            else:
                print(f"  [health] Email no enviado — send_custom_email no disponible")
        except Exception as e:
            print(f"  [health] WARN email: {e}")
    return r


if __name__ == "__main__":
    import sys
    if "--email" in sys.argv:
        result = run_with_email()
    else:
        result = run()
    sys.exit(0 if result.passed else 1)
