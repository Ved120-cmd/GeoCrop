"""GeoCrop resource catalog: the single source of truth for what the project needs.

Every audit / download script reads this file. Edit here, not in the scripts.

Fields
------
id, name, group          identifiers
modules                  GeoCrop modules that depend on it
source                   official source URL(s)
access                   public_auto | gee_auth | earthdata_auth | account | manual_portal | reference_only
globs                    where local files are expected (relative to project root)
expect                   checks used by validate_datasets.py
weight                   importance 1 (nice-to-have) .. 5 (critical) – used for readiness
licence                  licence / terms note
size_hint                expected download size for the Maharashtra subset
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Maharashtra bounding box (EPSG:4326), padded slightly.
MH_BBOX = (72.5, 15.5, 81.0, 22.2)  # minx, miny, maxx, maxy
HIST_START, HIST_END = "2015-01-01", "2025-12-31"

MODULES = ["Monitor", "Predict", "Soil Intelligence", "Crop Advisor", "Plant Doctor", "Farm Simulator"]

SG_PROPS = ["clay", "sand", "silt", "bdod", "cfvo", "phh2o", "soc", "cec", "nitrogen", "ocd"]
SG_DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]

R = []


def add(**kw):
    kw.setdefault("globs", [])
    kw.setdefault("expect", {})
    kw.setdefault("weight", 3)
    kw.setdefault("licence", "")
    kw.setdefault("size_hint", "")
    kw.setdefault("notes", "")
    R.append(kw)


# ---------------- A. Satellite vegetation ----------------
add(id="A1", name="MODIS MOD13Q1.061 (NDVI/EVI 250m 16-day)", group="satellite", modules=["Monitor", "Predict"],
    source="https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1 | https://lpdaac.usgs.gov/products/mod13q1v061/",
    access="gee_auth", globs=["data/raw/modis/mod13q1/**/*.tif"],
    expect={"kind": "raster", "bands_any": ["NDVI", "EVI", "SummaryQA"], "temporal": True, "expected_n": 253},
    weight=5, licence="NASA EOSDIS open data, no restrictions", size_hint="~1-3 GB (MH, 2015-2025, NDVI+EVI+QA)",
    notes="Scale factor 0.0001; keep SummaryQA/DetailedQA. Existing datasets/MOD13Q1061.py is a GEE snippet only.")
add(id="A2", name="MODIS MOD11A2.061 (LST day/night 1km 8-day)", group="satellite", modules=["Monitor", "Predict"],
    source="https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD11A2",
    access="gee_auth", globs=["data/raw/modis/mod11a2/**/*.tif"],
    expect={"kind": "raster", "bands_any": ["LST_Day_1km", "LST_Night_1km", "QC_Day"], "temporal": True, "expected_n": 506},
    weight=4, licence="NASA EOSDIS open data", size_hint="~300-600 MB",
    notes="Scale 0.02 -> Kelvin; minus 273.15 -> Celsius. Keep QC_Day/QC_Night.")
add(id="A3", name="MODIS MOD16A2GF.061 (ET/PET 500m 8-day)", group="satellite", modules=["Monitor", "Predict"],
    source="https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD16A2GF",
    access="gee_auth", globs=["data/raw/modis/mod16a2gf/**/*.tif"],
    expect={"kind": "raster", "bands_any": ["ET", "PET", "ET_QC"], "temporal": True, "expected_n": 506},
    weight=3, licence="NASA EOSDIS open data", size_hint="~500 MB-1 GB")
add(id="A4", name="MODIS MCD12Q1.061 (annual land cover 500m)", group="satellite", modules=["Monitor", "Crop Advisor"],
    source="https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD12Q1",
    access="gee_auth", globs=["data/raw/modis/mcd12q1/**/*.tif"],
    expect={"kind": "raster", "bands_any": ["LC_Type1", "QC"], "temporal": True, "expected_n": 11},
    weight=2, licence="NASA EOSDIS open data", size_hint="~50 MB",
    notes="Broad IGBP land cover only, not crop type.")

# ---------------- B. Weather ----------------
add(id="B5", name="NASA POWER daily (0.5 x 0.625 deg MERRA-2 grid)", group="weather", modules=["Monitor", "Predict", "Farm Simulator"],
    source="https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
    access="public_auto", globs=["data/raw/weather/nasa_power/**/*.csv"],
    expect={"kind": "nasa_power", "vars": ["T2M", "T2M_MAX", "T2M_MIN", "RH2M", "PRECTOTCORR", "WS2M", "ALLSKY_SFC_SW_DWN"]},
    weight=5, licence="NASA open data; cite POWER Project", size_hint="~60 MB CSV")
add(id="B6", name="IMD gridded daily rainfall 0.25 deg", group="weather", modules=["Monitor", "Predict", "Farm Simulator"],
    source="https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html",
    access="public_auto", globs=["data/raw/weather/imd/rain_0p25/*.nc", "datasets/RF25*.nc"],
    expect={"kind": "netcdf_years", "var_any": ["RAINFALL", "rf", "rain"]},
    weight=5, licence="IMD, free download for research; cite Pai et al. 2014", size_hint="~25 MB/year, ~280 MB",
    notes="2025 file availability depends on IMD release.")
add(id="B7", name="IMD gridded daily Tmax/Tmin 1 deg", group="weather", modules=["Predict", "Farm Simulator"],
    source="https://imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html | Min_1_Bin.html",
    access="public_auto", globs=["data/raw/weather/imd/temp_1deg/*.GRD", "data/raw/weather/imd/temp_1deg/*.grd"],
    expect={"kind": "imd_temp_bin"}, weight=3, licence="IMD, free download for research", size_hint="~1.4 MB/year/var")
add(id="B8", name="CHIRPS v2.0 daily rainfall", group="weather", modules=["Monitor", "Predict"],
    source="https://www.chc.ucsb.edu/data/chirps | https://data.chc.ucsb.edu/products/CHIRPS-2.0/",
    access="public_auto", globs=["data/raw/weather/chirps/**/*.nc", "data/raw/weather/chirps/**/*.tif"],
    expect={"kind": "netcdf_years", "var_any": ["precip"]}, weight=2,
    licence="CC BY 4.0 (CHC)", size_hint="p25 global ~70-90 MB/year (cropped to MH after download)",
    notes="Server rate-limits (HTTP 429); also available in GEE as UCSB-CHG/CHIRPS/DAILY.")
add(id="B9", name="GPM IMERG precipitation", group="weather", modules=["Monitor", "Predict"],
    source="https://gpm.nasa.gov/data/imerg | GEE: NASA/GPM_L3/IMERG_V07",
    access="gee_auth", globs=["data/raw/weather/gpm/**/*.tif"], expect={"kind": "raster", "bands_any": ["precipitation"], "temporal": True, "expected_n": 4018}, weight=2,
    licence="NASA open data; Earthdata login required for direct download", size_hint="daily MH subset ~1 GB")

# ---------------- C. Soil moisture & water ----------------
add(id="C10", name="SMAP L4 SPL4SMGP v008 (9 km, 3-hourly)", group="soil_moisture", modules=["Monitor", "Predict"],
    source="https://nsidc.org/data/spl4smgp/versions/8 | GEE: NASA/SMAP/SPL4SMGP/008",
    access="gee_auth", globs=["data/raw/soil/smap/**/*.tif"],
    expect={"kind": "raster", "bands_any": ["sm_surface", "sm_rootzone"], "temporal": True, "expected_n": 3929}, weight=5,
    licence="NASA open data", size_hint="daily-aggregated MH subset ~1-2 GB",
    notes="Record starts 2015-03-31. Proxy for stress, not ground-truth crop stress. datasets/SMAP.js is a GEE snippet only.")
add(id="C11", name="India-WRIS (reservoirs, rivers, irrigation)", group="water", modules=["Monitor", "Crop Advisor", "Farm Simulator"],
    source="https://indiawris.gov.in/wris/", access="manual_portal", globs=["data/raw/water/india_wris/**/*"],
    expect={"kind": "any"}, weight=2, licence="India-WRIS terms; interactive portal / data request")
add(id="C12", name="CGWB groundwater (levels, aquifer maps) - Maharashtra", group="water", modules=["Monitor", "Crop Advisor"],
    source="https://cgwb.gov.in/ | https://indiawris.gov.in/wris/#/groundWater", access="manual_portal",
    globs=["data/raw/water/cgwb/**/*", "datasets/*Aquifer*.zip"],
    expect={"kind": "region_check", "must_contain": "maharashtra"}, weight=2, licence="GoI open data (NDSAP) where published",
    notes="Existing archive is for Madhya Pradesh, not Maharashtra.")
add(id="C13", name="Maharashtra WRD irrigation/reservoir data", group="water", modules=["Crop Advisor", "Farm Simulator"],
    source="https://wrd.maharashtra.gov.in/", access="manual_portal", globs=["data/raw/water/mh_wrd/**/*"],
    expect={"kind": "any"}, weight=1, licence="State government website terms")

# ---------------- D. Soil ----------------
add(id="D14", name="SoilGrids 2.0 (250m, 6 depths, mean + Q0.05/Q0.95/uncertainty)", group="soil",
    modules=["Soil Intelligence", "Crop Advisor", "Farm Simulator"],
    source="https://files.isric.org/soilgrids/latest/data/", access="public_auto",
    globs=["data/raw/soil/soilgrids/sg2/**/*.tif"],
    expect={"kind": "soilgrids", "props": SG_PROPS, "depths": SG_DEPTHS}, weight=5,
    licence="CC BY 4.0 (ISRIC)", size_hint="~3-6 MB per layer for MH; 60 mean layers ~300 MB")
add(id="D14b", name="SoilGrids250m 2017 water retention (AWCh1/2/3, WWP, AWCtS)", group="soil",
    modules=["Soil Intelligence", "Farm Simulator"],
    source="https://files.isric.org/soilgrids/former/2017-03-10/data/", access="public_auto",
    globs=["data/raw/soil/soilgrids/sg2017_water/**/*.tif"],
    expect={"kind": "raster_set", "min_files": 35}, weight=4, licence="ODbL / CC BY 4.0 (ISRIC 2017 release)",
    size_hint="~35 layers x ~5 MB",
    notes="AVAILABLE water capacity with FC at -10/-20/-31.6 kPa (AWCh1-3, = theta_FC - theta_WP), water content at wilting point (WWP), saturation (AWCtS); 7 standard depths. SoilGrids 2.0 has no WRC layers.")
add(id="D15", name="NBSS&LUP soil resource maps / Bhoomi Geoportal", group="soil", modules=["Soil Intelligence", "Crop Advisor"],
    source="https://nbsslup.icar.gov.in/ | https://bhoomigeoportal-nbsslup.in/", access="manual_portal",
    globs=["data/raw/soil/nbss_lup/**/*"], expect={"kind": "any"}, weight=4,
    licence="ICAR-NBSS&LUP; digital data supplied on request / priced publications",
    notes="Viewer layers are not a sanctioned bulk download. Request via Director, NBSS&LUP, Amravati Road, Nagpur 440033.")
add(id="D16", name="Soil Health Card lab data (pH, EC, OC, NPK, S, micronutrients)", group="soil",
    modules=["Soil Intelligence", "Crop Advisor"], source="https://soilhealth.dac.gov.in/", access="manual_portal",
    globs=["data/raw/soil/soil_health_card/**/*"], expect={"kind": "any"}, weight=4,
    licence="GoI portal; farmer-level records are personal data - use aggregated reports only")

# ---------------- E. Terrain & boundaries ----------------
add(id="E17", name="DEM (SRTM / Copernicus GLO-90)", group="terrain", modules=["Monitor", "Soil Intelligence"],
    source="https://earthexplorer.usgs.gov/ (SRTM, login) | https://registry.opendata.aws/copernicus-dem/ (GLO-90, open)",
    access="public_auto", globs=["data/raw/terrain/**/*.tif"], expect={"kind": "raster_set", "min_files": 40, "cover_mh": True},
    weight=3, licence="Copernicus DEM GLO-90: free, licence by ESA/Airbus (attribution)", size_hint="~70 tiles, ~300 MB")
add(id="E18a", name="Maharashtra state + district boundaries (current, 36 districts)", group="boundaries",
    modules=MODULES, source="https://www.geoboundaries.org/ (IND ADM1/ADM2, source lgdirectory.gov.in) | FAO GAUL 2015 | Survey of India",
    access="public_auto", globs=["data/interim/boundaries/*.geojson", "data/raw/boundaries/**/*.gpkg", "data/raw/boundaries/**/*.shp"],
    expect={"kind": "boundaries", "n_districts": 36}, weight=5, licence="geoBoundaries: ODbL 1.0",
    notes="Indian official boundary depiction: Survey of India is authoritative for display.")
add(id="E18b", name="Taluka / village boundaries", group="boundaries", modules=["Monitor", "Crop Advisor"],
    source="https://onlinemaps.surveyofindia.gov.in/ | https://bhuvan.nrsc.gov.in/ | MRSAC https://mrsac.gov.in/",
    access="manual_portal", globs=["data/raw/boundaries/taluka/**/*", "data/raw/boundaries/village/**/*"],
    expect={"kind": "any"}, weight=3, licence="SoI / MRSAC terms; no verified open download found")

# ---------------- F. Crop & agriculture ----------------
add(id="F19", name="DES district crop APY statistics (Maharashtra)", group="crop", modules=["Predict", "Crop Advisor"],
    source="https://data.desagri.gov.in/website/crops-report-district-level-web", access="manual_portal",
    globs=["datasets/apy_*.xls", "datasets/horizontal_crop_vertical_year_report.xls", "data/raw/crop/crop_statistics/**/*"],
    expect={"kind": "apy_html"}, weight=4, licence="GoI open data (NDSAP)",
    notes="Exported reports do not embed the crop/crop-group name; re-export with crop name in filename.")
add(id="F20", name="FAO GIEWS India country brief", group="crop", modules=["Crop Advisor"],
    source="https://www.fao.org/giews/countrybrief/country.jsp?code=IND", access="public_auto",
    globs=["datasets/IND.pdf", "data/raw/crop/crop_requirements/giews/**/*"], expect={"kind": "pdf"}, weight=1,
    licence="FAO copyright; non-commercial reuse permitted with attribution")
add(id="F21", name="ICAR / SAU (MPKV, PDKV, VNMKV, DBSKKV) package of practices", group="crop", modules=["Crop Advisor", "Plant Doctor"],
    source="https://mpkv.ac.in/ | https://www.pdkv.ac.in/ | https://www.vnmkv.ac.in/ | https://dbskkv.org/", access="manual_portal",
    globs=["data/raw/crop/crop_requirements/sau/**/*"], expect={"kind": "any"}, weight=4,
    licence="University publications; copyright retained - use as reference, cite")
add(id="F22", name="FAO crop water information (Kc, stages, root depth, Ky)", group="crop", modules=["Crop Advisor", "Farm Simulator"],
    source="https://www.fao.org/land-water/databases-and-software/crop-information/en/ | FAO-56 https://www.fao.org/4/x0490e/x0490e00.htm",
    access="reference_only", globs=["data/raw/crop/crop_requirements/fao/**/*"], expect={"kind": "any"}, weight=3,
    licence="FAO copyright; free to read; non-commercial reuse")
add(id="F23", name="Maharashtra crop calendar (structured)", group="crop", modules=["Predict", "Crop Advisor", "Farm Simulator"],
    source="SAU package of practices; FAO GIEWS crop calendar; IMD/ICAR agro-advisories", access="manual_portal",
    globs=["data/raw/crop/crop_calendar/**/*.csv"], expect={"kind": "crop_calendar"}, weight=5,
    licence="Derived from cited sources", notes="Must be curated from authoritative documents; never invented.")

# ---------------- G. Forecasts ----------------
add(id="G24", name="ECMWF sub-seasonal forecasts + reforecasts", group="forecast", modules=["Predict"],
    source="https://www.ecmwf.int/en/forecasts/datasets/set-vi | https://apps.ecmwf.int/datasets/data/s2s/ | https://cds.climate.copernicus.eu/",
    access="account", globs=["data/raw/forecasts/ecmwf/**/*"], expect={"kind": "any"}, weight=4,
    licence="S2S archive: free for research (ECMWF account, non-commercial); CDS: account + licence acceptance",
    notes="Reforecasts are required to train 16/32-day models without future-weather leakage.")
add(id="G25", name="IMD extended-range forecasts (archive)", group="forecast", modules=["Predict"],
    source="https://mausam.imd.gov.in/ | https://imdpune.gov.in/ (ERF)", access="manual_portal",
    globs=["data/raw/forecasts/imd/**/*"], expect={"kind": "any"}, weight=2, licence="IMD; archive by request")

# ---------------- H. High resolution ----------------
add(id="H26", name="Sentinel-2 SR harmonized", group="hires", modules=["Monitor", "Crop Advisor"],
    source="https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED", access="gee_auth",
    globs=["data/raw/sentinel/sentinel2/**/*"], expect={"kind": "raster", "bands_any": ["B4", "B8"]}, weight=3,
    licence="Copernicus free & open", notes="Process per farm/AOI in GEE; statewide 10 m archive is multi-TB.")
add(id="H27", name="Sentinel-1 GRD", group="hires", modules=["Monitor", "Crop Advisor"],
    source="https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD", access="gee_auth",
    globs=["data/raw/sentinel/sentinel1/**/*"], expect={"kind": "raster", "bands_any": ["VV", "VH"]}, weight=2,
    licence="Copernicus free & open")
add(id="H28", name="Landsat 8/9 C2 L2", group="hires", modules=["Monitor"],
    source="https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2", access="gee_auth",
    globs=["data/raw/sentinel/landsat/**/*"], expect={"kind": "raster", "bands_any": ["SR_B4", "SR_B5"]}, weight=1,
    licence="USGS public domain")

# ---------------- Plant health ----------------
add(id="P29", name="PlantVillage", group="plant_health", modules=["Plant Doctor"],
    source="https://github.com/spMohanty/PlantVillage-Dataset", access="public_auto",
    globs=["data/raw/plant_health/plantvillage/**/*"], expect={"kind": "image_folders", "min_classes": 30}, weight=4,
    licence="CC BY-SA 3.0 (images)", size_hint="raw/color ~0.9 GB",
    notes="Lab images on plain backgrounds - poor field generalisation alone.")
add(id="P30", name="PlantDoc", group="plant_health", modules=["Plant Doctor"],
    source="https://github.com/pratikkayal/PlantDoc-Dataset", access="public_auto",
    globs=["data/raw/plant_health/plantdoc/**/*"], expect={"kind": "image_folders", "min_classes": 20}, weight=4,
    licence="CC BY 4.0", size_hint="~1 GB")
add(id="P31", name="IP102 insect pest dataset", group="plant_health", modules=["Plant Doctor"],
    source="https://github.com/xpwu95/IP102", access="manual_portal",
    globs=["data/raw/plant_health/ip102/**/*"], expect={"kind": "image_folders", "min_classes": 100}, weight=3,
    licence="Research use; hosted on Google Drive / Baidu (links in README)", size_hint="~4-8 GB")
add(id="P32", name="ICAR-NCIPM IPM packages", group="plant_health", modules=["Plant Doctor", "Crop Advisor"],
    source="https://ncipm.icar.gov.in/ | https://ppqs.gov.in/ipm-packages", access="public_auto",
    globs=["data/raw/plant_health/ipm_references/ipm/**/*.pdf"], expect={"kind": "pdf_set"}, weight=3,
    licence="GoI publications; reference use with citation")
add(id="P33", name="CIB&RC registered pesticides / approved uses", group="plant_health", modules=["Plant Doctor"],
    source="https://ppqs.gov.in/divisions/cib-rc", access="public_auto",
    globs=["data/raw/plant_health/ipm_references/cibrc/**/*"], expect={"kind": "pdf_set"}, weight=3,
    licence="GoI publications", notes="Label dose / PHI must come from approved label claims; never invented.")
add(id="P34", name="Organic / natural farming references (NCOF, NMNF)", group="plant_health", modules=["Crop Advisor"],
    source="https://ncof.dacnet.nic.in/ | https://naturalfarming.dac.gov.in/", access="manual_portal",
    globs=["data/raw/plant_health/ipm_references/organic/**/*"], expect={"kind": "any"}, weight=1,
    licence="GoI publications")

# ---------------- Simulation ----------------
add(id="S35", name="FAO AquaCrop 7.3 Python source (official)", group="simulation", modules=["Farm Simulator"],
    source="https://github.com/un-fao/fao-AquaCrop/releases/tag/v7.3", access="public_auto",
    globs=["datasets/python.source.code.zip", "data/raw/simulation/aquacrop/python.source.code.zip"],
    expect={"kind": "sha256", "sha256": "1eebc1b29f639cfba4528f515f38556482852009342937d64606332867e37cfc"}, weight=5,
    licence="(c) FAO 2026, all rights reserved; non-commercial use authorised on request (copyright@fao.org)")
add(id="S35b", name="AquaCrop 7.3 GUI databases (crop .CRO / soil .SOL / climate defaults)", group="simulation",
    modules=["Farm Simulator"], source="https://github.com/un-fao/fao-AquaCrop/releases/download/v7.3/GUI_AC7.3.zip",
    access="public_auto", globs=["data/raw/simulation/aquacrop/GUI_AC7.3.zip"],
    expect={"kind": "sha256", "sha256": "9d6e8351c1c45686aeb64d0917c58795771ad877e5d4863c2e4c88c6853874ab"}, weight=4,
    licence="(c) FAO")
add(id="S35c", name="AquaCrop calibration/validation data for Maharashtra crops", group="simulation", modules=["Farm Simulator"],
    source="Field trials from SAUs / ICAR-AICRP; published calibration studies", access="manual_portal",
    globs=["data/raw/simulation/aquacrop/calibration/**/*"], expect={"kind": "any"}, weight=4, licence="Per source")

# Existing unidentified files - audited so they are not silently ignored (weight 0: not a requirement)
add(id="X1", name="Unidentified GEE exports datasets/out*.tif", group="legacy", modules=[],
    source="Earth Engine export (no region set)", access="reference_only", globs=["datasets/out*.tif"],
    expect={"kind": "raster", "temporal": False}, weight=0,
    notes="No band names/metadata; bounds 0-2 deg lon/lat (Gulf of Guinea), all-zero or nodata.")

CATALOG = {r["id"]: r for r in R}

# ---------------- Models ----------------
MODELS = [
    dict(id="M1a", name="Water stress 16-day (XGBoost/LightGBM)", module="Predict", dir="models/water_stress/lead16", code="geocrop/predict",
         labels="data/processed/predict_features.parquet",
         needs_data=["A1", "A2", "B5", "B6", "C10", "D14", "G24"], weight=5),
    dict(id="M1b", name="Water stress 32-day (XGBoost/LightGBM)", module="Predict", dir="models/water_stress/lead32", code="geocrop/predict",
         labels="data/processed/predict_features.parquet",
         needs_data=["A1", "A2", "B5", "B6", "C10", "D14", "G24"], weight=5),
    dict(id="M2", name="Crop suitability (rule-based baseline)", module="Crop Advisor", dir="models/crop_suitability", code="ml/crop_suitability",
         needs_data=["D14", "D14b", "F22", "F23", "B5"], weight=4),
    dict(id="M3", name="Plant disease classifier (EfficientNet/MobileNet/ResNet)", module="Plant Doctor", dir="models/plant_disease", code="ml/plant_disease",
         needs_data=["P29", "P30"], weight=4),
    dict(id="M4", name="Pest detection (IP102)", module="Plant Doctor", dir="models/pest_detection", code="ml/pest_detection",
         needs_data=["P31"], weight=3),
    dict(id="M5", name="Crop classification (S1/S2)", module="Monitor", dir="models/crop_classification", code="ml/crop_classification",
         needs_data=["H26", "H27"], weight=3),
    dict(id="M6", name="Explainability (SHAP, metadata, versioning)", module="Predict", dir="models/explainability", code="ml/common",
         needs_data=[], weight=2),
]

# Module -> (dataset ids, model ids) for readiness
MODULE_REQ = {
    "Monitor": (["E18a", "A1", "A2", "A3", "A4", "H26", "H27", "C10", "B5", "B6", "E17"], ["M5"]),
    "Predict": (["A1", "A2", "C10", "B5", "B6", "B7", "G24", "G25", "D14", "F19", "F23"], ["M1a", "M1b", "M6"]),
    "Soil Intelligence": (["D14", "D14b", "D15", "D16", "E17", "E18a"], []),
    "Crop Advisor": (["F19", "F21", "F22", "F23", "D14", "D14b", "D16", "P32", "P34", "B5"], ["M2"]),
    "Plant Doctor": (["P29", "P30", "P31", "P32", "P33"], ["M3", "M4"]),
    "Farm Simulator": (["S35", "S35b", "S35c", "D14", "D14b", "B5", "B6", "F22", "F23"], []),
}
