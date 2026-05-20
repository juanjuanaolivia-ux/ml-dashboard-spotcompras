"""
ml_ads_fetch.py
Fetches Product Ads daily metrics from ML API (new endpoints, post Feb-2026)
and saves to data/ads_daily.json

Usage:
    python3 ml_ads_fetch.py              # last 30 days
    python3 ml_ads_fetch.py 60           # last N days
    python3 ml_ads_fetch.py 2026-04-01 2026-05-19  # custom range
"""
import sys, json, os, requests
from datetime import date, timedelta
from ml_auth import get_valid_token

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE   = os.path.join(SCRIPT_DIR, 'data', 'ads_daily.json')

BASE_URL  = 'https://api.mercadolibre.com'
SITE_ID   = 'MLA'
# Metrics that return the full picture in fewest calls:
# acos  → cost, direct_amount, indirect_amount, total_amount, acos
# roas  → + roas
# ctr   → + clicks, prints, ctr
# cpc   → + cpc
METRICS = ['acos', 'roas', 'ctr', 'cpc',
           'direct_units_quantity', 'indirect_units_quantity',
           'direct_items_quantity', 'indirect_items_quantity']

def get_advertiser_id(token):
    r = requests.get(f'{BASE_URL}/advertising/advertisers?product_id=PADS',
                     headers={'Authorization': f'Bearer {token}', 'Api-Version': '2'})
    r.raise_for_status()
    advs = r.json().get('advertisers', [])
    if not advs:
        raise RuntimeError('No advertiser found for this account')
    return advs[0]['advertiser_id']

def fetch_metric_daily(token, adv_id, date_from, date_to, metric):
    """Fetch one metric, returns {date_str: {field: value, ...}}"""
    r = requests.get(
        f'{BASE_URL}/marketplace/advertising/{SITE_ID}/advertisers/{adv_id}/product_ads/ads/search',
        params={
            'date_from':        date_from,
            'date_to':          date_to,
            'aggregation_type': 'daily',
            'metrics':          metric,
            'limit':            90,
        },
        headers={'Authorization': f'Bearer {token}', 'Api-Version': '2'},
        timeout=15
    )
    r.raise_for_status()
    results = {}
    for row in r.json().get('results', []):
        d = row.pop('date', None)
        if d:
            results[d] = row
    return results

def merge(base, extra):
    """Merge extra day-level dicts into base"""
    for d, vals in extra.items():
        if d not in base:
            base[d] = {}
        base[d].update(vals)
    return base

def fetch_all(date_from, date_to):
    token, _ = get_valid_token()
    adv_id   = get_advertiser_id(token)
    print(f'Advertiser: {adv_id} | Range: {date_from} → {date_to}')

    daily = {}
    for metric in METRICS:
        print(f'  Fetching {metric}...', end=' ', flush=True)
        try:
            data = fetch_metric_daily(token, adv_id, date_from, date_to, metric)
            merge(daily, data)
            print(f'{len(data)} days')
        except Exception as e:
            print(f'ERROR: {e}')

    # Add computed totals
    for d, v in daily.items():
        v['total_amount']  = round((v.get('direct_amount', 0) or 0) +
                                   (v.get('indirect_amount', 0) or 0), 2)
        v['total_units']   = (v.get('direct_units_quantity', 0) or 0) + \
                             (v.get('indirect_units_quantity', 0) or 0)
        v['total_items']   = (v.get('direct_items_quantity', 0) or 0) + \
                             (v.get('indirect_items_quantity', 0) or 0)

    # Sort by date
    daily_sorted = dict(sorted(daily.items()))
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'fetched_at': date.today().isoformat(),
                   'date_from':  date_from,
                   'date_to':    date_to,
                   'advertiser_id': adv_id,
                   'daily': daily_sorted}, f, indent=2)

    print(f'\nGuardado en {OUT_FILE} ({len(daily_sorted)} días)')
    # Summary
    total_cost = sum(v.get('cost', 0) or 0 for v in daily_sorted.values())
    total_rev  = sum(v.get('total_amount', 0) or 0 for v in daily_sorted.values())
    total_u    = sum(v.get('total_units', 0) or 0 for v in daily_sorted.values())
    avg_roas   = total_rev / total_cost if total_cost else 0
    print(f'  Inversión:  ${total_cost/1e6:.2f}M')
    print(f'  Ingresos:   ${total_rev/1e6:.2f}M')
    print(f'  Ventas:     {total_u:,} u')
    print(f'  ROAS prom:  {avg_roas:.2f}x')
    return daily_sorted

if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 2:
        date_from, date_to = args
    elif len(args) == 1:
        days = int(args[0])
        date_to   = date.today().isoformat()
        date_from = (date.today() - timedelta(days=days-1)).isoformat()
    else:
        date_to   = date.today().isoformat()
        date_from = (date.today() - timedelta(days=29)).isoformat()

    fetch_all(date_from, date_to)
