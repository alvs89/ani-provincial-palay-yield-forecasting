"""Reload validated operational data without refitting models or losing good snapshots."""
from __future__ import annotations
import asyncio
import hashlib
import json
import time
import sys
import re
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd


def signature(paths):
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else (str(p), None, None) for p in paths)


def period(frame):
    quarter = 'Quarter_Number' if 'Quarter_Number' in frame else 'Quarter'
    if frame.empty or not {'Year', quarter} <= set(frame):
        return None
    row = frame.sort_values(['Year', quarter]).iloc[-1]
    return f"Q{int(row[quarter])} {int(row.Year)}"


def validate_frame(frame, previous, name):
    if frame.empty and not previous.empty:
        raise ValueError(f'{name}: refusing an empty replacement')
    if not set(previous.columns) <= set(frame.columns):
        raise ValueError(f'{name}: missing established columns')
    quarter = 'Quarter_Number' if 'Quarter_Number' in frame else 'Quarter'
    keys = [k for k in ('Province', 'Ecosystem', 'Commodity', 'Year', quarter, 'Month_Number') if k in frame]
    if keys and frame.duplicated(keys).any():
        raise ValueError(f'{name}: duplicate observation keys')
    for column in ('Year', quarter):
        if column in frame and pd.to_numeric(frame[column], errors='coerce').isna().any():
            raise ValueError(f'{name}: invalid periods')
    if quarter in frame and not frame[quarter].between(1, 4).all():
        raise ValueError(f'{name}: invalid quarter')
    if {'Year', quarter} <= set(frame) and not previous.empty:
        if (frame.Year*4+frame[quarter]).max() < (previous.Year*4+previous[quarter]).max():
            raise ValueError(f'{name}: older replacement')
    for column in ('Yield_mt_per_ha', 'Production_mt', 'Area_Harvested_ha'):
        if column in frame:
            values = pd.to_numeric(frame[column], errors='coerce')
            if ((frame[column].notna() & values.isna()) | (values < 0)).any():
                raise ValueError(f'{name}: invalid agricultural values')


class OperationalRefresh:
    def __init__(self, namespace):
        self.ns = namespace
        self.frames = {'history_df':'HISTORY_PATH', 'weather_df':'WEATHER_PATH', 'satellite_df':'SATELLITE_PATH', 'market_df':'MARKET_PATH', 'enso_history_df':'ENSO_HISTORY_PATH', 'agricultural_source_df':'AGRICULTURAL_SOURCE_PATH'}
        self.objects = {'pagasa_agri_weather':'PAGASA_AGRI_WEATHER_PATH', 'pagasa_climate_risk':'PAGASA_CLIMATE_RISK_PATH', 'psa_near_term_outlook':'PSA_NEAR_TERM_OUTLOOK_PATH'}
        self.paths = [namespace[key] for key in (*self.frames.values(), *self.objects.values())]
        self.paths += [namespace['DATA_DIR']/'data_provenance.json', namespace['DATA_DIR']/'refresh_status.json']
        self.accepted = signature(self.paths)
        self.generation = hashlib.sha256(repr(self.accepted).encode()).hexdigest()[:16]
        self.checked = 0
        self.error = None
        self.provenance = self.read_json(namespace['DATA_DIR']/'data_provenance.json', {})

    @staticmethod
    def read_json(path, default):
        return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

    def refresh(self, force=False):
        if not force and time.monotonic()-self.checked < 5:
            return
        self.checked = time.monotonic()
        before = signature(self.paths)
        if before == self.accepted:
            return
        try:
            candidate = {}
            for name, key in self.frames.items():
                path = self.ns[key]
                if not path.exists() and not self.ns[name].empty:
                    raise ValueError(f'{name}: source file unavailable')
                frame = pd.read_csv(path) if path.exists() else pd.DataFrame()
                validate_frame(frame, self.ns[name], name)
                candidate[name] = frame
            for name, key in self.objects.items():
                value = self.read_json(self.ns[key], None)
                if value is None and self.ns[name] is not None:
                    raise ValueError(f'{name}: source file unavailable')
                if value is not None and not isinstance(value, dict):
                    raise ValueError(f'{name}: invalid source record')
                if value is not None:
                    required={'pagasa_agri_weather':('forecastPeriod','regions'), 'pagasa_climate_risk':('enso','drought'), 'psa_near_term_outlook':('releaseDate','referencePeriod','standingCrop')}[name]
                    if any(not value.get(key) for key in required):
                        raise ValueError(f'{name}: incomplete official record')
                    if name=='psa_near_term_outlook' and self.ns[name] and value['releaseDate']<self.ns[name].get('releaseDate',''):
                        raise ValueError('Refusing older standing-crop release')
                candidate[name] = value
            provenance = self.read_json(self.ns['DATA_DIR']/'data_provenance.json', {})
            # Build derived objects before committing any globals. The trained pipeline stays fixed.
            candidate['builder'] = self.ns['AniFeatureBuilder'](candidate['history_df'], candidate['weather_df'])
            candidate['long_term_projector'] = self.ns['LongTermProjector'](candidate['history_df'], candidate['weather_df'])
            candidate['province_region'] = candidate['history_df'].sort_values(['Year','Quarter_Number']).drop_duplicates('Province', keep='last').set_index('Province').Region_Context.to_dict()
            candidate['province_region'].update({'Negros Occidental':'NEGROS ISLAND REGION','Negros Oriental':'NEGROS ISLAND REGION','Siquijor':'NEGROS ISLAND REGION','Sulu':'REGION IX (ZAMBOANGA PENINSULA)'})
            if before != signature(self.paths):
                raise ValueError('Source files changed during reload; retrying next check')
            self.ns.update(candidate)
            self.provenance = provenance
            self.accepted = before
            self.generation = hashlib.sha256(repr(before).encode()).hexdigest()[:16]
            self.error = None
        except Exception as exc:
            self.error = str(exc)

    def freshness(self):
        ns = self.ns
        official = self.read_json(ns['DATA_DIR']/'refresh_status.json', {})
        agri = ns['pagasa_agri_weather'] or {}
        climate = ns['pagasa_climate_risk'] or {}
        near = ns['psa_near_term_outlook'] or {}
        sources = {
            'PSA agriculture': {'referencePeriod':period(ns['history_df']), 'releaseDate':self.provenance.get('agricultural_data',{}).get('source_version_date'), 'cadence':'Quarterly; publication may lag the reference quarter'},
            'NASA POWER': {'referencePeriod':period(ns['weather_df']), 'releaseDate':None, 'cadence':'Daily observations aggregated to completed quarters'},
            'Satellite': {'referencePeriod':period(ns['satellite_df']), 'releaseDate':None, 'cadence':'16-day composites aggregated to completed quarters'},
            'PAGASA agri-weather': {'referencePeriod':agri.get('forecastPeriod'), 'releaseDate':agri.get('releaseDate'), 'retrievedAtUtc':agri.get('retrievedAtUtc'), 'cadence':'10-day bulletin'},
            'PAGASA climate': {'referencePeriod':climate.get('enso',{}).get('title'), 'releaseDate':climate.get('enso',{}).get('issuedDate'), 'cadence':'Periodic official advisories'},
            'Near-Term Palay Outlook': {'referencePeriod':near.get('referencePeriod'), 'releaseDate':near.get('releaseDate'), 'cadence':'Periodic PSA standing-crop release'},
        }
        market=ns['market_df']
        latest=market.sort_values(['Year','Month_Number']).iloc[-1] if not market.empty else None
        sources['PSA farmgate prices']={'referencePeriod':f"{int(latest.Year)}-{int(latest.Month_Number):02d}" if latest is not None else None,'releaseDate':None,'cadence':'Monthly published prices'}
        for name, item in sources.items():
            check = official.get('sources',{}).get(name,{})
            item.update(check)
            item.setdefault('status','Latest integrated data; official latest release not verified')
            item['releaseDate'] = item.get('releaseDate') or None
            if self.error:
                item['status']='Reload failed; displaying previous integrated snapshot'
        match = re.fullmatch(r'\s*\d{1,2}\s*[-–]\s*(\d{1,2}\s+[A-Za-z]+\s+20\d{2})\s*',agri.get('forecastPeriod',''))
        if match:
            end = datetime.strptime(match[1],'%d %B %Y').date()
            if end < datetime.now(ZoneInfo('Asia/Manila')).date():
                sources['PAGASA agri-weather']['status'] = 'Published forecast period ended; '+sources['PAGASA agri-weather']['status']
        return {'generation':self.generation,'checkedAtUtc':datetime.now(timezone.utc).isoformat(),'reloadError':self.error,'sources':sources}


def install(app, namespace):
    refresh = OperationalRefresh(namespace)
    lock = asyncio.Lock()
    worker = None

    async def source_checks():
        while True:
            child = None
            try:
                child = await asyncio.create_subprocess_exec(sys.executable, '-m', 'tools.automatic_refresh', '--once', cwd=namespace['ROOT'], stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(child.wait(), timeout=300)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # A failed check cannot invalidate previously integrated observations.
            finally:
                if child and child.returncode is None:
                    child.kill()
                    await child.wait()
            await asyncio.sleep(6*3600)

    @app.on_event('startup')
    async def start_checks():
        nonlocal worker
        worker = asyncio.create_task(source_checks())

    @app.on_event('shutdown')
    async def stop_checks():
        if worker:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

    @app.middleware('http')
    async def reload_operational_data(request, call_next):
        # Serialize reload with consumers so a response cannot mix old/new frames.
        async with lock:
            await asyncio.to_thread(refresh.refresh)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-ANI-Data-Version'] = refresh.generation
            return response

    @app.get('/data-snapshot')
    def snapshot():
        return {'generation':refresh.generation,'meta':namespace['meta'](), 'historical':namespace['historical_all'](), 'projection':namespace['long_term_projection_meta'](), 'environmental':namespace['environmental_decision_support'](), 'freshness':refresh.freshness()}

    @app.get('/data-freshness')
    def freshness():
        return refresh.freshness()

    return refresh
