import os
import json
import math
import rasterio
import geopandas as gpd  # Fix for Pylance error
import pandas as pd
from pyproj import Transformer
import datetime
import uuid
# Import your sub-modules
from vectors_pipeline import get_bbox_from_map, get_bbox_from_text, fetch_bbox_safe, explore_available_tags
from ortho_elevation import download_maptiler_satellite, MAPTILER_API_KEY
import terrain_elevation
from geoai_terrain import generate_geoai_dem 
from reproject_coord import reproject_raster, reproject_vectors
from geoai_height import extrude_with_ai_terrain

def get_utm_epsg(lat, lon):
    zone = int((lon + 180) / 6) + 1
    epsg_base = 32600 if lat >= 0 else 32700
    return f"EPSG:{epsg_base + zone}"

def init_metadata(folder, bbox, place_name):
    """Calculates a PERFECT SQUARE for 3DExperience GDA compliance."""
    n, s, e, w = bbox
    target_epsg = get_utm_epsg((n + s) / 2, (e + w) / 2)
    transformer = Transformer.from_crs("EPSG:4326", target_epsg, always_xy=True)
    
    x_min_raw, y_min_raw = transformer.transform(w, s)
    x_max_raw, y_max_raw = transformer.transform(e, n)
    
    side = max(x_max_raw - x_min_raw, y_max_raw - y_min_raw)
    cx, cy = (x_min_raw + x_max_raw) / 2, (y_min_raw + y_max_raw) / 2
    
    x_min, x_max = cx - (side / 2), cx + (side / 2)
    y_min, y_max = cy - (side / 2), cy + (side / 2)

    inv_transformer = Transformer.from_crs(target_epsg, "EPSG:4326", always_xy=True)
    w_new, s_new = inv_transformer.transform(x_min, y_min)
    e_new, n_new = inv_transformer.transform(x_max, y_max)

    metadata = {
        "project_name": folder,
        "epsg": target_epsg,
        "bbox": [n_new, s_new, e_new, w_new],
        "geovia_coords": {
            "xmin": round(x_min, 3), "xmax": round(x_max, 3),
            "ymin": round(y_min, 3), "ymax": round(y_max, 3)
        }
    }
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=4)
    return metadata

def main():
    print("==============================================")
    print(" GEOAI DIGITAL TWIN: MASTER ORCHESTRATOR")
    print("==============================================\n")

    # --- STEP 0: PROJECT STATE MANAGER ---
    print("Project Configuration:")
    print("  [1] Start New City Selection")
    print("  [2] Work on Existing Project Folder")
    startup_mode = input("Choice (1/2): ").strip()

    if startup_mode == '2':
        folder = input("Enter existing project folder path: ").strip().replace('"', '')
        if not os.path.exists(os.path.join(folder, "metadata.json")):
            print("[X] Error: No metadata.json found in that folder.")
            return
        with open(os.path.join(folder, "metadata.json"), "r") as f:
            meta = json.load(f)
        bbox = meta['bbox']
        target_epsg = meta['epsg']
        print(f"[✓] Resuming project: {folder}")
    else:
        # STEP 1: Area Selection
        mode = input("\nSelect mode: [1] Search Text [2] Map Visual: ")
        bbox_raw, place_name = get_bbox_from_map() if mode == '2' else get_bbox_from_text(input("Enter location: "))
        
        if place_name is None:
            print("[X] Error: No location selected. Exiting.")
            return

        # Professional Naming: City_YYYYMMDD_ShortID
        city_clean = place_name.split(',')[0].replace(" ", "_")
        timestamp = datetime.datetime.now().strftime("%Y%m%d")
        project_id = str(uuid.uuid4())[:4]
        
        folder = f"DT_{city_clean}_{timestamp}_{project_id}"
        print(f"[✓] Project Workspace Created: {folder}")
        
        meta = init_metadata(folder, bbox_raw, place_name)

    # --- REMAINING STEPS WITH EXISTENCE CHECKS ---

    # --- STEP 2: Intelligent Vector Extraction ---
    print("\n[STEP 2] Extracting Vectors...")
    # First, scout what's actually there so we don't guess
    available = explore_available_tags(bbox)
    
    for tag in ['building', 'highway', 'natural', 'landuse', 'amenity']:
        file_path = os.path.join(folder, f"{tag}.geojson")
        
        if os.path.exists(file_path):
            print(f"  -> {tag}.geojson already exists. Skipping.")
            continue

        if tag in available:
            print(f"  [?] Fetching {tag} data...")
            try:
                data = fetch_bbox_safe(bbox, {tag: True})
                if data is not None and not data.empty:
                    # Clean columns for GeoJSON compatibility
                    for col in data.columns:
                        if col != 'geometry': data[col] = data[col].astype(str)
                    data.to_file(file_path, driver="GeoJSON")
                    print(f"  [✓] Saved {tag}.geojson")
            except Exception as e:
                print(f"  [X] Failed to fetch {tag}: {e}")
        else:
            print(f"  [-] No {tag} data found in this area. Skipping.")

    # STEP 3 & 4: Imagery and Baseline DEM
    ortho_path = os.path.join(folder, "ortho_final.tif")
    if not os.path.exists(ortho_path):
        download_maptiler_satellite(bbox, 18, ortho_path, MAPTILER_API_KEY)
    
    dem_pro_path = os.path.join(folder, "terrain_elevation_pro.tif")
    if not os.path.exists(dem_pro_path):
        terrain_elevation.main(folder=folder)

    # STEP 5: GeoAI Fusion
    final_dem = os.path.join(folder, "terrain_geoai_final.tif")
    if not os.path.exists(final_dem):
        generate_geoai_dem(folder)

    # --- STEP 6: Universal Alignment & Extrusion ---
    print("\n[STEP 6] Finalizing GDA-Ready Output...")
    reproject_vectors(folder, target_epsg)
    
    abs_path = os.path.abspath(folder)
    dem_path = os.path.join(abs_path, "terrain_geoai_final_utm.tif")
    
    if os.path.exists(dem_path):
        from geoai_height import get_elevation_at_point # Import correctly here
        
        with rasterio.open(dem_path) as dem:
            # Align non-building vectors (Roads, etc.)
            other_vectors = [f for f in os.listdir(abs_path) 
                            if f.endswith("_utm.geojson") and "building" not in f.lower()]
            
            for v_file in other_vectors:
                v_path = os.path.join(abs_path, v_file)
                gdf = gpd.read_file(v_path)
                # Sample centroid elevation for the base reference
                gdf['base_elev'] = gdf.geometry.centroid.apply(
                    lambda p: float(get_elevation_at_point(dem, p.x, p.y))
                )
                gdf.to_file(v_path, driver='GeoJSON')
                print(f"  [✓] Aligned Elevation: {v_file}")

    extrude_with_ai_terrain(folder)
    print(f"\n[✓] PIPELINE COMPLETE: ./{folder}/ is ready!")

if __name__ == "__main__":
    main()