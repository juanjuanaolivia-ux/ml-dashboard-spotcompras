"""
Fetch collections en batches pequeños. NO toca collections_raw.json hasta terminar.
"""
import sys, os, json, time, glob
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE    = os.path.dirname(os.path.abspath(__file__))
DATA    = os.path.join(BASE, 'data')
BATCHES = os.path.join(DATA, 'col_batches')
os.makedirs(BATCHES, exist_ok=True)

def state():
    s = os.path.join(BATCHES,'state.json')
    try: return json.load(open(s))
    except: return {'offset':0}

def save_state(offset):
    with open(os.path.join(BATCHES,'state.json'),'w') as f: json.dump({'offset':offset},f)

def next_batch_num():
    batches = glob.glob(os.path.join(BATCHES,'batch_*.json'))
    return len(batches)

def all_ids():
    ids = set()
    for b in glob.glob(os.path.join(BATCHES,'batch_*.json')):
        try:
            for r in json.load(open(b)): ids.add(r.get('id'))
        except: pass
    return ids

import requests as _req
def _token():
    with open(os.path.join(BASE,'ml_tokens.json')) as f: return json.load(f)['access_token']

def run():
    from ml_auth import MLSession
    session     = MLSession()
    tok         = _token()
    today       = date.today()
    target_from = (today - timedelta(days=40)).strftime('%Y-%m-%d')

    st     = state()
    offset = st.get('offset', 0)
    seen   = all_ids()
    bnum   = next_batch_num()
    print(f"Offset={offset} | Batches={bnum} | IDs vistos={len(seen)} | Target desde {target_from}")

    start = time.time()
    done  = False

    while not done:
        if time.time() - start > 36:
            print(f"\n⏱ Timeout seguro — offset={offset} guardado")
            break

        try:
            r = _req.get('https://api.mercadolibre.com/collections/search',
                headers={'Authorization': f'Bearer {tok}'},
                params={'seller_id': session.user_id, 'sort':'date_created',
                        'criteria':'desc', 'offset':offset, 'limit':50},
                timeout=15)
            r.raise_for_status()
            results = r.json().get('results',[])
        except Exception as e:
            print(f"\nError: {e}"); break

        if not results: done=True; break

        batch = []
        for item in results:
            c = item.get('collection', item)
            if (c.get('date_created') or '')[:10] < target_from:
                done=True; break
            if c.get('id') not in seen:
                batch.append(c); seen.add(c.get('id'))

        # Save this batch immediately (tiny file, instant)
        if batch:
            with open(os.path.join(BATCHES,f'batch_{bnum:05d}.json'),'w') as f:
                json.dump(batch, f, ensure_ascii=False)
            bnum += 1

        offset += len(results)
        save_state(offset)  # tiny file, instant

        print(f"  ~{len(seen):,} únicos | offset={offset} | {time.time()-start:.0f}s", end='\r')
        if done: break
        time.sleep(0.12)

    # Summary
    print(f"\nBatches guardados: {bnum} | IDs únicos: {len(seen)} | Completo: {done}")

    if done:
        # Only merge when fully done
        print("Mergeando en collections_raw.json...")
        all_rec = []
        merged_ids = set()
        for b in sorted(glob.glob(os.path.join(BATCHES,'batch_*.json'))):
            for r in json.load(open(b)):
                if r.get('id') not in merged_ids:
                    all_rec.append(r); merged_ids.add(r.get('id'))
        tmp = os.path.join(DATA,'collections_raw.json.tmp')
        with open(tmp,'w',encoding='utf-8') as f: json.dump(all_rec,f,ensure_ascii=False)
        os.replace(tmp, os.path.join(DATA,'collections_raw.json'))
        dates = sorted(set(r.get('date_created','')[:10] for r in all_rec if r.get('date_created')))
        print(f"✅ collections_raw: {len(all_rec)} | {dates[0]}→{dates[-1]}")
    return done

done = run()
sys.exit(0 if done else 2)
