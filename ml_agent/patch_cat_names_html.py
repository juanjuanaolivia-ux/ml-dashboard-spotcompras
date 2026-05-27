"""
patch_cat_names_html.py
Inyecta en el HTML un JS snippet que renombra/fusiona las keys MLA en TODOS los objetos
de datos de categorías: BY_CAT_CUR, BY_CAT_PRI, DAILY_BY_CAT, DAILY_BY_CAT_PRI.
Se aplica ANTES de que renderVentas() corra, reemplazando keys tipo "MLA1588" por "ILUMINACION".
"""
import os, json, re, sys

BASE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
HTML     = os.path.join(BASE, "dashboards", "ml_dashboard_360.html")

# Cargar overrides
override_path = os.path.join(DATA_DIR, "cat_manual_override.json")
override = json.load(open(override_path, encoding="utf-8")) if os.path.exists(override_path) else {}

# Solo los que tienen valor asignado
mapping = {k: v.upper() for k, v in override.items() if v.strip()}
print(f"  Mapeos a aplicar: {len(mapping)}")
for k, v in sorted(mapping.items()):
    print(f"    {k} → {v}")

if not mapping:
    print("ERROR: no hay mapeos en cat_manual_override.json")
    sys.exit(1)

# Construir el snippet JS
# Fusiona la key MLA dentro del objeto target (BY_CAT_CUR o BY_CAT_PRI)
mapping_js = json.dumps(mapping, ensure_ascii=False)
snippet = f"""
<script id="cat-name-patch">
(function(){{
  var MAP = {mapping_js};
  function remap(obj) {{
    if(!obj) return;
    Object.keys(MAP).forEach(function(mla) {{
      if(!(mla in obj)) return;
      var target = MAP[mla];
      if(target in obj) {{
        // Fusionar: sumar gmv, units y skus
        var src = obj[mla], dst = obj[target];
        dst.gmv   = (dst.gmv||0)   + (src.gmv||0);
        dst.units = (dst.units||0) + (src.units||0);
        Object.assign(dst.skus = dst.skus||{{}}, src.skus||{{}});
      }} else {{
        obj[target] = obj[mla];
      }}
      delete obj[mla];
    }});
  }}
  if(typeof BY_CAT_CUR !== 'undefined') remap(BY_CAT_CUR);
  if(typeof BY_CAT_PRI !== 'undefined') remap(BY_CAT_PRI);
  // CRÍTICO: DAILY_BY_CAT es la fuente principal de renderVentas — también debe ser remapeado
  if(typeof DAILY_BY_CAT !== 'undefined') {{
    Object.keys(DAILY_BY_CAT).forEach(function(d){{ remap(DAILY_BY_CAT[d]); }});
  }}
  if(typeof DAILY_BY_CAT_PRI !== 'undefined') {{
    Object.keys(DAILY_BY_CAT_PRI).forEach(function(d){{ remap(DAILY_BY_CAT_PRI[d]); }});
  }}
}})();
</script>"""

with open(HTML, encoding="utf-8") as f:
    html = f.read()

# Remover patch previo si existe
html = re.sub(r'\n?<script id="cat-name-patch">.*?</script>', '', html, flags=re.DOTALL)

# Estrategia: inyectar DESPUÉS del </script> que cierra el bloque de datos (BY_CAT_CUR)
# así el patch queda entre bloques <script>, no adentro de uno
marker = None
for candidate in ["const BY_CAT_CUR=", "var BY_CAT_CUR=", "let BY_CAT_CUR="]:
    if candidate in html:
        marker = candidate
        break
if not marker:
    print("ERROR: no se encontró 'BY_CAT_CUR=' en el HTML")
    sys.exit(1)
idx = html.find(marker)

# Buscar el </script> que cierra el bloque que contiene BY_CAT_CUR
close_tag = "</script>"
idx_close = html.find(close_tag, idx)
if idx_close < 0:
    print("ERROR: no se encontró </script> después de BY_CAT_CUR")
    sys.exit(1)
inject_pos = idx_close + len(close_tag)

html = html[:inject_pos] + "\n" + snippet + "\n" + html[inject_pos:]

with open(HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nOK inyectado ({len(html):,} bytes)")
print("Siguiente paso: deploy_rapido.bat")
