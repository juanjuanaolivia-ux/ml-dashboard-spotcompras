"""
fetch_retenciones.py — Obtiene retenciones REALES (IDB/IIBB) desde charges_details
via payments/search (NOT /v1/payments/{id} que devuelve charges vacíos)

Genera: data/retenciones_real.json
{
  "month": "2026-05",
  "total": 12345.67,
  "by_type": {"tax_withholding_collector-debitos_creditos": 12345.67},
  "count_payments": 1234,
  "fetched_at": "2026-05-25T..."
}
"""
import json, os, sys, datetime, urllib.request, urllib.parse, time

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
OUT  = os.path.join(DATA, 'retenciones_real.json')
API  = "https://api.mercadopago.com/v1/payments/search"

def run(month_str=None, force=False):
    sys.path.insert(0, BASE)
    from ml_auth import get_valid_token

    today = datetime.date.today()
    if month_str is None:
        month_str = today.strftime('%Y-%m')

    year, month = int(month_str[:4]), int(month_str[5:7])
    begin = f"{month_str}-01T00:00:00Z"
    # last day of month or today
    import calendar
    last_day = min(today.day, calendar.monthrange(year, month)[1]) if (year == today.year and month == today.month) else calendar.monthrange(year, month)[1]
    end = f"{month_str}-{last_day:02d}T23:59:59Z"

    # Check cache
    if not force and os.path.exists(OUT):
        try:
            cached = json.load(open(OUT))
            if cached.get('month') == month_str:
                fetched = cached.get('fetched_at', '')[:10]
                if fetched == today.isoformat():
                    print(f"  [retenciones] Cache válido para {month_str} (fetched hoy)")
                    return cached
        except Exception:
            pass

    tok, _ = get_valid_token()
    headers = {"Authorization": f"Bearer {tok}"}

    total_tax   = 0.0
    by_type     = {}
    count_pay   = 0
    offset      = 0
    limit       = 100
    pages       = 0

    print(f"  [retenciones] Fetching {month_str} ({begin} → {end})...")

    while True:
        params = urllib.parse.urlencode({
            "begin_date": begin,
            "end_date":   end,
            "status":     "approved",
            "sort":       "date_created",
            "criteria":   "asc",
            "offset":     offset,
            "limit":      limit,
        })
        req = urllib.request.Request(f"{API}?{params}", headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
        except Exception as e:
            print(f"  [retenciones] ERROR en offset {offset}: {e}")
            break

        results = data.get('results', [])
        paging  = data.get('paging', {})
        total   = paging.get('total', 0)

        if not results:
            break

        for p in results:
            charges = p.get('charges_details', [])
            for c in charges:
                if c.get('type') == 'tax':
                    amt  = c.get('amounts', {}).get('original', 0)
                    name = c.get('name', 'unknown_tax')
                    total_tax += amt
                    by_type[name] = round(by_type.get(name, 0) + amt, 2)

        count_pay += len(results)
        offset    += len(results)
        pages     += 1

        if offset >= total or len(results) < limit:
            break

        # Rate limit: evitar 429
        if pages % 10 == 0:
            time.sleep(0.5)

    result = {
        "month":           month_str,
        "total":           round(total_tax, 2),
        "by_type":         by_type,
        "count_payments":  count_pay,
        "fetched_at":      datetime.datetime.now().isoformat(),
        "begin":           begin,
        "end":             end,
    }

    os.makedirs(DATA, exist_ok=True)
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(result, f, indent=2)
    os.replace(tmp, OUT)

    print(f"  [retenciones] TOTAL={result['total']:,.0f} | pagos={count_pay} | tipos={list(by_type.keys())}")
    return result


if __name__ == '__main__':
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else None
    r = run(month, force=True)
    print(json.dumps(r, indent=2, ensure_ascii=False))
