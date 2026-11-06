import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from backend.data_refresh import OperationalRefresh, validate_frame, period
from tools.automatic_refresh import valid_context


class RefreshTests(unittest.TestCase):
    def test_supported_period_schemas(self):
        for key in ('Quarter','Quarter_Number'):
            frame=pd.DataFrame({'Province':['Abra','Abra'],'Year':[2026,2026],key:[1,2]})
            validate_frame(frame,frame,'weather')
            self.assertEqual(period(frame),'Q2 2026')

    def test_regressions_duplicates_and_invalid_data_rejected(self):
        old=pd.DataFrame({'Province':['Abra'],'Year':[2026],'Quarter_Number':[2],'Yield_mt_per_ha':[4.2]})
        for new in [old.assign(Quarter_Number=1),pd.concat([old,old]),old.assign(Yield_mt_per_ha=-1),old.iloc[0:0]]:
            with self.assertRaises(ValueError):validate_frame(new,old,'history')

    def test_incomplete_or_old_bulletins_rejected(self):
        old={'forecastPeriod':'21 - 31 October 2026','regions':[{'regionLabel':'Region I'}]}
        for new in [{**old,'regions':[]},{**old,'forecastPeriod':'1 - 10 October 2026'},{**old,'forecastPeriod':None}]:
            with self.assertRaises(ValueError):valid_context('PAGASA agri-weather',new,old)

    def test_atomic_reload_and_last_good_retention(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            history=pd.DataFrame({'Province':['Abra'],'Region_Context':['CAR'],'Ecosystem':['Irrigated'],'Year':[2026],'Quarter_Number':[2]})
            quarter=pd.DataFrame({'Province':['Abra'],'Year':[2026],'Quarter':[2]})
            keys={'history_df':'HISTORY_PATH','weather_df':'WEATHER_PATH','satellite_df':'SATELLITE_PATH','market_df':'MARKET_PATH','enso_history_df':'ENSO_HISTORY_PATH','agricultural_source_df':'AGRICULTURAL_SOURCE_PATH'}
            ns={'DATA_DIR':root,'ROOT':root,'AniFeatureBuilder':lambda h,w:('builder',len(h)), 'LongTermProjector':lambda h,w:('projector',len(h))}
            for name,key in keys.items():
                ns[name]=history.copy() if name in ('history_df','agricultural_source_df') else quarter.copy()
                ns[key]=root/(name+'.csv');ns[name].to_csv(ns[key],index=False)
            for name,key in {'pagasa_agri_weather':'PAGASA_AGRI_WEATHER_PATH','pagasa_climate_risk':'PAGASA_CLIMATE_RISK_PATH','psa_near_term_outlook':'PSA_NEAR_TERM_OUTLOOK_PATH'}.items():
                ns[name]=None;ns[key]=root/(name+'.json')
            refresh=OperationalRefresh(ns)
            first=refresh.generation
            history.assign(Quarter_Number=3).to_csv(ns['HISTORY_PATH'],index=False)
            refresh.refresh(force=True)
            self.assertIsNone(refresh.error);self.assertNotEqual(refresh.generation,first)
            self.assertEqual(ns['history_df'].Quarter_Number.iloc[0],3)
            good=refresh.generation
            ns['HISTORY_PATH'].write_text('bad,data\n1,2\n')
            refresh.refresh(force=True)
            self.assertIsNotNone(refresh.error);self.assertEqual(refresh.generation,good)
            self.assertEqual(ns['history_df'].Quarter_Number.iloc[0],3)


if __name__=='__main__':unittest.main()
