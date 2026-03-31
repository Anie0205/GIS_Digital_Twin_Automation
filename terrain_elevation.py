import os
import sys
import json
import requests
import gzip
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.transform import from_bounds
#from scipy.ndimage import gaussian_filter
#from scipy.interpolate import griddata

def load_project():
    project_dir = sys.argv[1] if len(sys.argv) > 1 else input("Enter project folder: ").strip().replace('"', '').replace("'", "")
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
            print("  [OK] Download and extraction complete.")
            return hgt_path
        else:
            print(f"  [!] AWS returned Error {r.status_code}. Tile coordinates may be invalid.")
            return None
    except Exception as e:
        print(f"  [!] Connection Error: {e}")
        return None

def main(folder=None):
    if folder:
        # If folder is provided, load metadata directly
        with open(os.path.join(folder, "metadata.json"), "r") as f:
            metadata = json.load(f)
    else:
        # Fallback to manual input if run as a standalone script
        metadata, folder = load_project()
    
    if not metadata: return
    # 1. Automated Enterprise Download (MULTI-TILE SUPPORT)
    bbox = metadata['bbox'] # [north, south, east, west]
    
    # Find all integer Lat/Lon blocks that intersect our bbox
    lat_min, lat_max = int(np.floor(bbox[1])), int(np.floor(bbox[0]))
    lon_min, lon_max = int(np.floor(bbox[3])), int(np.floor(bbox[2]))
    
    downloaded_tiles = []
    for lat in range(lat_min, lat_max + 1):
        for lon in range(lon_min, lon_max + 1):
            tile_path = download_aws_skadi_tile(lat, lon, folder)
            if tile_path:
                downloaded_tiles.append(tile_path)
                
    if not downloaded_tiles:
        print("[X] Could not acquire AWS elevation data.")
        return

    # 2. Merge and Crop High-Res HGT data
    print(f"[?] Merging and cropping {len(downloaded_tiles)} SRTM tiles...")
    
    src_files_to_mosaic = []
    for fp in downloaded_tiles:
        # Rasterio natively reads .hgt files as GeoTIFF equivalents
        src = rasterio.open(fp)
        src_files_to_mosaic.append(src)

    mosaic, out_trans = merge(src_files_to_mosaic, bounds=(bbox[3], bbox[1], bbox[2], bbox[0]))
    
    # Close files to free memory
    for src in src_files_to_mosaic:
        src.close()

    cropped = mosaic[0] # Grab the first band (elevation data)
    
    # 3. Trend Surface Analysis (Keep your existing math)
    print("[?] Calculating true ground slope (Trend Surface Analysis)...")
    Y_idx, X_idx = np.mgrid[0:cropped.shape[0], 0:cropped.shape[1]]    # Flatten the arrays to feed into our math solver
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
        
    print(f"\n[OK] SUCCESS! Perfect glassy DEM saved: {dem_path}")

if __name__ == "__main__":
    main()