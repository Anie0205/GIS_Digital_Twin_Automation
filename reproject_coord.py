import os
import sys
import json
import geopandas as gpd
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pyproj import Transformer # <-- NEW IMPORT for metric coordinate conversion

def reproject_vectors(folder, target_epsg):
    """Reprojects all GeoJSON files in the folder to the target UTM EPSG."""
    for file in os.listdir(folder):
        if file.endswith(".geojson") and "_utm" not in file:
            path = os.path.join(folder, file)
            gdf = gpd.read_file(path)
            
            print(f"[?] Reprojecting Vector: {file} -> {target_epsg}")
            gdf_utm = gdf.to_crs(target_epsg)
            output_name = file.replace(".geojson", "_utm.geojson")
            output_path = os.path.join(folder, output_name)
            
            try:
                if os.path.exists(output_path): os.remove(output_path)
                gdf_utm.to_file(output_path, driver='GeoJSON')
            except PermissionError:
                print(f"\n[!] ERROR: '{output_name}' is locked by Geovia/QGIS. Close to retry...")
                input()
                gdf_utm.to_file(output_path, driver='GeoJSON')

def reproject_raster(input_path, target_epsg):
    """Reprojects a GeoTIFF using the native, uncorrupted rasterio transform."""
    output_path = input_path.replace(".tif", "_utm.tif")
    
    with rasterio.open(input_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, target_epsg, src.width, src.height, *src.bounds)
        
        kwargs = src.meta.copy()
        kwargs.update({
            'crs': target_epsg,
            'transform': transform,
            'width': width,
            'height': height
        })

        print(f"[?] Reprojecting Raster: {os.path.basename(input_path)} -> {target_epsg}")
        with rasterio.open(output_path, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_epsg,
                    resampling=Resampling.bilinear
                )
    return output_path

def update_metadata_metric_bounds(metadata, meta_path):
    """Calculates and saves the precise metric UTM bounds into the metadata.json."""
    target_epsg = metadata['epsg']
    n, s, e, w = metadata['bbox']

    # Convert WGS84 degrees to target UTM meters
    transformer_to_utm = Transformer.from_crs("EPSG:4326", target_epsg, always_xy=True)
    x_min, y_min = transformer_to_utm.transform(w, s)
    x_max, y_max = transformer_to_utm.transform(e, n)

    # Update JSON with the exact metric limits for GEOVIA
    metadata["bbox_metric_utm"] = {
        "X_Min": round(x_min, 3),
        "X_Max": round(x_max, 3),
        "Y_Min": round(y_min, 3),
        "Y_Max": round(y_max, 3),
        "Width_Meters": round(x_max - x_min, 3),
        "Height_Meters": round(y_max - y_min, 3)
    }

    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=4)

    print("\n[OK] METADATA UPDATED WITH METRIC LIMITS FOR GEOVIA:")
    print(f"  Lower-Left (South-West) -> X min: {round(x_min, 3)}, Y min: {round(y_min, 3)}")
    print(f"  Upper-Right (North-East) -> X max: {round(x_max, 3)}, Y max: {round(y_max, 3)}")

def main():
    if len(sys.argv) > 1:
        project_dir = sys.argv[1]
        print(f"\n[!] Auto-loaded project folder: {project_dir}")
    else:
        project_dir = input("\nEnter project folder (e.g., Lajpat_Nagar): ").strip()
    abs_path = os.path.abspath(project_dir)
    meta_path = os.path.join(abs_path, "metadata.json")
    
    with open(meta_path, "r") as f:
        metadata = json.load(f)
    
    # 3DExperience GDA requires metric CRS (UTM)
    target_epsg = metadata['epsg'] 
    print(f"\n[!] Target System: {target_epsg} (Metric UTM)")

    # 1. Update the metadata.json with the calculated metric bounds
    update_metadata_metric_bounds(metadata, meta_path)

    print("\n--- Starting Data Reprojection ---")

    # 2. Reproject Vectors (Buildings/Roads)
    reproject_vectors(abs_path, target_epsg)

    # 3. Reproject Rasters (Ortho & AI-Terrain)
    raster_files = ["ortho_final.tif", "terrain_geoai_final.tif", "terrain_elevation_pro.tif"]
    for r_file in raster_files:
        r_path = os.path.join(abs_path, r_file)
        if os.path.exists(r_path):
            reproject_raster(r_path, target_epsg)

    print(f"\n[OK] GDA Prep Complete! Use the *_utm files for 3DExperience.")

if __name__ == "__main__":
    main()