import os
import json
import requests
import gzip
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from scipy.ndimage import gaussian_filter
from scipy.interpolate import griddata

def load_project():
    project_dir = input("\nEnter the project folder name: ").strip().replace('"', '').replace("'", "")
    if not os.path.isdir(project_dir):
        print(f"[X] Error: Folder '{project_dir}' not found.")
        return None, None
    with open(os.path.join(project_dir, "metadata.json"), "r") as f:
        return json.load(f), project_dir

def download_aws_skadi_tile(lat, lon, target_folder):
    """Downloads enterprise-grade 30m SRTM tiles from the AWS Open Data Registry."""
    lat_prefix = 'N' if lat >= 0 else 'S'
    lon_prefix = 'E' if lon >= 0 else 'W'
    
    # Format: N28 / N28E077
    lat_dir = f"{lat_prefix}{int(abs(lat)):02d}"
    tile_name = f"{lat_prefix}{int(abs(lat)):02d}{lon_prefix}{int(abs(lon)):03d}"
    
    # AWS Mapzen Skadi URL
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{lat_dir}/{tile_name}.hgt.gz"
    
    print(f"[?] Fetching High-Res AWS Skadi Tile: {tile_name}...")
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            hgt_path = os.path.join(target_folder, f"{tile_name}.hgt")
            # Decompress the .gz file directly to .hgt
            with open(hgt_path, 'wb') as f:
                f.write(gzip.decompress(r.content))
            print("  [✓] Download and extraction complete.")
            return hgt_path
        else:
            print(f"  [!] AWS returned Error {r.status_code}. Tile coordinates may be invalid.")
            return None
    except Exception as e:
        print(f"  [!] Connection Error: {e}")
        return None

def main():
    metadata, folder = load_project()
    if not metadata: return

    # 1. Automated Enterprise Download
    bbox = metadata['bbox'] # [north, south, east, west]
    
    # We use the south and west coordinates to identify the tile corner
    hgt_path = download_aws_skadi_tile(bbox[1], bbox[3], folder)
    
    if not hgt_path:
        print("[X] Could not acquire AWS elevation data.")
        return

    # 2. Process High-Res HGT (3601x3601)
    print(f"[?] Processing {os.path.basename(hgt_path)}...")
    with open(hgt_path, 'rb') as f:
        # Skadi tiles are 3601x3601 16-bit big-endian integers (30m resolution)
        raw_data = np.fromfile(f, np.dtype('>i2'), 3601*3601).reshape((3601, 3601))

    # 3. Precision Crop Math
    # Calculate the exact pixel bounds within the 1-degree tile
    top_lat = np.floor(bbox[1]) + 1.0 # E.g., if south is 28.5, top of tile is 29.0
    left_lon = np.floor(bbox[3])      # E.g., if west is 77.2, left of tile is 77.0
    
    row_start = int((top_lat - bbox[0]) * 3600)
    row_end = int((top_lat - bbox[1]) * 3600)
    col_start = int((bbox[3] - left_lon) * 3600)
    col_end = int((bbox[2] - left_lon) * 3600)
    
    # Ensure we don't get empty arrays on tiny selections
    row_start, row_end = min(row_start, row_end), max(row_start, row_end)
    col_start, col_end = min(col_start, col_end), max(col_start, col_end)
    
    cropped = raw_data[row_start:row_end, col_start:col_end]
    
    # ... previous code: cropped = raw_data[row_start:row_end, col_start:col_end] ...
    
    print("[?] Calculating true ground slope (Trend Surface Analysis)...")
    
    # 1. Create coordinate grids for the cropped data
    Y_idx, X_idx = np.mgrid[0:cropped.shape[0], 0:cropped.shape[1]]
    
    # Flatten the arrays to feed into our math solver
    X_flat = X_idx.flatten()
    Y_flat = Y_idx.flatten()
    Z_flat = cropped.flatten()
    
    # 2. Fit a 2D Plane (Equation: Z = a*X + b*Y + c)
    # This finds the absolute perfect "average slope" of the ground, ignoring radar noise
    A = np.c_[X_flat, Y_flat, np.ones_like(X_flat)]
    C, _, _, _ = np.linalg.lstsq(A, Z_flat, rcond=None)
    
    # 3. Generate the 1024x1024 Ultra-Smooth Glassy Grid
    print("[?] Generating perfectly smooth 1024x1024 gradient surface...")
    final_res = 1024
    grid_y, grid_x = np.mgrid[0:cropped.shape[0]-1:complex(0, final_res), 
                              0:cropped.shape[1]-1:complex(0, final_res)]
                              
    # Calculate the exact height for every single pixel on that perfect plane
    elev_smooth = C[0]*grid_x + C[1]*grid_y + C[2]

    # 4. Save Final GeoTIFF
    dem_path = os.path.join(folder, "terrain_elevation_pro.tif")
    transform = from_bounds(bbox[3], bbox[1], bbox[2], bbox[0], final_res, final_res)
    
    with rasterio.open(
        dem_path, 'w', driver='GTiff', height=final_res, width=final_res,
        count=1, dtype='float32', crs='EPSG:4326', transform=transform
    ) as dst:
        dst.write(elev_smooth.astype('float32'), 1)
        
    print(f"\n[✓] SUCCESS! Perfect glassy DEM saved: {dem_path}")

if __name__ == "__main__":
    main()