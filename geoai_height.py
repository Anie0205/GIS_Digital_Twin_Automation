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
    """
    Original logic: Samples AI terrain and saves building base and height.
    """
    if project_dir is None:
        project_dir = input("\nEnter project folder: ").strip()
    
    abs_path = os.path.abspath(project_dir)
    building_path = os.path.join(abs_path, "building_utm.geojson")
    dem_path = os.path.join(abs_path, "terrain_geoai_final_utm.tif")
    
    if not os.path.exists(building_path) or not os.path.exists(dem_path):
        print("[X] Missing UTM files. Run the reprojection script first.")
        return

    print("[?] Probing AI terrain for building base heights...")
    buildings = gpd.read_file(building_path)
    
    with rasterio.open(dem_path) as dem:
        # 1. Calculate Base Elevation (Z-Zero)
        buildings['base_elev'] = buildings.geometry.centroid.apply(
            lambda p: float(get_elevation_at_point(dem, p.x, p.y))
        )

        # 2. Original Height Estimation
        def calculate_height(row):
            if 'height' in row and row['height'] not in [None, 'nan', 'None']:
                return float(row['height'])
            elif 'building:levels' in row and row['building:levels'] not in [None, 'nan', 'None']:
                return float(row['building:levels']) * 3.5 
            else:
                return 12.0 

        buildings['render_height'] = buildings.apply(calculate_height, axis=1)

    output_path = os.path.join(abs_path, "buildings_3d_ready.geojson")
    buildings.to_file(output_path, driver='GeoJSON')
    
    print(f"\n[✓] SUCCESS: 3D-Ready Buildings saved: {output_path}")
    
if __name__ == "__main__":
    extrude_with_ai_terrain()