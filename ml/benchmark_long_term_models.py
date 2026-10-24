from __future__ import annotations

import json
from pathlib import Path
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
OUT_PATH = ROOT / "models" / "long_term_model_benchmark.json"

CLIMATE = ["Rainfall_Sum_mm","T2M_Mean_C","RH2M_Mean_pct","WS2M_Mean_m_s"]
CATEGORICAL = ["Province","Ecosystem","Quarter_Number"]
NUMERIC = CLIMATE + ["Year"]
TARGET = "Yield_mt_per_ha"

def metric(y_true,y_pred):
    return {"mae":float(mean_absolute_error(y_true,y_pred)),"rmse":float(mean_squared_error(y_true,y_pred)**0.5),"r2":float(r2_score(y_true,y_pred))}

def load_data():
    h=pd.read_csv(DATA_DIR/"palay_history.csv")
    w=pd.read_csv(DATA_DIR/"province_quarter_weather.csv")
    h["Ecosystem"]=h["Ecosystem"].astype(str).str.replace(" Palay","",regex=False)
    d=h.merge(w,left_on=["Province","Year","Quarter_Number"],right_on=["Province","Year","Quarter"],how="inner")
    d=d[(d["Year"]>=2001)&(d["Year"]<=2025)].dropna(subset=CATEGORICAL+NUMERIC+[TARGET]).copy()
    d=d.sort_values(["Province","Ecosystem","Quarter_Number","Year"])
    d["Seasonal_Naive"]=d.groupby(["Province","Ecosystem","Quarter_Number"])[TARGET].shift(1)
    return d

def prep(scale=False):
    return ColumnTransformer([
        ("cat",OneHotEncoder(handle_unknown="ignore",sparse_output=False),CATEGORICAL),
        ("num",StandardScaler() if scale else "passthrough",NUMERIC),
    ],sparse_threshold=0)

def candidates():
    return {
        "Ridge":Pipeline([("prep",prep(True)),("model",Ridge(alpha=10.0))]),
        "RandomForest":Pipeline([("prep",prep()),("model",RandomForestRegressor(n_estimators=500,max_depth=14,min_samples_leaf=3,max_features=0.7,random_state=42,n_jobs=-1))]),
        "GradientBoosting":Pipeline([("prep",prep()),("model",GradientBoostingRegressor(n_estimators=300,learning_rate=0.03,max_depth=3,min_samples_leaf=5,random_state=42,loss="huber"))]),
        "XGBoostClimate":Pipeline([("prep",prep()),("model",XGBRegressor(n_estimators=600,learning_rate=0.03,max_depth=4,min_child_weight=5,subsample=0.9,colsample_bytree=0.9,reg_lambda=5,objective="reg:squarederror",random_state=42,tree_method="hist",n_jobs=4))]),
    }

def main():
    d=load_data()
    train=d[d["Year"]<=2020].copy()
    test=d[(d["Year"]>=2021)&(d["Year"]<=2025)&d["Seasonal_Naive"].notna()].copy()
    result={"design":{"train_through":2020,"test_period":"2021-2025","features":CATEGORICAL+NUMERIC,"note":"Research benchmark only; production ANI models unchanged."},"rows":{"train":len(train),"test":len(test)},"models":{}}
    result["models"]["SeasonalNaive"]=metric(test[TARGET],test["Seasonal_Naive"])
    for name,model in candidates().items():
        model.fit(train[CATEGORICAL+NUMERIC],train[TARGET])
        result["models"][name]=metric(test[TARGET],model.predict(test[CATEGORICAL+NUMERIC]))
    result["ranking_by_mae"]=[{"model":k,**v} for k,v in sorted(result["models"].items(),key=lambda x:x[1]["mae"])]
    OUT_PATH.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
