"""
patch_crec_pct.py
Cambia la columna "Crec vs ant. $" de valor absoluto a porcentaje:
  ANTES: crecAbs = gmv - priGmv  → muestra "+$2.25M"
  AHORA: crecPct = (gmv/priGmv - 1) * 100 → muestra "+12.3%"
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE, "dashboards", "ml_dashboard_360.html")

with open(HTML, encoding="utf-8") as f:
    html = f.read()

errors = []

def rep(label, old, new):
    global html
    if old not in html:
        errors.append(f"FAIL [{label}]: string no encontrado")
        key = old[:50].strip()
        idx = html.find(key[:30])
        if idx >= 0:
            errors.append(f"  Contexto: ...{html[idx:idx+120]}...")
    else:
        html = html.replace(old, new, 1)
        print(f"OK [{label}]")

# ── 1. Header: renombrar columna ──────────────────────────────
rep("header-col",
    '<th style="text-align:right">Crec vs ant. $</th>',
    '<th style="text-align:right">Crec vs ant. %</th>'
)

# ── 2. VARS categoría: cambiar crecAbs/crecStr por crecPct ───
rep("cat-vars-crec",
    "var crecAbs=fData.gmv-(priData.gmv||0);var crecStr=(crecAbs>=0?'+':'')+fmtM(crecAbs);var crecC=crecAbs>=0?'var(--green)':'var(--red)';",
    "var crecPct=priData.gmv>0?((fData.gmv/priData.gmv-1)*100):null;var crecStr=crecPct===null?'—':((crecPct>=0?'+':'')+crecPct.toFixed(1)+'%');var crecC=crecPct===null?'var(--text3)':crecPct>=0?'var(--green)':'var(--red)';"
)

# ── 3. VARS SKU: cambiar skuCrecAbs por skuCrecPct ───────────
rep("sku-vars-crec",
    "var skuCrecAbs=sGmv-(priSku.gmv||0);var skuCrecStr=(skuCrecAbs>=0?'+':'')+fmtM(skuCrecAbs);var skuCrecC=skuCrecAbs>=0?'var(--green)':'var(--red)';",
    "var skuCrecPct=priSku.gmv>0?((sGmv/priSku.gmv-1)*100):null;var skuCrecStr=skuCrecPct===null?'—':((skuCrecPct>=0?'+':'')+skuCrecPct.toFixed(1)+'%');var skuCrecC=skuCrecPct===null?'var(--text3)':skuCrecPct>=0?'var(--green)':'var(--red)';"
)

# ── 4. VARS total row: cambiar totCrecAbs por totCrecPct ──────
rep("total-vars-crec",
    "var totCrecAbs=totalGraw-(totalPriG||0);var totCrecStr=(totCrecAbs>=0?'+':'')+fmtM(totCrecAbs);var totCrecC=totCrecAbs>=0?'var(--green)':'var(--red)';",
    "var totCrecPct=totalPriG>0?((totalGraw/totalPriG-1)*100):null;var totCrecStr=totCrecPct===null?'—':((totCrecPct>=0?'+':'')+totCrecPct.toFixed(1)+'%');var totCrecC=totCrecPct===null?'var(--text3)':totCrecPct>=0?'var(--green)':'var(--red)';"
)

# ─── Resultado ────────────────────────────────────────────────
if errors:
    print("\n=== ERRORES ===")
    for e in errors:
        print(e)
    print("\nNO se guardaron cambios.")
    sys.exit(1)

with open(HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nOK guardado ({len(html):,} bytes)")
print("Siguiente paso: deploy_rapido.bat")
