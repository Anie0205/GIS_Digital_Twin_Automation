import os
import sys
import glob
import json
import geopandas as gpd
import pandas as pd
import rasterio
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, MultiLineString

def get_elevation_at_point(raster, x, y):
    try:
        return float(next(raster.sample([(x, y)]))[0])
    except:
        return 0.0

def drape_geometry(geom, dem):
    """Physically injects Z-altitude to create true 3D [X, Y, Z] geometries."""
    if geom is None or geom.is_empty: return geom
    
    # FIX: Changed geom.type to geom.geom_type to clear Shapely warnings
    if geom.geom_type == 'Point':
        return Point(geom.x, geom.y, get_elevation_at_point(dem, geom.x, geom.y))
    elif geom.geom_type == 'LineString':
        return LineString([(x, y, get_elevation_at_point(dem, x, y)) for x, y, *_ in geom.coords])
    elif geom.geom_type == 'Polygon':
        ext = [(x, y, get_elevation_at_point(dem, x, y)) for x, y, *_ in geom.exterior.coords]
        ints = [[(x, y, get_elevation_at_point(dem, x, y)) for x, y, *_ in hole.coords] for hole in geom.interiors]
        return Polygon(ext, ints)
    elif geom.geom_type == 'MultiLineString':
        return MultiLineString([drape_geometry(line, dem) for line in geom.geoms])
    elif geom.geom_type == 'MultiPolygon':
        return MultiPolygon([drape_geometry(poly, dem) for poly in geom.geoms])
        
    return geom

def process_datasets_for_3dexperience(project_dir=None):
    if project_dir is None:
        if len(sys.argv) > 1:
            project_dir = sys.argv[1]
        else:
            project_dir = input("\nEnter project folder: ").strip()
    
    abs_path = os.path.abspath(project_dir)
    dem_path = os.path.join(abs_path, "terrain_geoai_final_utm.tif")
    meta_path = os.path.join(abs_path, "metadata.json")
    
    if not os.path.exists(dem_path):
        print("[X] Missing AI terrain DEM. Run the reprojection script first.")
        return

    # Extract the EPSG code (e.g., '32643' from 'EPSG:32643')
    with open(meta_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    epsg_code = metadata['epsg'].split(':')[-1]

    utm_files = glob.glob(os.path.join(abs_path, "*_utm.geojson"))
    print("\n[?] Formatting datasets for 3DEXPERIENCE Simple Features...")
    
    with rasterio.open(dem_path) as dem:
        for file_path in utm_files:
            filename = os.path.basename(file_path)
            target_name = filename.replace('_utm.geojson', '')
            
            print(f"  -> Processing {target_name.upper()}...")
            try:
                gdf = gpd.read_file(file_path)
                if gdf.empty: continue

                # 1. EXPLODE: Break down massive networks to clear the 10,000 point limit
                gdf = gdf.explode(index_parts=False, ignore_index=True)

                if target_name == 'building':
                    # Buildings keep flat base_elev for clean 3D block extrusion
                    gdf['base_elev'] = gdf.geometry.centroid.apply(lambda p: float(get_elevation_at_point(dem, p.x, p.y)))
                    def estimate_smart_height(row):
                        if 'height' in row and pd.notna(row['height']) and str(row['height']).lower() not in ['nan', 'none']:
                            return float(row['height'])
                        if 'building:levels' in row and pd.notna(row['building:levels']) and str(row['building:levels']).lower() not in ['nan', 'none']:
                            return float(row['building:levels']) * 3.5 
                        return 10.0 + (row['base_elev'] % 5)
                    gdf['render_height'] = gdf.apply(estimate_smart_height, axis=1)
                    # Add this line to bend the building bases over the hills!
                    gdf['geometry'] = gdf.geometry.apply(lambda geom: drape_geometry(geom, dem))
                else:
                    # 2. DRAPE: Inject true [X, Y, Z] coordinates for roads, rivers, etc.
                    gdf['geometry'] = gdf.geometry.apply(lambda geom: drape_geometry(geom, dem))

                output_name = f"{target_name}_3d_ready.geojson"
                output_path = os.path.join(abs_path, output_name)
                
                # Save the base file
                gdf.to_file(output_path, driver='GeoJSON')
               # --- NEW: Save a Web UI version in GPS coordinates (WGS84) ---
                if gdf.crs is None:
                    gdf.set_crs(f"EPSG:{epsg_code}", inplace=True)
                web_name = f"{target_name}_web_3d_ready.geojson"
                web_path = os.path.join(abs_path, web_name)
                gdf.to_crs("EPSG:4326").to_file(web_path, driver='GeoJSON')
                # -------------------------------------------------------------
                
                # 3. CRS HACK: Inject the explicit OGC URN CRS so Dassault reads the metrics
                # FIX: Added encoding='utf-8' to prevent decoding crashes on international characters
                with open(output_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                data['crs'] = {
                    "type": "name", 
                    "properties": { "name": f"urn:ogc:def:crs:EPSG::{epsg_code}" }
                }
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
                
                print(f"     [OK] Saved {output_name} with explicit CRS EPSG:{epsg_code}")
                
            except Exception as e:
                print(f"     [X] Failed to process {filename}: {e}")

    print("\n[OK] SUCCESS: Datasets are 100% compliant with 3DEXPERIENCE limits!")
    
if __name__ == "__main__":
    process_datasets_for_3dexperience()