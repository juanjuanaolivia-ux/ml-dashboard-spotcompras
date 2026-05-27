"""
postprocess_dashboard.py  v12
- Step 0: Update MP_BALANCE in-place
- Step 1: Replace period-bar with calendar picker
- Step 2: Inject calendar CSS
- Step 5: Inject calendar JS (con validación de integridad)
- Step 6: Inject phishing tab data + JS
- Step 7: Inject auth layer (login + roles)
"""
import os
import re
import json
from datetime import datetime, timedelta

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "dashboards", "ml_dashboard_360.html")
DATA_DIR  = os.path.join(BASE_DIR, "data")
TPL_DIR   = os.path.join(BASE_DIR, "templates")

# Firmas que deben existir al final de cada template (anti-truncación)
TEMPLATE_GUARDS = {
    "calendar.js":     "_calInit",
    "period_bar.html": 'id="day-to"',
}


def _validate_tpl(name, content):
    """Lanza RuntimeError si el template parece truncado."""
    guard = TEMPLATE_GUARDS.get(name)
    if guard and guard not in content:
        raise RuntimeError(
            f"TEMPLATE TRUNCADO: {name} no contiene '{guard}'. "
            f"({len(content)} chars). El archivo está roto — restauralo con bash."
        )
    if name == "calendar.js" and not content.rstrip().endswith("}"):
        raise RuntimeError(
            f"calendar.js truncado: no termina en '}}'. "
            f"Últimos 40 chars: {repr(content[-40:])}"
        )


def find_balanced_div(html, start):
    i, depth = start, 0
    while i < len(html):
        if html[i:i+4] == "<div":
            depth += 1
        elif html[i:i+6] == "</div>":
            depth -= 1
            if depth == 0:
                return i + 6
        i += 1
    return len(html)


def _load_mp_balance():
    p = os.path.join(DATA_DIR, "mp_balance.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    snap = data.get("snapshot_at", "")
    if snap:
        try:
            dt = datetime.strptime(snap, "%Y-%m-%d %H:%M")
            dt_ar = dt - timedelta(hours=3)
            data["snapshot_at"] = dt_ar.strftime("%d/%m %H:%M") + " hs (ARG)"
        except Exception:
            pass
    return data


def _fmt_m(v):
    if v >= 1_000_000:
        return "${:.2f}M".format(v / 1_000_000)
    return "${:,.0f}".format(v)


def _read_tpl(name):
    p = os.path.join(TPL_DIR, name)
    with open(p, encoding="utf-8") as f:
        content = f.read()
    _validate_tpl(name, content)
    return content


# ── Step 6: Phishing tab ─────────────────────────────────────────────────────

def _load_phishing_data():
    p = os.path.join(DATA_DIR, "phishing.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


SEV_COLOR = {
    "critical": "#ff4d4f",
    "high":     "#faad14",
    "medium":   "#1890ff",
    "low":      "#52c41a",
}
SEV_LABEL = {
    "critical": "🔴 CRÍTICO",
    "high":     "🟠 ALTO",
    "medium":   "🟡 MEDIO",
    "low":      "🟢 BAJO",
}


def _build_phishing_tab_html(phdata):
    """Genera el HTML de la tab de phishing."""
    if not phdata:
        return (
            '<div id="tab20" class="tab">'
            '<div class="card"><div class="card-body" style="text-align:center;padding:40px">'
            '<p style="color:var(--text3);font-size:14px">⚠️ No hay datos de phishing todavía.<br>'
            'Corré <code>python phishing.py</code> para generar el análisis.</p>'
            '</div></div></div>'
        )

    alerts     = phdata.get("fraud_alerts", [])
    blacklist  = phdata.get("blacklist", [])
    summary    = phdata.get("summary", {})
    gen_at     = phdata.get("generated_at", "—")
    n_orders   = phdata.get("total_orders", 0)

    # KPIs
    n_crit = summary.get("critical", 0)
    n_high = summary.get("high", 0)
    n_med  = summary.get("medium", 0)
    n_bl   = len(blacklist)

    kpi_color = "#ff4d4f" if n_crit > 0 else ("#faad14" if n_high > 0 else "var(--green)")

    # Tabla de alertas
    alert_rows = ""
    for a in alerts[:50]:
        sev   = a.get("severity", "low")
        col   = SEV_COLOR.get(sev, "#888")
        lbl   = SEV_LABEL.get(sev, sev)
        nick  = a.get("nickname", a.get("buyer_id", "—"))
        det   = a.get("detail", "")
        gmv   = a.get("gmv_risk", 0)
        gmv_s = "${:,.0f}".format(gmv) if gmv else "—"
        alert_rows += (
            f'<tr>'
            f'<td style="padding:8px 10px;font-size:11px;font-weight:700;color:{col}">{lbl}</td>'
            f'<td style="padding:8px 10px;font-size:12px;font-weight:600">{nick}</td>'
            f'<td style="padding:8px 10px;font-size:12px;color:var(--text2)">{det}</td>'
            f'<td style="padding:8px 10px;font-size:12px;color:var(--red);text-align:right">{gmv_s}</td>'
            f'</tr>'
        )
    if not alert_rows:
        alert_rows = (
            '<tr><td colspan="4" style="padding:20px;text-align:center;color:var(--green)">'
            '✅ Sin alertas de fraude detectadas en el período actual.</td></tr>'
        )

    # Tabla blacklist
    bl_rows = ""
    for b in blacklist:
        bl_rows += (
            f'<tr>'
            f'<td style="padding:8px 10px;font-size:12px;font-weight:600;color:var(--red)">'
            f'🚫 {b.get("buyer_nickname","—")}</td>'
            f'<td style="padding:8px 10px;font-size:11px;color:var(--text3)">{b.get("buyer_id","—")}</td>'
            f'<td style="padding:8px 10px;font-size:12px">{b.get("reason","—")}</td>'
            f'<td style="padding:8px 10px;font-size:11px;color:var(--text3)">{b.get("added_at","—")}</td>'
            f'</tr>'
        )
    if not bl_rows:
        bl_rows = (
            '<tr><td colspan="4" style="padding:16px;text-align:center;color:var(--text3)">'
            'Blacklist vacía. Usá <code>python phishing.py</code> o el CLI para agregar compradores.</td></tr>'
        )

    html = f"""<div id="tab20" class="tab">
<div style="max-width:1100px;margin:0 auto">

  <!-- KPIs -->
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px">
    <div class="kpi" style="flex:1;min-width:140px">
      <div class="kpi-label">🔴 Alertas críticas</div>
      <div class="kpi-val" style="color:{('#ff4d4f' if n_crit>0 else 'var(--green)')}">{n_crit}</div>
    </div>
    <div class="kpi" style="flex:1;min-width:140px">
      <div class="kpi-label">🟠 Alertas altas</div>
      <div class="kpi-val" style="color:{('#faad14' if n_high>0 else 'var(--green)')}">{n_high}</div>
    </div>
    <div class="kpi" style="flex:1;min-width:140px">
      <div class="kpi-label">🟡 Alertas medias</div>
      <div class="kpi-val" style="color:var(--text)">{n_med}</div>
    </div>
    <div class="kpi" style="flex:1;min-width:140px">
      <div class="kpi-label">🚫 En Blacklist</div>
      <div class="kpi-val" style="color:var(--red)">{n_bl}</div>
    </div>
    <div class="kpi" style="flex:1;min-width:180px">
      <div class="kpi-label">📊 Órdenes analizadas</div>
      <div class="kpi-val" style="color:var(--blue)">{n_orders:,}</div>
      <div class="kpi-pri">Actualizado: {gen_at}</div>
    </div>
  </div>

  <!-- Alertas de fraude -->
  <div class="card" style="margin-bottom:16px">
    <div class="card-header">
      <span class="card-title">⚠️ Alertas de Fraude · Período actual</span>
      <span style="font-size:11px;color:var(--text3);margin-left:8px">
        Análisis automático de patrones en órdenes
      </span>
    </div>
    <div class="card-body tbl-scroll">
      <table style="width:100%;border-collapse:collapse">
        <thead><tr style="border-bottom:1px solid var(--border)">
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">SEVERIDAD</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">COMPRADOR</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">DETALLE</th>
          <th style="padding:8px 10px;text-align:right;font-size:11px;color:var(--text3);font-weight:600">GMV RIESGO</th>
        </tr></thead>
        <tbody>{alert_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Blacklist -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">🚫 Blacklist de Compradores</span>
      <span style="font-size:11px;color:var(--text3);margin-left:8px">
        Para agregar: <code style="background:var(--surface2);padding:2px 6px;border-radius:4px;font-size:10px">
        python phishing.py add-blacklist BUYER_ID "motivo"</code>
      </span>
    </div>
    <div class="card-body tbl-scroll">
      <table style="width:100%;border-collapse:collapse">
        <thead><tr style="border-bottom:1px solid var(--border)">
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">COMPRADOR</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">ID</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">MOTIVO</th>
          <th style="padding:8px 10px;text-align:left;font-size:11px;color:var(--text3);font-weight:600">FECHA</th>
        </tr></thead>
        <tbody>{bl_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Patrones detectados -->
  <div class="card" style="margin-top:16px">
    <div class="card-header"><span class="card-title">🔍 Patrones de Phishing Monitoreados</span></div>
    <div class="card-body">
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <span style="background:rgba(255,77,79,.1);color:#ff4d4f;border:1px solid rgba(255,77,79,.3);padding:4px 10px;border-radius:6px;font-size:11px">Pago fuera de plataforma</span>
        <span style="background:rgba(255,77,79,.1);color:#ff4d4f;border:1px solid rgba(255,77,79,.3);padding:4px 10px;border-radius:6px;font-size:11px">URL falsa de ML</span>
        <span style="background:rgba(255,77,79,.1);color:#ff4d4f;border:1px solid rgba(255,77,79,.3);padding:4px 10px;border-radius:6px;font-size:11px">Solicitud DNI/tarjeta</span>
        <span style="background:rgba(250,173,20,.1);color:#faad14;border:1px solid rgba(250,173,20,.3);padding:4px 10px;border-radius:6px;font-size:11px">Desvío a WhatsApp/Telegram</span>
        <span style="background:rgba(250,173,20,.1);color:#faad14;border:1px solid rgba(250,173,20,.3);padding:4px 10px;border-radius:6px;font-size:11px">Links acortados</span>
        <span style="background:rgba(24,144,255,.1);color:#1890ff;border:1px solid rgba(24,144,255,.3);padding:4px 10px;border-radius:6px;font-size:11px">Urgencia cuenta</span>
        <span style="background:rgba(24,144,255,.1);color:#1890ff;border:1px solid rgba(24,144,255,.3);padding:4px 10px;border-radius:6px;font-size:11px">Alta tasa cancelación comprador</span>
        <span style="background:rgba(24,144,255,.1);color:#1890ff;border:1px solid rgba(24,144,255,.3);padding:4px 10px;border-radius:6px;font-size:11px">Comprador en blacklist activo</span>
      </div>
    </div>
  </div>

</div>
</div>"""
    return html


def inject_phishing_tab(html, phdata):
    """Inyecta el nav-btn y el contenido de la tab de phishing."""
    SKIP_MARKER = "data-tab=\"20\""
    if SKIP_MARKER in html:
        print("  SKIP phishing tab (ya inyectada)")
        return html

    # 1. Agregar botón nav (justo antes del cierre del nav-bar </div>)
    # Buscamos el pattern del último nav-btn
    last_nav_btn = html.rfind('onclick="showTab(')
    if last_nav_btn == -1:
        print("  [phishing] WARN: no se encontró nav-btn. Skipping.")
        return html
    # Encontrar el fin de ese botón
    btn_end = html.find('</button>', last_nav_btn) + len('</button>')
    phishing_btn = '<button class="nav-btn" data-tab="20" onclick="showTab(20)">🛡️ Seguridad</button>'
    html = html[:btn_end] + "\n        " + phishing_btn + html[btn_end:]

    # 2. Agregar el contenido de la tab (antes de </body> o al final del último tab)
    tab_html = _build_phishing_tab_html(phdata)

    # Buscar el marcador del último tab cerrado para insertar después
    last_tab_close = html.rfind('</div>')
    # Insertar el tab antes de </html> (el dashboard no tiene </body>)
    if "</html>" in html:
        html = html.replace("</html>", tab_html + "\n</html>", 1)
    elif "</body>" in html:
        html = html.replace("</body>", tab_html + "\n</body>", 1)
    else:
        html += tab_html

    # 3. _initTab ya incluye la llamada a renderPhishing con guard typeof
    # (inyectada en ml_dashboard.py). Fallback idempotente si por alguna razón no está.
    GUARDED_CALL = "if(n===20&&typeof renderPhishing==='function')renderPhishing();"
    UNGUARDED_CALL = "if(n===20)renderPhishing();"
    if GUARDED_CALL not in html and UNGUARDED_CALL not in html and "if(n===10)" in html:
        html = html.replace(
            "  if(n===10)renderLiquidaciones(f,t);",
            "  if(n===10)renderLiquidaciones(f,t);\n  " + GUARDED_CALL
        )
    elif UNGUARDED_CALL in html and GUARDED_CALL not in html:
        # Upgrade old unguarded call to guarded
        html = html.replace(
            "  if(n===20)renderPhishing();",
            "  " + GUARDED_CALL
        )

    print("  [phishing] Tab 🛡️ Seguridad inyectada OK")
    return html


# ── Step 7: Auth layer ───────────────────────────────────────────────────────


# ── Step 7b: Nav-right patch ─────────────────────────────────────────────────

def _patch_auth_nav(html):
    """Integra logout y role badge en el nav-right (idempotente)."""
    import re as _re
    # Guard: ya parchado
    if "nav-right integrado" in html:
        print("  [auth-nav] SKIP (ya parchado)")
        return html
    changed = False
    # 1. CSS: reemplazar bloque de flotantes por display:none!important
    # Buscamos desde el comentario hasta el cierre de #sp-role-badge
    tok1 = "/* Botón logout */"     # /* Botón logout */
    tok2 = "/* Badge de rol */"
    if tok1 in html and tok2 in html:
        i1 = html.index(tok1)
        # Encontrar el cierre del bloque #sp-role-badge (el siguiente "}" despues de tok2)
        i2 = html.index(tok2, i1)
        # Buscar el "}" que cierra #sp-role-badge
        i3 = html.index("}", i2 + len(tok2))
        new_css = ("/* Flotantes legacy — nav-right integrado */\n"
                   "#sp-logout-btn { display:none!important; }\n"
                   "#sp-role-badge  { display:none!important; }")
        html = html[:i1] + new_css + html[i3+1:]
        changed = True

    # 2. Quitar div flotante de logout (si existe)
    div_logout = '<div id="sp-logout-btn" onclick="spLogout()">'
    if div_logout in html:
        i_div = html.index(div_logout)
        i_div_end = html.index("</div>", i_div) + 6
        html = html[:i_div] + html[i_div_end:]
        changed = True

    # 3. Quitar div flotante de role-badge (si existe)
    div_badge = '<div id="sp-role-badge" id="sp-role-badge">'
    if div_badge in html:
        i_div = html.index(div_badge)
        i_div_end = html.index("</div>", i_div) + 6
        html = html[:i_div] + html[i_div_end:]
        changed = True

    # 4. spApplyRole: reemplazar if (logoutB) por nav-right
    old_logoutb = 'if (logoutB) { logoutB.style.display = "block"; }'
    new_navright = ('var _nr=document.getElementById("nav-right-user");'
                    'var _nb=document.getElementById("sp-role-badge-nav");'
                    'if(_nb)_nb.textContent=(roleLabels[role]||role)+" \\u00b7 "+username;'
                    'if(_nr)_nr.style.display="flex";')
    if old_logoutb in html:
        html = html.replace(old_logoutb, new_navright, 1)
        changed = True

    if changed:
        print("  [auth-nav] OK nav-right integrado")
    else:
        print("  [auth-nav] WARN: nada reemplazado")
    return html


def inject_auth_layer(html):
    """Llama a auth_layer.py para inyectar el login overlay."""
    import sys
    auth_module = os.path.join(BASE_DIR, "auth_layer.py")
    if not os.path.exists(auth_module):
        print("  [auth] SKIP: auth_layer.py no encontrado")
        return html

    import importlib.util
    spec = importlib.util.spec_from_file_location("auth_layer", auth_module)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    users_file = os.path.join(BASE_DIR, "auth_users.json")
    if not os.path.exists(users_file):
        print("  [auth] SKIP: auth_users.json no encontrado")
        return html

    with open(users_file, encoding="utf-8") as f:
        data = json.load(f)
    users = data.get("users", [])
    if not users:
        print("  [auth] SKIP: no hay usuarios en auth_users.json")
        return html

    auth_html = mod.generate_auth_html(users)

    # Idempotente: remover si ya existe
    START_MARKER = "<!-- ============================================================ -->\n<!-- AUTH LAYER"
    END_MARKER   = "<!-- FIN AUTH LAYER"
    if START_MARKER in html:
        start_idx = html.index(START_MARKER)
        end_idx   = html.index("-->", html.index(END_MARKER)) + 3
        while end_idx < len(html) and html[end_idx] in ('\n', '\r'):
            end_idx += 1
        html = html[:start_idx] + html[end_idx:]
        print("  [auth] Auth anterior removida (actualizando)")

    if "</html>" in html:
        html = html.replace("</html>", auth_html + "\n</html>", 1)
    elif "</body>" in html:
        html = html.replace("</body>", auth_html + "\n</body>", 1)
    else:
        html += auth_html

    print(f"  [auth] ✅ Login inyectado. {len(users)} usuario(s).")
    return html


# ── run() principal ──────────────────────────────────────────────────────────

def run():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    mpb = _load_mp_balance()

    # 0. Update MP_BALANCE in-place
    if mpb:
        mpb_json = json.dumps(mpb)
        new_decl = "const MP_BALANCE=" + mpb_json + ";"
        html = re.sub(
            r'(?:const|var|let)\s+MP_BALANCE\s*=\s*\{[^}]*\};',
            new_decl, html, count=1
        )
        print("OK MP_BALANCE: " + _fmt_m(mpb["disponible"]) + " @ " + str(mpb["snapshot_at"]))

    # 1. Replace period-bar with calendar picker
    bar_start = html.find('<div class="period-bar"')
    bar_end = find_balanced_div(html, bar_start)
    new_bar = _read_tpl("period_bar.html")
    html = html[:bar_start] + new_bar + html[bar_end:]
    print("OK Period-bar replaced")

    # 2. Inject CSS (guard: skip if already injected)
    if '.cd{' in html:
        print("SKIP CSS (ya inyectado)")
    else:
        extra_css = (
            "<style>\n"
            ".cd{width:100%;height:36px;line-height:36px;text-align:center;border-radius:8px;"
            "font-size:13px;font-weight:600;cursor:pointer;transition:background .08s,color .08s;"
            "color:var(--text);box-sizing:border-box;user-select:none;}\n"
            ".cd:hover{background:rgba(52,131,250,.12);color:#3483FA;}\n"
            ".cd.cd-sel{background:#3483FA!important;color:#fff!important;border-radius:8px!important;}\n"
            ".cd.cd-rng{background:rgba(52,131,250,.18)!important;color:#3483FA;border-radius:0;}\n"
            ".cd.cd-rs{background:#3483FA!important;color:#fff!important;border-radius:8px 0 0 8px;}\n"
            ".cd.cd-re{background:#3483FA!important;color:#fff!important;border-radius:0 8px 8px 0;}\n"
            ".cd.cd-rs.cd-re{border-radius:8px!important;}\n"
            ".cd.cd-today:not(.cd-sel):not(.cd-rs):not(.cd-re){box-shadow:inset 0 0 0 1.5px #3483FA;color:#3483FA;}\n"
            ".cd.cd-dis{color:var(--text3)!important;cursor:default!important;opacity:.35;"
            "background:none!important;pointer-events:none;}\n"
            ".cd.cd-prev{color:var(--text3);opacity:.4;cursor:pointer;}\n"
            ".cd.cd-hover-rng{background:rgba(52,131,250,.13)!important;color:#3483FA;border-radius:0;}\n"
            ".cd.cd-hover-rs{background:rgba(52,131,250,.45)!important;color:#fff!important;"
            "border-radius:8px 0 0 8px;}\n"
            ".cd.cd-hover-re{background:rgba(52,131,250,.45)!important;color:#fff!important;"
            "border-radius:0 8px 8px 0;}\n"
            ".cd.cd-hover-re.cd-hover-rs{border-radius:8px!important;}\n"
            ".kpi{cursor:pointer;transition:transform .18s,box-shadow .18s;}\n"
            ".kpi:hover{transform:translateY(-3px);box-shadow:0 6px 20px rgba(52,131,250,.13);}\n"
            ".card{transition:box-shadow .18s;}\n"
            ".card:hover{box-shadow:0 4px 18px rgba(0,0,0,.09);}\n"
            "@keyframes fadeIn{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}\n"
            "button.cal-open{border-color:#3483FA!important;"
            "box-shadow:0 0 0 3px rgba(52,131,250,.18)!important;}\n"
            ".period-chip.active{background:#3483FA;color:#fff;border-color:#3483FA;}\n"
            "</style>"
        )
        html = html.replace("</head>", extra_css + "\n</head>", 1)
        print("OK CSS injected")

    # 5. Inject calendar JS from template (always re-inject; own <script> block before </html>)
    extra_js = _read_tpl("calendar.js")
    CAL_MARKER = "// === CALENDAR DATE PICKER"
    OLD_CAL_MARKER = "// ── FIN CALENDAR"  # viejo marker inline — limpiar si existe
    # Remove any previously injected calendar <script> block (new marker)
    if CAL_MARKER in html:
        blk_start = html.rfind("<script>", 0, html.index(CAL_MARKER))
        if blk_start == -1:
            blk_start = html.index(CAL_MARKER)
        blk_end = html.index("</script>", html.index(CAL_MARKER)) + len("</script>")
        html = html[:blk_start] + html[blk_end:]
        print("  [calendar] bloque nuevo anterior removido")
    # Remove old inline calendar block (starts before function calToggle/calDayClick, ends at FIN CALENDAR)
    if OLD_CAL_MARKER in html:
        # The old block is inside the main <script>; find the JS section and strip from var _calYear to FIN CALENDAR
        old_markers = ["var _calOpen", "var _calYear", "var _calMonth", "var _calSel"]
        for om in old_markers:
            if om in html:
                old_start = html.rfind(om)
                old_end_str = OLD_CAL_MARKER
                if old_end_str in html:
                    old_end = html.index(old_end_str) + len(old_end_str)
                    html = html[:old_start] + html[old_end:]
                    print("  [calendar] bloque viejo (calDayClick) removido")
                break
    # Inject as its own <script> block — use </html> if present, else append to end
    cal_block = "\n<script>\n" + extra_js + "\n</script>\n"
    if "</html>" in html:
        html = html.replace("</html>", cal_block + "</html>", 1)
    else:
        html = html + cal_block  # fallback: append cuando no hay </html>
    print("OK JS injected (calendar v6 + hover-preview + stopPropagation)")

    # 6. Phishing: correr análisis + inyectar tab
    try:
        import importlib.util as _ilu
        _ph_path = os.path.join(BASE_DIR, "phishing.py")
        if os.path.exists(_ph_path):
            _ph_spec = _ilu.spec_from_file_location("phishing", _ph_path)
            _ph_mod  = _ilu.module_from_spec(_ph_spec)
            _ph_spec.loader.exec_module(_ph_mod)
            phdata = _ph_mod.run()  # genera data/phishing.json y retorna el dict
        else:
            phdata = _load_phishing_data()
        html = inject_phishing_tab(html, phdata)
    except Exception as e:
        print(f"  [phishing] WARN: {e} (no crítico)")

    # 7. Auth layer
    try:
        html = inject_auth_layer(html)
        html = _patch_auth_nav(html)
    except Exception as e:
        print(f"  [auth] WARN: {e} (no crítico)")

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK Saved {:,} chars".format(len(html)))

if __name__ == "__main__":
    run()
