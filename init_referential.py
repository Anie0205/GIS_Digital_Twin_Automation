import os
import json

# --- CONFIGURATION FROM YOUR GDA REFERENTIAL ---
PROJECT_NAME = "LJN_Referential_AVA41"
USER_ID = "ava41"
TARGET_EPSG = "EPSG:32643" # UTM Zone 43N

# --- COORDINATES ---
# I corrected the South boundary to 28.5 to create a valid 10km x 10km box.
# Adjust south_lat if your GDA referential uses a different value.
west_lon, south_lat = 77.2, 28.5  
east_lon, north_lat = 77.3, 28.6  

def initialize_project():
    # 1. Create the project folder on your D: drive
    os.makedirs(PROJECT_NAME, exist_ok=True)
    
    # 2. Generate the Master Metadata
    metadata = {
        "location": "Lajpat Nagar - GDA Referential",
        "created_by": USER_ID,
        "timestamp": "2026-03-06 15:06:15",
        "epsg": TARGET_EPSG,
        "bbox": [north_lat, south_lat, east_lon, west_lon], # [N, S, E, W]
        "referential_id": PROJECT_NAME
    }
    
    meta_path = os.path.join(PROJECT_NAME, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=4)
        
    print(f"\n[✓] Project '{PROJECT_NAME}' Initialized.")
    print(f"[!] Metadata saved to: {meta_path}")
    print(f"[!] Coordinate System locked to: {TARGET_EPSG}")

if __name__ == "__main__":
    initialize_project()