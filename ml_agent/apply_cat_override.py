"""
apply_cat_override.py
Aplica data/cat_manual_override.json sobre cat_names.json y redeploya.
Correr después de editar cat_manual_override.json.
"""
import os, json

BASE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")

override_path  = os.path.join(DATA_DIR, "cat_manual_override.json")
cat_names_path = os.path.join(DATA_DIR, "cat_names.json")

override  = json.load(open(override_path,  encoding="utf-8")) or {}
cat_names = json.load(open(cat_names_path, encoding="utf-8")) or {}

updated = 0
skipped = 0
for cid, nombre in override.items():
    if nombre.strip():
        old = cat_names.get(cid, "")
        cat_names[cid] = nombre.strip().upper()
        if old != cat_names[cid]:
            print(f"  {cid}: '{old}' → '{cat_names[cid]}'")
            updated += 1
    else:
        skipped += 1

with open(cat_names_path, "w", encoding="utf-8") as f:
    json.dump(cat_names, f, ensure_ascii=False, indent=2)

print(f"\nOK: {updated} actualizados, {skipped} vacíos omitidos")
print("Siguiente paso: deploy_rapido.bat")
