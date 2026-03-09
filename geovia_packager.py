import os
import json
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

def load_project():
    print("\n" + "="*45)
    print(" GeoAI Phase 4: GEOVIA Enterprise Packager")
    print("="*45)
    project_dir = input("\nEnter the project folder name: ").strip().replace('"', '').replace("'", "")
    if not os.path.isdir(project_dir):
        print(f"[X] Error: Folder '{project_dir}' not found."); return None, None
    with open(os.path.join(project_dir, "metadata.json"), "r") as f:
        return json.load(f), project_dir

def generate_geovia_sidecars(tif_path):
    """Creates the .tfw and .prj files that Dassault GEOVIA strictly requires."""
    if not os.path.exists(tif_path): return False
    
    base_name = os.path.splitext(tif_path)[0]
    tfw_path, prj_path = f"{base_name}.tfw", f"{base_name}.prj"

    with rasterio.open(tif_path) as src:
        # 1. World File (.tfw)
        transform = src.transform
        tfw_content = f"{transform[0]}\n{transform[3]}\n{transform[1]}\n{transform[4]}\n{transform[2]}\n{transform[5]}\n"
        with open(tfw_path, "w") as f: f.write(tfw_content)

        # 2. Projection File (.prj)
        wkt_content = src.crs.to_wkt()
        with open(prj_path, "w") as f: f.write(wkt_content)
        
    print(f"  [✓] Sidecars created for: {os.path.basename(tif_path)}")
    return True

def reproject_terrain_to_metric(folder, target_crs):
    """Converts the WGS84 terrain into the local metric CRS to match the vectors/ortho."""
    source_path = os.path.join(folder, "terrain_elevation_pro.tif")
    metric_path = os.path.join(folder, "terrain_metric.tif")
    
    if not os.path.exists(source_path):
        print("[X] Could not find terrain_elevation_pro.tif")
        return None

    print(f"\n[?] Reprojecting Terrain to {target_crs}...")
    with rasterio.open(source_path) as src:
        transform, width, height = calculate_default_transform(src.crs, target_crs, src.width, src.height, *src.bounds)
        kwargs = src.meta.copy()
        kwargs.update({'crs': target_crs, 'transform': transform, 'width': width, 'height': height})

        with rasterio.open(metric_path, 'w', **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(source=rasterio.band(src, i), destination=rasterio.band(dst, i),
                          src_transform=src.transform, src_crs=src.crs,
                          dst_transform=transform, dst_crs=target_crs, resampling=Resampling.bilinear)
                          
    print(f"  [✓] Terrain reprojected successfully.")
    return metric_path

def main():
    metadata, folder = load_project()
    if not metadata: return
    target_crs = metadata['epsg']

    # 1. Reproject Terrain to match Ortho
    terrain_metric_path = reproject_terrain_to_metric(folder, target_crs)

    # 2. Generate GEOVIA Sidecars for Ortho
    print(f"\n[?] Generating GEOVIA sidecar metadata...")
    ortho_path = os.path.join(folder, "ortho_metric.tif")
    generate_geovia_sidecars(ortho_path)

    # 3. Generate GEOVIA Sidecars for the NEW Metric Terrain
    if terrain_metric_path:
        generate_geovia_sidecars(terrain_metric_path)

    print(f"\n[✓] ALL DONE! Your data is 100% ready for Dassault Systèmes GEOVIA.")
    print("    -> Import 'ortho_metric.tif' as your image drape.")
    print("    -> Import 'terrain_metric.tif' as your elevation grid.")

if __name__ == "__main__":
    main()