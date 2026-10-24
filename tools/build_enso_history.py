from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "enso_history.csv"
URL = "https://cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/"
SEASONS = ["DJF","JFM","FMA","MAM","AMJ","MJJ","JJA","JAS","ASO","SON","OND","NDJ"]
QUARTER_SEASON = {1:"JFM", 2:"AMJ", 3:"JAS", 4:"OND"}

def main():
    tables = pd.read_html(URL)
    table = tables[8].copy()
    table.columns = ["Year", *SEASONS]

    seasonal = []
    for _, row in table.iterrows():
        try:
            year = int(row["Year"])
        except (TypeError, ValueError):
            continue
        for season_index, season in enumerate(SEASONS):
            value = row[season]
            if pd.isna(value):
                continue
            seasonal.append({
                "Year": year,
                "SeasonIndex": season_index,
                "Season": season,
                "RONI": float(value),
            })

    all_seasons = pd.DataFrame(seasonal).sort_values(["Year", "SeasonIndex"]).reset_index(drop=True)
    signs = all_seasons["RONI"].apply(lambda v: 1 if v >= 0.5 else (-1 if v <= -0.5 else 0)).tolist()
    episode = ["Neutral"] * len(signs)

    start = 0
    while start < len(signs):
        sign = signs[start]
        end = start + 1
        while end < len(signs) and signs[end] == sign:
            end += 1
        if sign != 0 and end - start >= 5:
            label = "El Nino" if sign > 0 else "La Nina"
            for idx in range(start, end):
                episode[idx] = label
        start = end

    all_seasons["Episode"] = episode
    quarter_rows = []
    for quarter, season in QUARTER_SEASON.items():
        subset = all_seasons[all_seasons["Season"] == season].copy()
        subset["Quarter"] = quarter
        quarter_rows.append(subset)

    out = pd.concat(quarter_rows, ignore_index=True).sort_values(["Year", "Quarter"])
    out["Signal"] = out["RONI"].apply(
        lambda v: "Warm" if v >= 0.5 else ("Cold" if v <= -0.5 else "Neutral")
    )
    out["Source"] = "NOAA CPC Relative Oceanic Nino Index (RONI) ERSSTv6"
    out["Source_URL"] = URL
    out = out[["Year","Quarter","Season","RONI","Signal","Episode","Source","Source_URL"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"Saved {len(out):,} quarterly ENSO context records to {OUT}")

if __name__ == "__main__":
    main()
