"""
ml_fetch_reviews.py — Fetch calificaciones negativas (rate ≤ 2) del año en curso.
Escanea hasta 300 items activos en batches de 90 para respetar timeout.
Guarda: data/negative_reviews.json
"""
import sys, json, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
sys.path.insert(0, SCRIPT_DIR)
from ml_auth import MLSession

def fetch_negative_reviews(session=None, year=None, max_items=300):
    if session is None:
        session = MLSession()
    if year is None:
        year = datetime.now().year
    uid = session.user_id
    print(f"\n⭐ Fetching calificaciones negativas {year} (user {uid})...")

    # Step 1: get item IDs
    all_ids = []
    offset = 0
    while len(all_ids) < max_items:
        r = session.get(f"/users/{uid}/items/search", params={"limit": 50, "offset": offset})
        batch = r.get("results", [])
        if not batch: break
        all_ids.extend(batch)
        total = r.get("paging", {}).get("total", 0)
        offset += 50
        if offset >= total: break

    # Step 2: get titles in bulk
    titles = {}
    for i in range(0, len(all_ids), 20):
        try:
            r2 = session.get("/items", params={"ids": ",".join(all_ids[i:i+20])})
            for e in r2:
                b = e.get("body", {})
                titles[b.get("id","")] = b.get("title","")[:80]
        except: pass

    print(f"  📦 {len(all_ids)} items · {len(titles)} títulos")

    # Step 3: scan reviews per item (in chunks to avoid timeout in callers)
    neg = []
    item_neg_count = {}
    year_prefix = str(year)

    for item_id in all_ids:
        try:
            r = session.get(f"/reviews/item/{item_id}", params={"limit": 50, "sort": "date_desc"})
            for rv in r.get("reviews", []):
                d = (rv.get("date_created") or "")[:10]
                if not d.startswith(year_prefix): continue
                if rv.get("rate", 5) <= 2:
                    neg.append({
                        "item_id":      item_id,
                        "item_title":   titles.get(item_id, ""),
                        "rate":         rv["rate"],
                        "review_title": rv.get("title", ""),
                        "content":      (rv.get("content") or "")[:200],
                        "date":         d,
                        "likes":        rv.get("likes", 0),
                    })
                    if item_id not in item_neg_count:
                        item_neg_count[item_id] = {
                            "item_id": item_id,
                            "item_title": titles.get(item_id, ""),
                            "neg_count": 0
                        }
                    item_neg_count[item_id]["neg_count"] += 1
        except: pass

    neg.sort(key=lambda x: x.get("date",""), reverse=True)

    result = {
        "fetched_at":          datetime.now().isoformat(),
        "year_filter":         year,
        "total_items_checked": len(all_ids),
        "items_with_negative": len(item_neg_count),
        "total_negative":      len(neg),
        "item_summary":        sorted(item_neg_count.values(), key=lambda x: -x["neg_count"]),
        "reviews":             neg[:150],
    }
    out = os.path.join(DATA_DIR, "negative_reviews.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {len(neg)} neg reviews en {year} · {len(item_neg_count)} productos → {out}")
    return result

if __name__ == "__main__":
    fetch_negative_reviews()
