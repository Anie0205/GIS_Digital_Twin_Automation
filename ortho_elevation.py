import os
import json
import math
import requests
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image
from io import BytesIO
import numpy as np
import time

def load_metadata():
    print("\n" + "="*40)
    print(" GeoAI Phase 2: Orthomosaic Generator")
    print("="*40)
    project_dir = input("\nEnter the project folder name: ").strip().replace('"', '').replace("'", "")

    if not os.path.isdir(project_dir):
        print(f"[X] Error: Directory '{project_dir}' not found.")
        return None, None

    metadata_path = os.path.join(project_dir, "metadata.json")
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
        return metadata, project_dir

def deg2tile(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return xtile, ytile

def tile2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg

def create_ortho():
    metadata, folder = load_metadata()
    if not metadata: return

    bbox = metadata['bbox'] # [north, south, east, west]
    target_crs = metadata['epsg']
    zoom = 18 

    # 1. Calculate and Download Tiles
    x_start, y_start = deg2tile(bbox[0], bbox[3], zoom)
    x_end, y_end = deg2tile(bbox[1], bbox[2], zoom)
    
    num_x, num_y = x_end - x_start + 1, y_end - y_start + 1
    width, height = num_x * 256, num_y * 256
    
    print(f"\n[?] Stitching {num_x * num_y} tiles for {metadata['location']}...")
    stitched = Image.new('RGB', (width, height))

    success_count = 0
    for x in range(x_start, x_end + 1):
        for y in range(y_start, y_end + 1):
            url = f"https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={zoom}"
            try:
                r = requests.get(url, timeout=15)
                if r.status_code == 200:
                    img = Image.open(BytesIO(r.content)).convert('RGB')
                    stitched.paste(img, ((x - x_start) * 256, (y - y_start) * 256))
                    success_count += 1
            except Exception as e:
                print(f"    [!] Tile {x},{y} failed: {e}")

    # DEBUG CHECK: Ensure we actually have an image
    if success_count == 0:
        print("[X] Error: No tiles were downloaded. Check your internet connection.")
        return

    # 2. Save Temporary GeoTIFF
    temp_path = os.path.join(folder, "temp_wgs84.tif")
    # Ensure array is uint8 (standard for images)
    img_array = np.array(stitched).transpose(2, 0, 1).astype('uint8')
    
    lat_n, lon_w = tile2deg(x_start, y_start, zoom)
    lat_s, lon_e = tile2deg(x_end + 1, y_end + 1, zoom)
    transform = from_bounds(lon_w, lat_s, lon_e, lat_n, width, height)

    print(f"[?] Saving temporary file...")
    with rasterio.open(temp_path, 'w', driver='GTiff', height=height, width=width,
                       count=3, dtype='uint8', crs='EPSG:4326', transform=transform) as dst:
        dst.write(img_array)

    # 3. Force Close and Re-Open for Reprojection
    time.sleep(1) # Small pause to ensure file system has flushed the write
    
    final_path = os.path.join(folder, "ortho_metric.tif")
    print(f"[?] Reprojecting to {target_crs}...")

    try:
        with rasterio.open(temp_path) as src:
            transform, width, height = calculate_default_transform(src.crs, target_crs, src.width, src.height, *src.bounds)
            kwargs = src.meta.copy()
            kwargs.update({'crs': target_crs, 'transform': transform, 'width': width, 'height': height})

            with rasterio.open(final_path, 'w', **kwargs) as dst:
                for i in range(1, src.count + 1):
                    reproject(source=rasterio.band(src, i), destination=rasterio.band(dst, i),
                              src_transform=src.transform, src_crs=src.crs,
                              dst_transform=transform, dst_crs=target_crs, resampling=Resampling.nearest)
        
        # Cleanup
        if os.path.exists(temp_path): os.remove(temp_path)
        print(f"\n[✓] Success! Orthomosaic saved: {final_path}")

    except Exception as e:
        print(f"\n[X] Reprojection Error: {e}")
        print("    Ensure your project folder contains 'metadata.json' with the correct EPSG code.")

if __name__ == "__main__":
    create_ortho()