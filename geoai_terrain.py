import os
import json
import torch
import numpy as np
import rasterio
from PIL import Image
from transformers import pipeline
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

def generate_geoai_dem():
    project_folder = input("\nEnter project folder: ").strip()
    meta, ortho_path, srtm_path = load_data(project_folder)
    
    if not os.path.exists(ortho_path) or not os.path.exists(srtm_path):
        print("[X] Missing ortho_final.tif or SRTM baseline. Run previous scripts first.")
        return

    # 1. Initialize Depth Anything V2
    print(f"[?] Loading GeoAI Model onto {DEVICE}...")
    pipe = pipeline("depth-estimation", model=MODEL_ID, device=DEVICE)

    # 2. Run AI Inference on High-Res Ortho
    print("[?] AI inferring micro-terrain shapes from satellite imagery...")
    image = Image.open(ortho_path).convert("RGB")
    result = pipe(image)
    ai_depth = np.array(result["depth"]) 
    
    # AI depth is often "inverse" (higher value = closer/higher). Normalize to 0-1.
    ai_depth = (ai_depth - ai_depth.min()) / (ai_depth.max() - ai_depth.min())

    # 3. Load SRTM Baseline
    with rasterio.open(srtm_path) as src:
        srtm_data = src.read(1)
        srtm_min, srtm_max = srtm_data.min(), srtm_data.max()
        target_shape = srtm_data.shape

    # 4. Statistical Fusion
    # Resize AI depth map to match SRTM grid resolution
    ai_resized = cv2.resize(ai_depth, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_CUBIC)
    
    # Scale AI relative shapes to the real-world meter range of the SRTM data
    print(f"[?] Fusing AI detail with SRTM heights ({srtm_min}m to {srtm_max}m)...")
    fused_dem = (ai_resized * (srtm_max - srtm_min)) + srtm_min

    # 5. Save Final GeoAI DEM
    output_path = os.path.join(project_folder, "terrain_geoai_final.tif")
    bbox = meta['bbox']
    transform = from_bounds(bbox[3], bbox[1], bbox[2], bbox[0], target_shape[1], target_shape[0])
    
    with rasterio.open(
        output_path, 'w', driver='GTiff', height=target_shape[0], width=target_shape[1],
        count=1, dtype='float32', crs='EPSG:4326', transform=transform
    ) as dst:
        dst.write(fused_dem.astype('float32'), 1)

    print(f"\n[✓] SUCCESS: GeoAI Terrain generated: {output_path}")

if __name__ == "__main__":
    generate_geoai_dem()