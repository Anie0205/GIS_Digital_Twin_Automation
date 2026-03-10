import os
import json
import geopandas as gpd
import rasterio
import numpy as np
from shapely.geometry import Point

def get_elevation_at_point(raster, x, y):
    """Samples the elevation value from the GeoTIFF at a specific UTM coordinate."""
    try:
        # Sample the first band (elevation) at the given (x, y)
        val = next(raster.sample([(x, y)]))[0]
        return val
    except:
        return 0

def extrude_with_ai_terrain(project_dir=None):
    # If no folder is passed (running standalone), ask the user
    if project_dir is None:
        project_dir = input("\nEnter project folder: ").strip()

    abs_path = os.path.abspath(project_dir)
    
    # Load Metadata for UTM code
    with open(os.path.join(abs_path, "metadata.json"), "r") as f:
        meta = json.load(f)
    
    # 1. Load the reprojected UTM Buildings and the AI Terrain
    building_path = os.path.join(abs_path, "building_utm.geojson")
    dem_path = os.path.join(abs_path, "terrain_geoai_final_utm.tif")
    
    if not os.path.exists(building_path) or not os.path.exists(dem_path):
        print("[X] Missing UTM files. Run the reprojection script first.")
        return

    print("[?] Loading building footprints and GeoAI terrain...")
    buildings = gpd.read_file(building_path)
    
    with rasterio.open(dem_path) as dem:
        print("[?] Probing AI terrain for building base heights...")
        
        # 2. Calculate Base Elevation (Z-Zero)
        # We take the centroid of the building to find where it sits on the ground
        buildings['base_elev'] = buildings.geometry.centroid.apply(
            lambda p: get_elevation_at_point(dem, p.x, p.y)
        )

        # 3. Intelligent Height Estimation
        # If OSM has no height, we use the building 'levels' attribute or a default
        def calculate_height(row):
            if 'height' in row and row['height'] not in [None, 'nan', 'None']:
                return float(row['height'])
            elif 'building:levels' in row and row['building:levels'] not in [None, 'nan', 'None']:
                return float(row['building:levels']) * 3.5 # Standard 3.5m per floor
            else:
                return 12.0 # Default ~3-4 story building for urban India

        buildings['render_height'] = buildings.apply(calculate_height, axis=1)

    # 4. Save for 3DExperience GDA
    # GDA needs these attributes to know where to 'start' and 'stop' the 3D mesh
    output_path = os.path.join(abs_path, "buildings_3d_ready.geojson")
    buildings.to_file(output_path, driver='GeoJSON')
    
    print(f"\n[✓] SUCCESS: 3D-Ready Buildings saved: {output_path}")
    print("    - 'base_elev': Ground level in meters")
    print("    - 'render_height': Extrusion height in meters")

if __name__ == "__main__":
    extrude_with_ai_terrain()