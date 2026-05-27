"""
patch_total_row_ventas.py
Fija la fila TOTAL PERÍODO en la tabla de Ventas para que use DAILY_CUR
(misma fuente que Resumen) en lugar de la suma de DAILY_BY_CAT.

Problema original:
  - DAILY_BY_CAT usa unit_price sin fallback a full_unit_price
  - daily_cur_computed (fuente de DAILY_CUR) usa unit_price OR full_unit_price OR 0
  - Resultado: fila TOTAL difería ~$639K respecto a Resumen

Fix: computar curGmv/curUnits desde DAILY_CUR filtrado por rango,
     y usarlos en la fila totalizadora en lugar de totalGraw/totalU.
"""
import os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE, "dashboards", "ml_dashboard_360.html")

with open(HTML, encoding="utf-8") as f:
    html = f.read()

OLD = (
    "  var totTk=totalU>0?totalGraw/totalU:0;\n"
    "  var totCrecPct=totalPriG>0?((totalGraw/totalPriG-1)*100):null;"
    "var totCrecStr=totCrecPct===null?'—':((totCrecPct>=0?'+':'')+totCrecPct.toFixed(1)+'%');"
    "var totCrecC=totCrecPct===null?'var(--text3)':totCrecPct>=0?'var(--green)':'var(--red)';\n"
    "  var totRow='<tr style=\"background:linear-gradient(90deg,rgba(52,131,250,.07),transparent);"
    "border-top:2px solid var(--blue);border-bottom:2px solid var(--blue)\">'+\n"
    "    '<td style=\"padding:10px 10px 10px 12px\">"
    "<span style=\"font-size:12px;font-weight:800;color:var(--blue);text-transform:uppercase;"
    "letter-spacing:.3px\">📊 TOTAL PERÍODO</span>'+\n"
    "    '<span style=\"color:var(--text3);font-size:11px;margin-left:8px;font-weight:400\">"
    "'+cats.length+' categorías</span></td>'+\n"
    "    '<td style=\"font-weight:800;color:var(--blue);text-align:right;font-size:15px;"
    "padding-right:10px\">'+fmtM(totalGraw)+'</td>'+\n"
    "    '<td style=\"text-align:center\">"
    "<span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;"
    "font-size:11px;font-weight:700\">100%</span></td>'+\n"
    "    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtN(totalU)+'</td>'+\n"
    "    '<td style=\"text-align:center\">"
    "<span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;"
    "font-size:11px;font-weight:700\">100%</span></td>'+\n"
    "    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtM(totTk)+'</td>'+\n"
    "    '<td style=\"text-align:right;font-weight:800;color:'+totCrecC+'\">'+totCrecStr+'</td></tr>';"
)

NEW = (
    "  // SINGLE SOURCE OF TRUTH: usar DAILY_CUR (misma fuente que Resumen) para el total del período\n"
    "  var curGmv=0,curUnits=0;\n"
    "  for(var _dc=f;_dc<=t;_dc++){if(typeof DAILY_CUR!=='undefined'&&DAILY_CUR[String(_dc)])"
    "{curGmv+=DAILY_CUR[String(_dc)].gmv||0;curUnits+=DAILY_CUR[String(_dc)].units||0;}}\n"
    "  curGmv=Math.round(curGmv);\n"
    "  var totTk=curUnits>0?curGmv/curUnits:0;\n"
    "  var totCrecPct=totalPriG>0?((curGmv/totalPriG-1)*100):null;"
    "var totCrecStr=totCrecPct===null?'—':((totCrecPct>=0?'+':'')+totCrecPct.toFixed(1)+'%');"
    "var totCrecC=totCrecPct===null?'var(--text3)':totCrecPct>=0?'var(--green)':'var(--red)';\n"
    "  var totRow='<tr style=\"background:linear-gradient(90deg,rgba(52,131,250,.07),transparent);"
    "border-top:2px solid var(--blue);border-bottom:2px solid var(--blue)\">'+\n"
    "    '<td style=\"padding:10px 10px 10px 12px\">"
    "<span style=\"font-size:12px;font-weight:800;color:var(--blue);text-transform:uppercase;"
    "letter-spacing:.3px\">📊 TOTAL PERÍODO</span>'+\n"
    "    '<span style=\"color:var(--text3);font-size:11px;margin-left:8px;font-weight:400\">"
    "'+cats.length+' categorías</span></td>'+\n"
    "    '<td style=\"font-weight:800;color:var(--blue);text-align:right;font-size:15px;"
    "padding-right:10px\">'+fmtM(curGmv)+'</td>'+\n"
    "    '<td style=\"text-align:center\">"
    "<span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;"
    "font-size:11px;font-weight:700\">100%</span></td>'+\n"
    "    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtN(curUnits)+'</td>'+\n"
    "    '<td style=\"text-align:center\">"
    "<span style=\"background:var(--blue);color:#fff;border-radius:4px;padding:2px 7px;"
    "font-size:11px;font-weight:700\">100%</span></td>'+\n"
    "    '<td style=\"font-weight:700;text-align:right;padding-right:10px\">'+fmtM(totTk)+'</td>'+\n"
    "    '<td style=\"text-align:right;font-weight:800;color:'+totCrecC+'\">'+totCrecStr+'</td></tr>';"
)

if OLD not in html:
    # Ya aplicado o HTML diferente — verificar si ya está fixed
    if "curGmv=Math.round(curGmv)" in html:
        print("OK - patch ya aplicado previamente, nada que hacer")
        sys.exit(0)
    print("WARN - no se encontró el bloque exacto a parchear")
    print("       Es posible que ml_dashboard.py fue rebuildeado con la fuente corregida")
    sys.exit(0)

html = html.replace(OLD, NEW, 1)
with open(HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK patch_total_row_ventas aplicado ({len(html):,} bytes)")
