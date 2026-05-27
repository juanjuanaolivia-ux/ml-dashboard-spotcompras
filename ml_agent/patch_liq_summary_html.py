"""
patch_liq_summary_html.py — Inyecta LIQ_SUMMARY con retenciones + envíos reales en el HTML.
Reemplaza patch_retenciones_html.py — cubre ambas fuentes de datos reales.
Usar cuando el rebuild hace timeout en el sandbox de Cowork.
"""
import json, re, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE, 'dashboards', 'ml_dashboard_360.html')
LIQ  = os.path.join(BASE, 'data', 'liq_summary.json')
RET  = os.path.join(BASE, 'data', 'retenciones_real.json')
ENV  = os.path.join(BASE, 'data', 'envios_real.json')

# Cargar datos
liq = json.load(open(LIQ, encoding='utf-8'))

# Actualizar con retenciones reales
if os.path.exists(RET):
    ret = json.load(open(RET, encoding='utf-8'))
    liq['retenciones_total']   = ret['total']
    liq['retenciones_es_real'] = True
    print(f"  retenciones_total  = {ret['total']:,.2f}")

# Actualizar con envíos reales
if os.path.exists(ENV):
    env = json.load(open(ENV, encoding='utf-8'))
    liq['shipping_total']  = env['total']
    liq['envios_es_real']  = True
    print(f"  shipping_total     = {env['total']:,.2f}")

# Leer HTML
html = open(HTML, encoding='utf-8').read()

# Buscar y reemplazar const LIQ_SUMMARY={...};
new_liq_json = json.dumps(liq, ensure_ascii=False)
pattern = r'(const LIQ_SUMMARY=)(\{[^;]+\})(;)'
m = re.search(pattern, html, re.DOTALL)
if not m:
    print("ERROR: no se encontró const LIQ_SUMMARY en el HTML")
    sys.exit(1)

old_block = m.group(0)
new_block = f'const LIQ_SUMMARY={new_liq_json};'
html_new  = html.replace(old_block, new_block, 1)

if html_new == html:
    print("ERROR: el reemplazo no tuvo efecto")
    sys.exit(1)

# Guardar atómico
tmp = HTML + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(html_new)
os.replace(tmp, HTML)

print(f"✅ LIQ_SUMMARY actualizado en HTML ({os.path.getsize(HTML):,} bytes)")
