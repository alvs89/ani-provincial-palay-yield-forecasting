#!/usr/bin/env python3
"""ANI Pilot Stage 3 — Public future-condition layer for Nueva Ecija."""
from __future__ import annotations
import argparse, json, math, time
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
import requests
import rasterio

PROVINCE='Nueva Ecija'; LAT=15.5833; LON=121.0000; TZ='Asia/Manila'
OUT=Path('data/pilot'); OUT.mkdir(parents=True, exist_ok=True)
CACHE=OUT/'cache'; CACHE.mkdir(parents=True, exist_ok=True)
STAGE1=OUT/'nueva_ecija_pilot_conditions.json'
OM='https://api.open-meteo.com/v1/forecast'
C3G='https://data.chc.ucsb.edu/products/CHIRPS-GEFS/v3/10_day/global/data'
S=requests.Session(); S.headers.update({'User-Agent':'ANI-CS406-academic-project/3.0'})

def get(url, params=None, timeout=90, attempts=4, stream=False):
    last=None
    for i in range(attempts):
        try:
            r=S.get(url,params=params,timeout=timeout,stream=stream); r.raise_for_status(); return r
        except Exception as e:
            last=e; time.sleep(min(2**(i+1),8))
    raise RuntimeError(f'GET failed: {url}\n{last}')

def remote_exists(url):
    try:
        r=S.get(url,headers={'Range':'bytes=0-0'},timeout=20,stream=True)
        return r.status_code in (200,206)
    except Exception: return False

def load_stage1():
    if not STAGE1.exists(): raise FileNotFoundError(f'Missing {STAGE1}; run Stage 1 first.')
    return json.loads(STAGE1.read_text(encoding='utf-8'))

def openmeteo(days=16):
    p={'latitude':LAT,'longitude':LON,'timezone':TZ,'forecast_days':min(max(days,1),16),
       'hourly':','.join(['temperature_2m','relative_humidity_2m','precipitation','precipitation_probability','weather_code','wind_speed_10m','wind_gusts_10m','soil_moisture_0_to_7cm','soil_moisture_7_to_28cm']),
       'daily':','.join(['temperature_2m_max','temperature_2m_min','temperature_2m_mean','precipitation_sum','precipitation_probability_max','weather_code','wind_speed_10m_max','wind_gusts_10m_max'])}
    raw=get(OM,p,60).json()
    h=pd.DataFrame(raw['hourly']); h['time']=pd.to_datetime(h['time']); h['date']=h.time.dt.date
    d=pd.DataFrame(raw['daily']); d['date']=pd.to_datetime(d['time']).dt.date
    return raw,h,d

def summary(h,d,start,days):
    end=start+timedelta(days=days-1)
    h=h[(h.date>=start)&(h.date<=end)].copy(); d=d[(d.date>=start)&(d.date<=end)].copy()
    if d.empty: raise RuntimeError(f'No Open-Meteo forecast for {start}–{end}.')
    num=lambda f,c: pd.to_numeric(f[c],errors='coerce') if c in f else pd.Series(dtype=float)
    mean=lambda f,c: None if num(f,c).dropna().empty else round(float(num(f,c).mean()),3)
    mx=lambda f,c: None if num(f,c).dropna().empty else round(float(num(f,c).max()),3)
    mn=lambda f,c: None if num(f,c).dropna().empty else round(float(num(f,c).min()),3)
    sm=lambda f,c: None if num(f,c).dropna().empty else round(float(num(f,c).sum()),2)
    return {
      'forecast_start':start.isoformat(),'forecast_end':end.isoformat(),'days_available':len(d),
      'forecast_rainfall_mm':sm(d,'precipitation_sum'),
      'forecast_rainy_days_ge_1mm':int((num(d,'precipitation_sum')>=1).sum()),
      'forecast_precip_probability_max_pct':mx(d,'precipitation_probability_max'),
      'forecast_temp_mean_c':mean(d,'temperature_2m_mean'),'forecast_temp_max_c':mx(d,'temperature_2m_max'),'forecast_temp_min_c':mn(d,'temperature_2m_min'),
      'forecast_rh_mean_pct':mean(h,'relative_humidity_2m'),'forecast_wind_mean_kmh':mean(h,'wind_speed_10m'),'forecast_wind_gust_max_kmh':mx(d,'wind_gusts_10m_max'),
      'forecast_soil_moisture_0_7cm_mean_m3_m3':mean(h,'soil_moisture_0_to_7cm'),'forecast_soil_moisture_7_28cm_mean_m3_m3':mean(h,'soil_moisture_7_to_28cm'),
      'technical_note':'Rainy day >=1 mm is a display convention only, not an agronomic threshold.'}

def latest_c3g(max_back=10):
    today=date.today()
    for back in range(max_back+1):
        issue=today-timedelta(days=back); fn=f'c3g_{issue:%Y.%m.%d}.tif'; url=f'{C3G}/{issue.year}/{fn}'
        print('Checking CHIRPS3-GEFS issue',issue,flush=True)
        if remote_exists(url): return issue,url
    raise RuntimeError('No CHIRPS3-GEFS 10-day raster found in last 11 days.')

def sample_c3g():
    issue,url=latest_c3g()
    try:
        with rasterio.open(url) as src:
            v=float(next(src.sample([(LON,LAT)]))[0]); nod=src.nodata
            if (nod is not None and v==nod) or v<=-900: v=None
            return {'issue_date':issue.isoformat(),'forecast_rainfall_10day_mm':None if v is None else round(v,2),'source_url':url,'access_method':'remote_range'}
    except Exception:
        local=CACHE/url.split('/')[-1]
        if not local.exists():
            print('Downloading CHIRPS3-GEFS raster (~60 MB) once...',flush=True)
            with get(url,timeout=240,stream=True) as r, open(local,'wb') as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk: f.write(chunk)
        with rasterio.open(local) as src:
            v=float(next(src.sample([(LON,LAT)]))[0]); nod=src.nodata
            if (nod is not None and v==nod) or v<=-900: v=None
            return {'issue_date':issue.isoformat(),'forecast_rainfall_10day_mm':None if v is None else round(v,2),'source_url':url,'access_method':'local_download'}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--ecosystem',choices=['Irrigated','Rainfed'],default='Rainfed'); ap.add_argument('--water',default='Unknown'); ap.add_argument('--start'); ap.add_argument('--days',type=int,default=10); ap.add_argument('--skip-gefs',action='store_true'); a=ap.parse_args()
    if not 1<=a.days<=10: raise SystemExit('--days must be 1–10.')
    start=datetime.strptime(a.start,'%Y-%m-%d').date() if a.start else date.today()+timedelta(days=1)
    print('=== ANI Pilot Stage 3 ==='); print(PROVINCE,a.ecosystem,'| water:',a.water,'| window:',start,'to',start+timedelta(days=a.days-1))
    s1=load_stage1(); raw,h,d=openmeteo(); om=summary(h,d,start,a.days)
    h.to_csv(OUT/'nueva_ecija_openmeteo_hourly.csv',index=False); d.to_csv(OUT/'nueva_ecija_openmeteo_daily.csv',index=False)
    (OUT/'nueva_ecija_openmeteo_raw.json').write_text(json.dumps(raw,indent=2),encoding='utf-8')
    if a.skip_gefs: c3g={'status':'skipped'}
    else:
        try: c3g=sample_c3g()
        except Exception as e: c3g={'status':'not completed','error':str(e),'fallback':'Open-Meteo rainfall available'}
    (OUT/'nueva_ecija_chirps3_gefs.json').write_text(json.dumps(c3g,indent=2),encoding='utf-8')
    r10=s1.get('nasa_recent_10d',{}); r30=s1.get('nasa_recent_30d',{}); an=s1.get('nasa_rainfall_anomaly',{}); cr=s1.get('chirps_v3_recent',{})
    rec={
      'Province':PROVINCE,'Latitude':LAT,'Longitude':LON,'Ecosystem':a.ecosystem,'Water_Availability':a.water,
      'Intended_Planting_Start':start.isoformat(),'Intended_Planting_End':(start+timedelta(days=a.days-1)).isoformat(),
      'Latest_Observed_NASA_Date':s1.get('latest_complete_nasa_date'),'Recent_NASA_Rainfall_10d_mm':r10.get('rainfall_mm'),'Recent_NASA_Rainfall_30d_mm':r30.get('rainfall_mm'),
      'Recent_NASA_Rainfall_10d_Anomaly_pct':an.get('rainfall_10d_anomaly_pct'),'Recent_NASA_Rainfall_30d_Anomaly_pct':an.get('rainfall_30d_anomaly_pct'),
      'Recent_CHIRPS_Rainfall_10d_Approx_mm':cr.get('rainfall_10d_approx_mm') if isinstance(cr,dict) else None,'Recent_CHIRPS_Rainfall_30d_Approx_mm':cr.get('rainfall_30d_approx_mm') if isinstance(cr,dict) else None,
      'Recent_NASA_Temperature_10d_C':r10.get('mean_temperature_c'),'Recent_NASA_RH_10d_pct':r10.get('mean_rh_pct'),'Recent_NASA_Wind_10d_m_s':r10.get('mean_wind_m_s'),
      'OpenMeteo_Forecast_Rainfall_mm':om['forecast_rainfall_mm'],'OpenMeteo_Forecast_Rainy_Days_ge_1mm':om['forecast_rainy_days_ge_1mm'],'OpenMeteo_Forecast_Precip_Probability_Max_pct':om['forecast_precip_probability_max_pct'],
      'OpenMeteo_Forecast_Temp_Mean_C':om['forecast_temp_mean_c'],'OpenMeteo_Forecast_Temp_Max_C':om['forecast_temp_max_c'],'OpenMeteo_Forecast_RH_Mean_pct':om['forecast_rh_mean_pct'],'OpenMeteo_Forecast_Wind_Mean_kmh':om['forecast_wind_mean_kmh'],'OpenMeteo_Forecast_Wind_Gust_Max_kmh':om['forecast_wind_gust_max_kmh'],
      'OpenMeteo_Soil_Moisture_0_7cm_Mean_m3_m3':om['forecast_soil_moisture_0_7cm_mean_m3_m3'],'OpenMeteo_Soil_Moisture_7_28cm_Mean_m3_m3':om['forecast_soil_moisture_7_28cm_mean_m3_m3'],
      'CHIRPS3_GEFS_Issue_Date':c3g.get('issue_date'),'CHIRPS3_GEFS_10d_Rainfall_mm':c3g.get('forecast_rainfall_10day_mm'),
      'Planting_Condition':'PENDING_EVIDENCE_BASED_RULES','Recommendation':'PENDING_EVIDENCE_BASED_RULES'}
    pd.DataFrame([rec]).to_csv(OUT/'nueva_ecija_stage3_condition_record.csv',index=False)
    final={'record':rec,'open_meteo_summary':om,'chirps3_gefs':c3g,'recommendation_enabled':False,'limitations':['Representative province point only.','Open-Meteo and CHIRPS3-GEFS are not official PAGASA forecasts.','Forecast soil moisture is modeled, not field-measured.','No cyclone is inferred from generic rain/wind values.']}
    (OUT/'nueva_ecija_stage3_condition_record.json').write_text(json.dumps(final,indent=2),encoding='utf-8')
    print('\n=== Stage 3 complete ==='); print('Open-Meteo rainfall:',om['forecast_rainfall_mm'],'mm'); print('Rainy days:',om['forecast_rainy_days_ge_1mm']); print('Mean temp:',om['forecast_temp_mean_c'],'C'); print('Mean RH:',om['forecast_rh_mean_pct'],'%'); print('Max gust:',om['forecast_wind_gust_max_kmh'],'km/h'); print('Soil moisture 0-7cm:',om['forecast_soil_moisture_0_7cm_mean_m3_m3'])
    print('CHIRPS3-GEFS 10-day rainfall:',c3g.get('forecast_rainfall_10day_mm'),'mm | issue:',c3g.get('issue_date'))
    print('NO planting recommendation generated yet. Send the CSV/JSON and terminal output for Stage 4.')

if __name__=='__main__': main()
