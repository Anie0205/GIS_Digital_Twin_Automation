import os
import json
import geopandas as gpd
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

def reproject_vectors(folder, target_epsg):
    """Reprojects all GeoJSON files in the folder to the target UTM EPSG."""
    for file in os.listdir(folder):
        if file.endswith(".geojson") and "_utm" not in file:
            path = os.path.join(folder, file)
            gdf = gpd.read_file(path)
            
            print(f"[?] Reprojecting Vector: {file} -> {target_epsg}")
            gdf_utm = gdf.to_crs(target_epsg)
            
            # Save with _utm suffix for GDA identification
            output_name = file.replace(".geojson", "_utm.geojson")
            gdf_utm.to_file(os.path.join(folder, output_name), driver='GeoJSON')

def reproject_raster(input_path, target_epsg):
    """Reprojects a GeoTIFF to the target UTM EPSG for 3DExperience ingestion."""
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
                    resampling=Resampling.bilinear # Smooths elevation/imagery
                )
    return output_path

def main():
    project_dir = input("\nEnter project folder (e.g., Lajpat_Nagar): ").strip()
    abs_path = os.path.abspath(project_dir)
    
    with open(os.path.join(abs_path, "metadata.json"), "r") as f:
        metadata = json.load(f)
    
    # 3DExperience GDA requires metric CRS (UTM)
    target_epsg = metadata['epsg'] 
    print(f"\n[!] Target System: {target_epsg} (Metric UTM)")

    # 1. Reproject Vectors (Buildings/Roads)
    reproject_vectors(abs_path, target_epsg)

    # 2. Reproject Rasters (Ortho & AI-Terrain)
    raster_files = ["ortho_final.tif", "terrain_geoai_final.tif"]
    for r_file in raster_files:
        r_path = os.path.join(abs_path, r_file)
        if os.path.exists(r_path):
            reproject_raster(r_path, target_epsg)

    print(f"\n[✓] GDA Prep Complete! Use the *_utm files for 3DExperience.")

if __name__ == "__main__":
    main()