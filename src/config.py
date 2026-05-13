from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_OFFICIAL_DIR = RAW_DIR / "official"
RAW_OSM_DIR = RAW_DIR / "osm"
PROCESSED_DIR = DATA_DIR / "processed"

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
TABLES_DIR = OUTPUTS_DIR / "tables"
MAPS_DIR = OUTPUTS_DIR / "maps"
REPORT_DIR = PROJECT_ROOT / "report"

PBF_PATH = RAW_OSM_DIR / "denmark-latest.osm.pbf"

CRS_WGS84 = "EPSG:4326"
CRS_METRIC = "EPSG:25832"
CRS_WEB_MERCATOR = "EPSG:3857"

GRID_SIZE_M = 500
WALKING_SPEED_KMH = 5.0
ACCESS_THRESHOLD_MINUTES = 15.0
SNAP_WARNING_DISTANCE_M = 100.0

CKAN_API_BASE = "https://admin.opendata.dk/api/3/action"
CKAN_ORGANIZATION = "city-of-copenhagen"

OFFICIAL_DATASETS = {
    "libraries": {
        "dataset_name": "Biblioteker",
        "package_ids": ["biblioteker"],
        "search_query": "title:Biblioteker organization:city-of-copenhagen",
        "amenity_type": "library",
    },
    "playgrounds": {
        "dataset_name": "Legepladser",
        "package_ids": ["legepladser1"],
        "search_query": "title:Legepladser organization:city-of-copenhagen tags:legepladser",
        "amenity_type": "playground",
    },
    "sports_facilities": {
        "dataset_name": "Idraetsanlaeg",
        "package_ids": ["idraetsanlaeg"],
        "search_query": "title:Idraetsanlaeg organization:city-of-copenhagen",
        "amenity_type": "sports_facility",
    },
    "bydele": {
        "dataset_name": "Bydele",
        "package_ids": ["bydele"],
        "search_query": "title:Bydele organization:city-of-copenhagen",
        "amenity_type": None,
    },
}

AMENITY_LAYER_KEYS = ["libraries", "playgrounds", "sports_facilities"]

AMENITY_TYPE_BY_LAYER = {
    "libraries": "library",
    "playgrounds": "playground",
    "sports_facilities": "sports_facility",
}

LAYER_BY_AMENITY_TYPE = {v: k for k, v in AMENITY_TYPE_BY_LAYER.items()}

MATCH_THRESHOLDS_M = {
    "library": 100.0,
    "playground": 100.0,
    "sports_facility": 150.0,
}

OFFICIAL_CLEAN_FILES = {
    "libraries": PROCESSED_DIR / "official_libraries.gpkg",
    "playgrounds": PROCESSED_DIR / "official_playgrounds.gpkg",
    "sports_facilities": PROCESSED_DIR / "official_sports_facilities.gpkg",
}

OSM_RAW_FILES = {
    "libraries": PROCESSED_DIR / "osm_libraries.gpkg",
    "playgrounds": PROCESSED_DIR / "osm_playgrounds.gpkg",
    "sports_facilities": PROCESSED_DIR / "osm_sports_facilities.gpkg",
}

OSM_CLEAN_FILES = {
    "libraries": PROCESSED_DIR / "osm_libraries_clean.gpkg",
    "playgrounds": PROCESSED_DIR / "osm_playgrounds_clean.gpkg",
    "sports_facilities": PROCESSED_DIR / "osm_sports_facilities_clean.gpkg",
}

BYDELE_FILE = PROCESSED_DIR / "bydele.gpkg"
BOUNDARY_FILE = PROCESSED_DIR / "copenhagen_boundary.gpkg"

OSM_WALKING_EDGES_FILE = PROCESSED_DIR / "osm_walking_edges.gpkg"
OSM_WALKING_NODES_FILE = PROCESSED_DIR / "osm_walking_nodes.gpkg"
OSM_WALKING_EDGES_CLEAN_FILE = PROCESSED_DIR / "osm_walking_edges_clean.gpkg"
OSM_WALKING_NODES_CLEAN_FILE = PROCESSED_DIR / "osm_walking_nodes_clean.gpkg"
OSM_WALKING_GRAPH_FILE = PROCESSED_DIR / "osm_walking_graph.graphml"

ORIGINS_GRID_FILE = PROCESSED_DIR / "origins_grid_500m.gpkg"
ORIGINS_POINTS_FILE = PROCESSED_DIR / "origins_points_500m.gpkg"
ORIGINS_POINTS_SNAPPED_FILE = PROCESSED_DIR / "origins_points_500m_snapped.gpkg"

ACCESSIBILITY_TABLE = TABLES_DIR / "origin_accessibility_comparison.csv"
ACCESSIBILITY_GPKG = PROCESSED_DIR / "origin_accessibility_comparison.gpkg"
CLASSIFIED_ACCESSIBILITY_TABLE = TABLES_DIR / "origin_accessibility_classified.csv"
CLASSIFIED_ACCESSIBILITY_GPKG = PROCESSED_DIR / "origin_accessibility_classified.gpkg"
COMPOSITE_DISAGREEMENT_TABLE = TABLES_DIR / "composite_disagreement_scores.csv"
COMPOSITE_DISAGREEMENT_GPKG = PROCESSED_DIR / "composite_disagreement.gpkg"


def ensure_directories() -> None:
    for path in [
        RAW_OFFICIAL_DIR,
        RAW_OSM_DIR,
        PROCESSED_DIR,
        FIGURES_DIR,
        TABLES_DIR,
        MAPS_DIR,
        REPORT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
