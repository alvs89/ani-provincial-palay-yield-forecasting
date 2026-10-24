import json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import pandas as pd, requests
ROOT=Path(__file__).resolve().parents[1]
CENT=ROOT/'data/reference/province_centroids.csv'
OUT=ROOT/'data/processed/province_quarter_climate_extremes.csv'
CACHE=ROOT/'data/cache/power_daily'; CACHE.mkdir(parents=True,exist_ok=True)
PARAMS='PRECTOTCORR,T2M_MAX,T2M_MIN'

def longest_run(mask):
    best=cur=0
    for v in mask:
        cur=cur+1 if bool(v) else 0; best=max(best,cur)
    return best

def fetch(row):
    p=CACHE/(row.Province.replace('/','_')+'.json')
    if p.exists(): return json.loads(p.read_text())
    u='https://power.larc.nasa.gov/api/temporal/daily/point'
    q={'parameters':PARAMS,'community':'AG','longitude':row.Longitude,'latitude':row.Latitude,'start':'20010101','end':'20251231','format':'JSON','time-standard':'LST'}
    last=None
    for attempt in range(6):
        try:
            x=requests.get(u,params=q,timeout=180); x.raise_for_status(); j=x.json()
            p.write_text(json.dumps(j)); time.sleep(2.0); return j
        except requests.RequestException as exc:
            last=exc; time.sleep(3*(attempt+1))
    raise last

def main():
    out=[]; rows=list(pd.read_csv(CENT).itertuples(index=False))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch,row):row for row in rows}
        for i,future in enumerate(as_completed(futures),1):
            row=futures[future]; j=future.result(); par=j['properties']['parameter']; dates=sorted(par['PRECTOTCORR'])
            d=pd.DataFrame({'date':pd.to_datetime(dates),'pr':[par['PRECTOTCORR'][x] for x in dates],'tx':[par['T2M_MAX'][x] for x in dates],'tn':[par['T2M_MIN'][x] for x in dates]})
            d=d.replace(-999,pd.NA).dropna(); d['Year']=d.date.dt.year; d['Quarter']=d.date.dt.quarter
            for (y,q),g in d.groupby(['Year','Quarter']):
                out.append({'Province':row.Province,'Year':int(y),'Quarter':int(q),'Rainfall_Daily_Sum_mm':float(g.pr.sum()),'Rainy_Days_1mm':int((g.pr>=1).sum()),'Heavy_Rain_Days_20mm':int((g.pr>=20).sum()),'Very_Heavy_Rain_Days_50mm':int((g.pr>=50).sum()),'Consecutive_Dry_Days_Max':int(longest_run(g.pr<1)),'Hot_Days_35C':int((g.tx>=35).sum()),'Very_Hot_Days_37C':int((g.tx>=37).sum()),'Warm_Nights_25C':int((g.tn>=25).sum()),'Tmax_Mean_C':float(g.tx.mean()),'Tmin_Mean_C':float(g.tn.mean())})
            print(f'{i}/82 {row.Province}',flush=True)
    pd.DataFrame(out).sort_values(['Province','Year','Quarter']).to_csv(OUT,index=False); print(OUT)
if __name__=='__main__': main()
