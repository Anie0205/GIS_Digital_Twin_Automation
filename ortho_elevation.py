import ee
import geemap
import os
import sys
import json
import math
import requests
import numpy as np
import warnings
from PIL import Image
import rasterio
from rasterio.transform import from_bounds
from dotenv import load_dotenv 

warnings.filterwarnings("ignore")
Image.MAX_IMAGE_PIXELS = None
load_dotenv() 

GEE_PROJECT_ID = 'my-digital-twin-city'
MAPTILER_API_KEY = os.environ.get("MAPTILER_API_KEY")

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def num2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)

def download_maptiler_satellite(bbox, zoom, output_path, api_key):
    if not api_key: raise ValueError("MAPTILER_API_KEY environment variable is not set.")
    north, south, east, west = bbox[0], bbox[1], bbox[2], bbox[3]
    x_min, y_max = deg2num(south, west, zoom)
    x_max, y_min = deg2num(north, east, zoom)
    
    print(f"\n[?] Fetching high-res tiles via MapTiler API at Zoom {zoom}...")
    tile_size = 512 
    canvas_width = (x_max - x_min + 1) * tile_size
    canvas_height = (y_max - y_min + 1) * tile_size
    stitched_image = Image.new('RGB', (canvas_width, canvas_height))

    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            url = f"https://api.maptiler.com/tiles/satellite-v2/{zoom}/{x}/{y}.jpg?key={api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                from io import BytesIO
                img = Image.open(BytesIO(response.content))
                if img.size[0] != tile_size: img = img.resize((tile_size, tile_size))
                paste_x, paste_y = (x - x_min) * tile_size, (y - y_min) * tile_size
                stitched_image.paste(img, (paste_x, paste_y))
            else:
                raise Exception(f"API rejected tile {x},{y}. Status: {response.status_code}")

    top_lat, left_lon = num2deg(x_min, y_min, zoom)
    bottom_lat, right_lon = num2deg(x_max + 1, y_max + 1, zoom)
    transform = from_bounds(left_lon, bottom_lat, right_lon, top_lat, canvas_width, canvas_height)
    img_array = np.array(stitched_image)
    
    print(f"[?] Saving georeferenced GeoTIFF to {output_path}...")
    with rasterio.open(
        output_path, 'w', driver='GTiff', height=canvas_height, width=canvas_width,
        count=3, dtype=img_array.dtype, crs='EPSG:4326', transform=transform
    ) as dst:
        dst.write(img_array[:, :, 0], 1) 
        dst.write(img_array[:, :, 1], 2) 
        dst.write(img_array[:, :, 2], 3) 

def sentinel_backup(roi, final_path, crs):
    print("\n[?] Generating Sentinel-2 Baseline (10m, unlimited)...")
    s2_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(roi)
        .filterDate('2025-01-01', '2026-12-31') 
        .median())
    rgb = s2_collection.visualize(bands=['B4', 'B3', 'B2'], min=0, max=3000)
    geemap.ee_export_image(rgb, filename=final_path, scale=10, region=roi, crs=crs, file_per_band=False)
    print(f"[OK] Sentinel-2 backup ready!")

def generate_ortho():
    print("\n==================================================")
    print(" GeoAI Phase: Interactive Ortho Engine")
    print("==================================================")
    
    # --- WEB HOOK ---
    if len(sys.argv) > 2:
        project_dir = sys.argv[1]
        choice = sys.argv[2]
        print(f"\n[!] Auto-loaded project folder: {project_dir}")
        print(f"[!] Web UI Engine Choice Selected: Engine {choice}")
    elif len(sys.argv) > 1:
        project_dir = sys.argv[1]
        print(f"\n[!] Auto-loaded project folder: {project_dir}")
        print("\nSelect Image Engine:")
        print("  1) MapTiler (High-Res 0.6m, requires API key)")
        print("  2) Sentinel-2 (Standard 10m, GEE native)")
        print("  3) Auto (Try MapTiler, auto-fallback to Sentinel-2)")
        choice = input("\nEnter choice (1/2/3) [3]: ").strip()
        if choice not in ['1', '2', '3']: choice = '3'
    # --- TERMINAL MODE ---
    else:
        project_dir = input("\nEnter project folder: ").strip()
        print("\nSelect Image Engine:")
        print("  1) MapTiler (High-Res 0.6m, requires API key)")
        print("  2) Sentinel-2 (Standard 10m, GEE native)")
        print("  3) Auto (Try MapTiler, auto-fallback to Sentinel-2)")
        choice = input("\nEnter choice (1/2/3) [3]: ").strip()
        if choice not in ['1', '2', '3']: choice = '3'

    abs_path = os.path.abspath(project_dir)
    final_path = os.path.join(abs_path, "ortho_final.tif")
    with open(os.path.join(abs_path, "metadata.json"), "r") as f: metadata = json.load(f)
    
    bbox = metadata['bbox']  
    region = [bbox[3], bbox[1], bbox[2], bbox[0]]  
    target_crs = metadata['epsg']

    if os.path.exists(final_path):
        if len(sys.argv) <= 2: # Only prompt in terminal mode
            print(f"\n[!] PRIORITY 0: {final_path} already exists.")
            if input("Do you want to overwrite it? (y/n) [n]: ").strip().lower() != 'y': return
        else:
            print(f"\n[!] PRIORITY 0: Overwriting existing data for new web run.")

    if choice in ['1', '3']:
        try:
            if not MAPTILER_API_KEY: raise Exception("MAPTILER_API_KEY environment variable not configured.")
            
            # --- NEW DYNAMIC ZOOM LOGIC ---
            side_length = metadata.get('bbox_metric_utm', {}).get('Side_Length_Meters', 1000)
            if side_length <= 1000:
                calc_zoom = 18 # Ultra-high res for small areas
            elif side_length <= 2500:
                calc_zoom = 17 # High res for medium areas
            else:
                calc_zoom = 16 # Standard res for large areas
                
            print(f"[!] Area size is ~{int(side_length)}m. Dynamically selected Zoom {calc_zoom}.")
            
            download_maptiler_satellite(bbox, zoom=calc_zoom, output_path=final_path, api_key=MAPTILER_API_KEY)
            # ------------------------------
            
            print(f"\n[OK] SUCCESS: Authorized High-Res Ortho saved!")
            return
        
        except Exception as e:
            print(f"\n[X] MapTiler Failed: {e}")
            if choice == '1':
                print("[!] Exiting. Run again and select Sentinel-2 or Auto to use the fallback.")
                return
            else: print("[?] Triggering Sentinel-2 fail-safe...")

    if choice in ['2', '3']:
        try:
            try: ee.Initialize(project=GEE_PROJECT_ID)
            except:
                ee.Authenticate()
                ee.Initialize(project=GEE_PROJECT_ID)
            roi = ee.Geometry.BBox(*region)
            sentinel_backup(roi, final_path, target_crs)
        except Exception as e:
            print(f"\n[X] CRITICAL FAILURE: GEE Sentinel-2 failed.\nError: {e}")

if __name__ == "__main__":
    generate_ortho()