# Geospatial reference data

## Philippine provincial boundaries

`ph_provincial_boundaries_denr_simplified.geojson` is the frozen provincial-boundary reference used to aggregate satellite vegetation observations to ANI's province-level modeling unit.

- Source: Department of Environment and Natural Resources (DENR), Forest Management Bureau, Provincial Boundary FeatureServer.
- Service: `https://fmbfsd.denr.gov.ph/server/rest/services/Hosted/Provincial_Boundary/FeatureServer/0/query`
- Retrieved: 2026-10-16.
- Output coordinate system: EPSG:4326.
- The extraction request uses `maxAllowableOffset=0.001` and `geometryPrecision=5` to keep the repository copy compact while retaining province-scale geometry.

The reference contains current administrative boundaries. ANI does not assign the current Maguindanao del Sur polygon to pre-2024 agricultural records representing the former undivided Maguindanao province; those historical satellite values are withheld during model evaluation rather than spatially mismatched.

Related source references:
- NASA MODIS Vegetation Index products: `https://modis.gsfc.nasa.gov/data/dataprod/mod13.php`
- ESA Climate Change Initiative Land Cover: `https://planetarycomputer.microsoft.com/dataset/group/esa-cci-lc`
