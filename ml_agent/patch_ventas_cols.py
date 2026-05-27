"""
patch_ventas_cols.py
Reestructura columnas tabla Ventas por categoría/SKU:
  ANTES: GMV | Unid | Ticket | Share$ | Dep | Full | Aduana | Cobert | vs Ant%
  AHORA: Venta$ | Share$ | Venta U | Share U | Ticket | Crec vs ant $
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
        # mostrar contexto de búsqueda para debug
        key = old[:60].strip()
        idx = html.find(key[:30])
        if idx >= 0:
            errors.append(f"  Contexto: ...{html[idx:idx+120]}...")
    else:
        html = html.replace(old, new, 1)
        print(f"OK [{label}]")

# ── 1. HEADER ─────────────────────────────────────────────────────────────────
rep("header",
    '<th>Categoría / SKU</th><th>GMV</th><th>Unidades</th><th>Ticket Prom.</th><th>% GMV</th><th>vs Ant.</th><th style="text-align:right">Dep.</th><th style="text-align:right">Full</th><th style="text-align:right">Aduana</th><th style="text-align:center">Cobert.</th></tr></thead>',
    '<th style="min-width:200px">Categoría / SKU</th><th style="text-align:right">Venta $</th><th style="text-align:center">Share $</th><th style="text-align:right">Venta U</th><th style="text-align:center">Share U</th><th style="text-align:right">Ticket Prom.</th><th style="text-align:right">Crec vs ant. $</th></tr></thead>'
)

# ── 2. VARS categoría: agregar shareU y crecAbs ───────────────────────────────
rep("cat-vars",
    '    var share=(fData.gmv/totalG*100).toFixed(1);\n    var dpG=dPct(fData.gmv,priData.gmv);\n    var tk=fData.units>0?fData.gmv/fData.units:0;',
    '    var share=(fData.gmv/totalG*100).toFixed(1);\n    var shareU=(totalU>0?(fData.units/totalU*100).toFixed(1):\'0.0\');\n    var crecAbs=fData.gmv-(priData.gmv||0);var crecStr=(crecAbs>=0?\'+\':\'\')+fmtM(crecAbs);var crecC=crecAbs>=0?\'var(--green)\':\'var(--red)\';\n    var tk=fData.units>0?fData.gmv/fData.units:0;'
)

# ── 3. ORDEN columnas categoría: GMV → share% → units → shareU% → ticket → crec$ ──
rep("cat-cols-gmv",
    "    html+='<td style=\"font-weight:700;color:var(--blue);text-align:right\">'+fmtM(fData.gmv)+'</td>'\n    html+='<td style=\"text-align:right\">'+fmtN(fData.units)+'</td>'\n    html+='<td style=\"text-align:right\">'+fmtM(tk)+'</td>'\n    html+='<td style=\"text-align:center\"><span class=\"badge-share\">'+share+'%</span></td>'",
    "    html+='<td style=\"font-weight:700;color:var(--blue);text-align:right\">'+fmtM(fData.gmv)+'</td>'\n    html+='<td style=\"text-align:center\"><span class=\"badge-share\">'+share+'%</span></td>'\n    html+='<td style=\"text-align:right\">'+fmtN(fData.units)+'</td>'\n    html+='<td style=\"text-align:center\"><span class=\"badge-share\" style=\"background:rgba(52,199,89,.13);color:var(--green)\">'+shareU+'%</span></td>'\n    html+='<td style=\"text-align:right\">'+fmtM(tk)+'</td>'"
)

# ── 4. Quitar stock y cobertura categoría, poner crec$ ────────────────────────
rep("cat-stock-remove",
    "    var catStkDep=0,catStkFull=0,catStkAduana=0;\n    Object.keys(fullData.skus||{}).forEach(function(sid){var sr=stkMap[sid]||{};catStkDep+=sr.stock_dep||0;catStkFull+=sr.stock_full||0;catStkAduana+=sr.stock_aduana||0;});\n    totStkDep+=catStkDep;totStkFull+=catStkFull;totStkAduana+=catStkAduana;\n    html+='<td style=\\\"text-align:center\\\">'+arrH(dpG)+'</td>'\n    html+='<td style=\\\"text-align:right;color:var(--text2);font-size:12px\\\">'+fmtN(catStkDep)+'</td>'\n    html+='<td style=\\\"text-align:right;color:var(--cyan);font-size:12px\\\">'+fmtN(catStkFull)+'</td>'\n    html+='<td style=\\\"text-align:right;color:var(--text3);font-size:12px\\\">'+fmtN(catStkAduana)+'</td>'\n    var catTotStk=catStkDep+catStkFull;\n    var catUnits=fData.units||0;\n    var catDays=t-f+1;\n    var catDr=catUnits>0?catUnits/catDays:0;\n    var catCovD=catDr>0?Math.round(catTotStk/catDr):null;\n    var catCovStr=catCovD===null?'—':(catCovD>999?'>999d':catCovD+'d');\n    var catCovC=catCovD===null?'var(--text3)':catCovD<7?'var(--red)':catCovD<15?'var(--yellow)':'var(--green)';\n    html+='<td style=\\\"text-align:center;color:'+catCovC+';font-weight:700\\\">'+catCovStr+'</td></tr>'",
    "    html+='<td style=\\\"text-align:right;font-weight:700;color:'+crecC+'\\\">'+crecStr+'</td></tr>'"
)

# ── 5. VARS SKU: agregar shareU y crecAbs ────────────────────────────────────
rep("sku-vars",
    "        var priSku=TOP_ITEMS_PRI[s.id]||{};\n        var dpSku=priSku.gmv?dPct(sGmv,priSku.gmv):null;",
    "        var priSku=TOP_ITEMS_PRI[s.id]||{};\n        var sSU=fData.units>0?(sU/fData.units*100).toFixed(1):'0.0';\n        var skuCrecAbs=sGmv-(priSku.gmv||0);var skuCrecStr=(skuCrecAbs>=0?'+':'')+fmtM(skuCrecAbs);var skuCrecC=skuCrecAbs>=0?'var(--green)':'var(--red)';"
)

# ── 6. ORDEN columnas SKU ────────────────────────────────────────────────────
rep("sku-cols",
    '        html+=\'<td style="color:var(--cyan);text-align:right">\'+fmtM(sGmv)+\'</td>\';\n        html+=\'<td style="text-align:right">\'+fmtN(sU)+\'</td>\';\n        html+=\'<td style="text-align:right">\'+fmtM(sT)+\'</td>\';\n        html+=\'<td style="text-align:center"><span class="badge-sku">\'+sS+\'%</span></td>\';',
    '        html+=\'<td style="color:var(--cyan);text-align:right">\'+fmtM(sGmv)+\'</td>\';\n        html+=\'<td style="text-align:center"><span class="badge-sku">\'+sS+\'%</span></td>\';\n        html+=\'<td style="text-align:right">\'+fmtN(sU)+\'</td>\';\n        html+=\'<td style="text-align:center"><span class="badge-sku" style="background:rgba(52,199,89,.13);color:var(--green)">\'+sSU+\'%</span></td>\';\n        html+=\'<td style="text-align:right">\'+fmtM(sT)+\'</td>\';'
)

# ── 7. Quitar stock y cobertura SKU, poner crec$ ─────────────────────────────
rep("sku-stock-remove",
    '        var stkR=stkMap[s.id]||{};\n        var stkDep=stkR.stock_dep||0,stkFull=stkR.stock_full||0,stkAduana=stkR.stock_aduana||0;\n        var stkDays2=t-f+1;\n        var dr2=sU>0?sU/stkDays2:0;\n        var covDays=dr2>0?Math.round((stkDep+stkFull)/dr2):null;\n        var covStr=covDays===null?\'—\':(covDays>999?\'&gt;999d\':covDays+\'d\');\n        var covC2=covDays===null?\'var(--text3)\':covDays<7?\'var(--red)\':covDays<15?\'var(--yellow)\':\'var(--green)\';\n        html+=\'<td style="text-align:center">\'+arrH(dpSku)+\'</td>\';\n        html+=\'<td style="text-align:right;color:var(--text2);font-size:11px">\'+fmtN(stkDep)+\'</td>\';\n        html+=\'<td style="text-align:right;color:var(--cyan);font-size:11px">\'+fmtN(stkFull)+\'</td>\';\n        html+=\'<td style="text-align:right;color:var(--text3);font-size:11px">\'+fmtN(stkAduana)+\'</td>\';\n        html+=\'<td style="text-align:center;color:\'+covC2+\';font-weight:700;font-size:11px">\'+covStr+\'</td></tr>\';',
    '        html+=\'<td style="text-align:right;font-weight:700;color:\'+skuCrecC+\';font-size:11px">\'+skuCrecStr+\'</td></tr>\';'
)

# ── 8. TOTAL ROW: reordenar y quitar stock ────────────────────────────────────
rep("total-row",
    "  var totTk=totalU>0?totalGraw/totalU:0;\n  var dpTot=dPct(totalGraw,totalPriG);",
    "  var totTk=totalU>0?totalGraw/totalU:0;\n  var totCrecAbs=totalGraw-(totalPriG||0);var totCrecStr=(totCrecAbs>=0?'+':'')+fmtM(totCrecAbs);var totCrecC=totCrecAbs>=0?'var(--green)':'var(--red)';"
)

rep("total-row-cols",
    "    '<td style=\"font-weight:800;color:var(--blue);text-align:right;font-size:15px;padding-right:10px\">'+fmtM(totalGraw)+'</td>'+\n    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtN(totalU)+'</td>'+\n    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtM(totTk)+'</td>'+\n    '<td style=\"text-align:center\"><span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:700\">100%</span></td>'+\n    '<td style=\\\"text-align:center\\\">'+arrH(dpTot)+'</td>';",
    "    '<td style=\"font-weight:800;color:var(--blue);text-align:right;font-size:15px;padding-right:10px\">'+fmtM(totalGraw)+'</td>'+\n    '<td style=\"text-align:center\"><span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:700\">100%</span></td>'+\n    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtN(totalU)+'</td>'+\n    '<td style=\"text-align:center\"><span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:700\">100%</span></td>'+\n    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtM(totTk)+'</td>'+\n    '<td style=\"text-align:right;font-weight:800;color:\'+totCrecC+\'\">\'+totCrecStr+\'</td></tr>\';"
)

rep("total-stock-remove",
    "  var _ts=totStkDep+totStkFull;var _td=totalU>0?totalU/(t-f+1):0;\n  var _tc=_td>0?Math.round(_ts/_td):null;\n  var _tcs=_tc===null?'—':(_tc>999?'>999d':_tc+'d');\n  var _tcc=_tc===null?'var(--text3)':_tc<7?'var(--red)':_tc<15?'var(--yellow)':'var(--green)';\n  totRow+=\"<td style=\\\"text-align:right;color:var(--text2);font-weight:800;font-size:12px\\\"\"+\">\" +fmtN(totStkDep)+\"</td>\";\n  totRow+=\"<td style=\\\"text-align:right;color:var(--cyan);font-weight:800;font-size:12px\\\"\"+\">\" +fmtN(totStkFull)+\"</td>\";\n  totRow+=\"<td style=\\\"text-align:right;color:var(--text3);font-weight:800;font-size:12px\\\"\"+\">\" +fmtN(totStkAduana)+\"</td>\";\n  totRow+='<td style=\"text-align:center;font-weight:800;color:'+_tcc+'\">'+_tcs+'</td></tr>';",
    ""
)

# ─── Resultado ────────────────────────────────────────────────────────────────
if errors:
    print("\n=== ERRORES ===")
    for e in errors:
        print(e)
    print("\nNO se guardaron cambios. Corregir los patches arriba.")
    sys.exit(1)

with open(HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"\nOK guardado ({len(html):,} bytes)")
print("Siguiente paso: correr deploy_rapido.bat")
