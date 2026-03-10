import os
import json
import math
from pyproj import Transformer

# Import your sub-modules
from vectors_pipeline import get_bbox_from_map, get_bbox_from_text, fetch_bbox_safe
from ortho_elevation import download_maptiler_satellite, sentinel_backup, MAPTILER_API_KEY, GEE_PROJECT_ID
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
    
    # Get current metric dimensions
    x_min_raw, y_min_raw = transformer.transform(w, s)
    x_max_raw, y_max_raw = transformer.transform(e, n)
    
    # Calculate the 'Square Side' to satisfy Geovia's 1-meter tolerance
    side = max(x_max_raw - x_min_raw, y_max_raw - y_min_raw)
    cx, cy = (x_min_raw + x_max_raw) / 2, (y_min_raw + y_max_raw) / 2
    
    x_min, x_max = cx - (side / 2), cx + (side / 2)
    y_min, y_max = cy - (side / 2), cy + (side / 2)

    # Convert back to Degrees for the scrapers
    inv_transformer = Transformer.from_crs(target_epsg, "EPSG:4326", always_xy=True)
    w_new, s_new = inv_transformer.transform(x_min, y_min)
    e_new, n_new = inv_transformer.transform(x_max, y_max)

    metadata = {
        "project_name": folder,
        "epsg": target_epsg,
        "bbox": [n_new, s_new, e_new, w_new],
        "geovia_coords": {
            "xmin": round(x_min, 3), "xmax": round(x_max, 3),
            "ymin": round(y_min, 3), "ymax": round(y_max, 3),
            "side_meters": round(side, 3)
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

    # STEP 1: Area Selection
    mode = input("Select mode: [1] Search Text [2] Map Visual: ")
    bbox_raw, place_name = get_bbox_from_map() if mode == '2' else get_bbox_from_text(input("Enter location: "))
    
    folder = place_name.replace(" ", "_").replace(",", "").split("_")[0] 
    meta = init_metadata(folder, bbox_raw, place_name)
    bbox = meta['bbox']
    target_epsg = meta['epsg']

    # STEP 2: Vector Extraction
    print("\n[STEP 2] Extracting Vectors...")
    for tag in ['building', 'highway', 'natural', 'landuse', 'amenity']:
        if not os.path.exists(os.path.join(folder, f"{tag}.geojson")):
            try:
                data = fetch_bbox_safe(bbox, {tag: True})
                if data is not None and not data.empty:
                    for col in data.columns:
                        if col != 'geometry': data[col] = data[col].astype(str)
                    data.to_file(os.path.join(folder, f"{tag}.geojson"), driver="GeoJSON")
            except: continue
        else:
            print(f"  -> {tag}.geojson already exists. Skipping extraction.")

    # STEP 3: Imagery (API Save Feature)
    print("\n[STEP 3] Fetching High-Res Imagery...")
    ortho_path = os.path.join(folder, "ortho_final.tif")
    if not os.path.exists(ortho_path):
        try:
            download_maptiler_satellite(bbox, 18, ortho_path, MAPTILER_API_KEY)
        except:
            print("[!] MapTiler failed. Falling back to Sentinel-2...")
            sentinel_backup(folder, ortho_path) # Assumes your script is refactored
    else:
        print(f"  -> {ortho_path} already exists. Skipping API call.")

    # STEP 4: Baseline DEM
    print("\n[STEP 4] Generating Baseline DEM...")
    dem_pro_path = os.path.join(folder, "terrain_elevation_pro.tif")
    if not os.path.exists(dem_pro_path):
        terrain_elevation.main(folder=folder)
    else:
        print(f"  -> {dem_pro_path} already exists. Skipping generation.")

    # STEP 5: GeoAI Fusion
    print("\n[STEP 5] Running GeoAI Terrain Fusion...")
    final_dem = os.path.join(folder, "terrain_geoai_final.tif")
    if not os.path.exists(final_dem):
        generate_geoai_dem(folder)
    else:
        print(f"  -> {final_dem} already exists. Skipping AI processing.")

    # STEP 6: Reprojection & 3D Extrusion
    print("\n[STEP 6] Finalizing GDA-Ready Output...")
    reproject_vectors(folder, target_epsg)
    for r in ["ortho_final.tif", "terrain_geoai_final.tif"]:
        r_path = os.path.join(folder, r)
        if os.path.exists(r_path): reproject_raster(r_path, target_epsg)
    
    extrude_with_ai_terrain(folder)

    print(f"\n[✓] PIPELINE COMPLETE: ./{folder}/ is ready!")
    print(f"Copy these to Geovia: X:[{meta['geovia_coords']['xmin']} to {meta['geovia_coords']['xmax']}]")

if __name__ == "__main__":
    main()