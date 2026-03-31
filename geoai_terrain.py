import os
import sys
import json
import torch
import numpy as np
import rasterio
from PIL import Image
from transformers import pipeline
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
import cv2

# --- CONFIGURATION ---
MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf" # Lightweight for P1000
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def load_data(project_dir):
    # Load metadata and paths
    with open(os.path.join(project_dir, "metadata.json"), "r") as f:
        meta = json.load(f)
    
    ortho_path = os.path.join(project_dir, "ortho_final.tif")
    srtm_path = os.path.join(project_dir, "terrain_elevation_pro.tif") # From your Skadi script
    
    return meta, ortho_path, srtm_path

def generate_geoai_dem(project_folder=None):
    if project_folder is None:
        if len(sys.argv) > 1:
            project_folder = sys.argv[1]
            print(f"\n[!] Auto-loaded project folder: {project_folder}")
        else:
            project_folder = input("\nEnter project folder: ").strip()
            
    meta, ortho_path, srtm_path = load_data(project_folder)
    
    if not os.path.exists(ortho_path) or not os.path.exists(srtm_path):
        print("[X] Missing ortho_final.tif or SRTM baseline. Run previous scripts first.")
        return

    # 1. Initialize Depth Anything V2
    print(f"[?] Loading GeoAI Model onto {DEVICE}...")
    pipe = pipeline("depth-estimation", model=MODEL_ID, device=DEVICE)

    # 2. Run AI Inference on High-Res Ortho (PATCH-BASED APPROACH)
    print("[?] AI inferring micro-terrain shapes (Patch Processing to prevent Out-Of-Memory)...")
    image = Image.open(ortho_path).convert("RGB")
    img_width, img_height = image.size
    
    # Create an empty array for the final depth map
    ai_depth = np.zeros((img_height, img_width), dtype=np.float32)
    patch_size = 1024

    for y in range(0, img_height, patch_size):
        for x in range(0, img_width, patch_size):
            # Calculate patch boundaries
            box = (x, y, min(x + patch_size, img_width), min(y + patch_size, img_height))
            patch = image.crop(box)
            
            # Run inference on the small patch
            res = pipe(patch)
            patch_depth = np.array(res["depth"])
            
            # Paste the result back into the master array
            ai_depth[y:box[3], x:box[2]] = patch_depth

    # Normalize the combined depth map to 0-1
    ai_depth = (ai_depth - ai_depth.min()) / (ai_depth.max() - ai_depth.min())

    # 3. Load SRTM Baseline and prepare for Fusion
    with rasterio.open(srtm_path) as srtm_src:
        srtm_data = srtm_src.read(1)
        srtm_meta = srtm_src.meta.copy()
        target_shape = srtm_data.shape

    # 4. Correct Coordinate-Aware Fusion
    print("[?] Aligning AI depth map to SRTM coordinates...")
    
    # We create a temporary in-memory raster for the AI depth 
    # and reproject it to match the SRTM grid exactly.
    ai_aligned = np.zeros(target_shape, dtype='float32')
    
    # Define the transform for the AI data (based on the Ortho it came from)
    with rasterio.open(ortho_path) as ortho_src:
        reproject(
            source=ai_depth,
            destination=ai_aligned,
            src_transform=ortho_src.transform,
            src_crs=ortho_src.crs,
            dst_transform=srtm_meta['transform'],
            dst_crs=srtm_meta['crs'],
            resampling=Resampling.bilinear
        )

    print(f"[?] Fusing aligned AI detail with heights...")
    srtm_min, srtm_max = srtm_data.min(), srtm_data.max()
    fused_dem = (ai_aligned * (srtm_max - srtm_min)) + srtm_min
    # 5. Save Final GeoAI DEM
    output_path = os.path.join(project_folder, "terrain_geoai_final.tif")
    bbox = meta['bbox']
    transform = from_bounds(bbox[3], bbox[1], bbox[2], bbox[0], target_shape[1], target_shape[0])
    
    with rasterio.open(
        output_path, 'w', driver='GTiff', height=target_shape[0], width=target_shape[1],
        count=1, dtype='float32', crs='EPSG:4326', transform=transform
    ) as dst:
        dst.write(fused_dem.astype('float32'), 1)

    print(f"\n[OK] SUCCESS: GeoAI Terrain generated: {output_path}")

if __name__ == "__main__":
    generate_geoai_dem()