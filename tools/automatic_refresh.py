"""Bounded periodic official-source checks; promote only validated parsed context."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import requests
from tools import update_farmer_context as updater

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'/'processed'


def replace(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_bytes() if path.exists() else None
    if old == content:
        return
    if old is not None:
        archive = DATA/'refresh_archive'/hashlib.sha256(old).hexdigest()/path.name
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            archive.write_bytes(old)
    temp = path.with_suffix(path.suffix+'.refresh-tmp')
    temp.write_bytes(content)
    os.replace(temp, path)


def period_end(value):
    match = re.fullmatch(r'\s*\d{1,2}\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})\s*', value or '')
    if not match:
        raise ValueError('Unrecognized bulletin reference period')
    return datetime.strptime(' '.join(match.groups()), '%d %B %Y').date()


def valid_context(name, value, previous):
    if name == 'PAGASA agri-weather':
        end = period_end(value.get('forecastPeriod'))
        if not value.get('regions') or len(value['regions']) < len(previous.get('regions', [])):
            raise ValueError('Incomplete regional bulletin; retaining previous data')
        if previous.get('forecastPeriod') and end < period_end(previous['forecastPeriod']):
            raise ValueError('Older official bulletin; retaining previous data')
        return 'Published period ended' if end < datetime.now(timezone.utc).date() else 'Latest checked bulletin'
    enso = value.get('enso',{})
    if not enso.get('available') or not enso.get('issuedDate'):
        raise ValueError('Missing ENSO issue date')
    if enso['issuedDate'] < previous.get('enso',{}).get('issuedDate',''):
        raise ValueError('Older climate advisory')
    if not value.get('drought',{}).get('provinces'):
        raise ValueError('Missing provincial drought context')
    if set(previous.get('drought',{}).get('provinces',{})) - set(value['drought']['provinces']):
        raise ValueError('Drought coverage decreased; retaining previous release')
    return 'Latest checked advisory; inspect issue/reference dates'


def refresh_context(name, function, attribute, filename, stage):
    target = DATA/filename
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    setattr(updater, attribute, stage/filename)
    value = function()
    status = valid_context(name, value, previous)
    replace(target, (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode())
    return {'status':status,'lastSuccessfulCheckUtc':datetime.now(timezone.utc).isoformat()}


def check_publication(url):
    response = requests.get(url, timeout=(10,25), headers={'User-Agent':'ANI official-source freshness check'})
    response.raise_for_status()
    # A successful page fetch does not mean that numbers have been parsed/integrated.
    return {'status':'Official source reachable; automated release import not configured', 'sourceUrl':url, 'publicationPageSha256':hashlib.sha256(response.content).hexdigest()}


def refresh_market(stage):
    import pandas as pd
    target=DATA/'palay_farmgate_prices.csv'
    previous=pd.read_csv(target)
    updater.PRICE_PATH=stage/target.name
    value=updater.update_psa_farmgate_prices()
    from backend.data_refresh import validate_frame
    validate_frame(value,previous,'market')
    if (value.Year*12+value.Month_Number).max() < (previous.Year*12+previous.Month_Number).max():
        raise ValueError('Older farmgate price release')
    if len(value)<len(previous) or value.Price_PHP_per_kg.isna().any() or (value.Price_PHP_per_kg<0).any():
        raise ValueError('Incomplete or invalid farmgate prices')
    replace(target,(stage/target.name).read_bytes())
    return {'status':'Latest checked OpenSTAT prices','lastSuccessfulCheckUtc':datetime.now(timezone.utc).isoformat()}


def cycle():
    status_path = DATA/'refresh_status.json'
    previous = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {'sources':{}}
    status = {'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'intervalHours':6,'sources':dict(previous.get('sources',{}))}
    with tempfile.TemporaryDirectory(prefix='ani-source-refresh-') as folder:
        stage = Path(folder)
        actions = {
            'PSA farmgate prices':lambda:refresh_market(stage),
            'PAGASA agri-weather':lambda:refresh_context('PAGASA agri-weather',updater.update_pagasa_agri_weather,'PAGASA_PATH','pagasa_regional_agri_weather.json',stage),
            'PAGASA climate':lambda:refresh_context('PAGASA climate',updater.update_pagasa_climate_risk,'PAGASA_CLIMATE_PATH','pagasa_climate_risk.json',stage),
            'Near-Term Palay Outlook':lambda:check_publication('https://psa.gov.ph/statistics/crops/palay-and-corn-estimates'),
            'PSA agriculture':lambda:check_publication('https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/DB__2E__CS/'),
            'NASA POWER':lambda:check_publication('https://power.larc.nasa.gov/'),
            'Satellite':lambda:check_publication('https://planetarycomputer.microsoft.com/api/stac/v1/collections/modis-13A1-061'),
        }
        def run(name, action):
            old = status['sources'].get(name,{})
            try:
                value = action()
                if old.get('publicationPageSha256') and value.get('publicationPageSha256') != old['publicationPageSha256']:
                    value['status'] = 'Publication page changed; release verification/import required'
                return name, {**value,'lastAttemptUtc':datetime.now(timezone.utc).isoformat()}
            except Exception as exc:
                return name, {**old,'status':'Update check failed; retaining last integrated data','lastAttemptUtc':datetime.now(timezone.utc).isoformat(),'error':str(exc)}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(run,name,action) for name,action in actions.items()]
            for future in futures:
                name, value = future.result()
                status['sources'][name] = value
    replace(status_path, (json.dumps(status,indent=2)+'\n').encode())
    print(json.dumps(status), flush=True)
    return status


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    while True:
        try:
            cycle()
        except Exception as exc:
            print(f'ANI source refresh retained existing data: {exc}',flush=True)
        if args.once:
            return
        time.sleep(6*3600)


if __name__ == '__main__':
    main()
