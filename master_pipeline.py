import subprocess
import sys
import glob
import os

def run_script(script_name, *args):
    print(f"\n{'='*60}", flush=True)
    print(f" >>> STARTING PHASE: {script_name}", flush=True)
    print(f"{'='*60}\n", flush=True)
    try:
        # Pass the extra arguments (like folder name) to the script
        subprocess.run([sys.executable, "-u", script_name, *args], check=True, encoding='utf-8', errors='replace')
        return True
    except subprocess.CalledProcessError:
        print(f"\n[X] Error occurred in {script_name}. Pipeline halted.", flush=True)
        return False
    except FileNotFoundError:
        print(f"\n[X] Script not found: {script_name}.", flush=True)
        return False
def generate_web_assets(project_folder):
    if not project_folder or not os.path.exists(project_folder):
        return
        
    print(f"\n{'='*60}", flush=True)
    print(" >>> STARTING PHASE: Web Asset Generation", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        
        # Add any .tif files here you want available in your 3D Web UI
        web_rasters = ["ortho_final.tif"]
        
        for raster in web_rasters:
            tif_path = os.path.join(project_folder, raster)
            if os.path.exists(tif_path):
                print(f"[?] Converting {raster} to WebGL-ready PNG...", flush=True)
                png_path = tif_path.replace('.tif', '.png')
                Image.open(tif_path).convert('RGB').save(png_path)
                
        print("[OK] Web assets generated successfully.", flush=True)
    except ImportError:
        print("[!] PIL (Pillow) not installed. Skipping web image generation.", flush=True)
    except Exception as e:
        print(f"[!] Error generating web assets: {e}", flush=True)

def generate_web_terrain(project_folder):
    """Converts raw radar DEM into a WebGL-friendly Terrain-RGB image."""
    if not project_folder or not os.path.exists(project_folder):
        return
        
    print(f"\n{'='*60}", flush=True)
    print(" >>> STARTING PHASE: Web 3D Terrain Generation", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    tif_path = os.path.join(project_folder, "terrain_geoai_final.tif")
    if not os.path.exists(tif_path):
        print("[!] No GeoAI terrain found. Skipping web terrain generation.", flush=True)
        return

    try:
        import numpy as np
        import rasterio
        from PIL import Image
        
        print(f"[?] Encoding {os.path.basename(tif_path)} to Terrain-RGB...", flush=True)
        with rasterio.open(tif_path) as src:
            dem = src.read(1)
            
            # The Magic Math: Hide elevation data inside RGB color channels
            # Formula: height = -10000 + ((R * 256 * 256 + G * 256 + B) * 0.1)
            val = np.clip(np.round((dem + 10000) * 10), 0, 16777215).astype(np.uint32)
            
            r = (val >> 16) & 255
            g = (val >> 8) & 255
            b = val & 255
            
            rgb = np.dstack((r, g, b)).astype(np.uint8)
            output_path = os.path.join(project_folder, "terrain_rgb.png")
            Image.fromarray(rgb).save(output_path)
            
        print("[OK] Terrain Mesh safely encoded for the Web UI.", flush=True)
    except Exception as e:
        print(f"[X] Failed to generate terrain mesh: {e}", flush=True)

def cleanup_intermediate_files(project_folder):
    if not project_folder or not os.path.exists(project_folder):
        return
        
    print(f"\n{'='*60}", flush=True)
    print(" >>> STARTING PHASE: Cleanup", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    print(f"[?] Cleaning up intermediate files in '{project_folder}'...", flush=True)
    files_to_delete = []

    # 1. Delete original unprojected vectors and intermediate UTM vectors
    # We only want to keep the final 3DEXPERIENCE-ready files
    all_geojson = glob.glob(os.path.join(project_folder, "*.geojson"))
    for f in all_geojson:
        if not f.endswith("_3d_ready.geojson"):
            files_to_delete.append(f)

    # 2. Delete raw HGT tiles downloaded from AWS
    files_to_delete.extend(glob.glob(os.path.join(project_folder, "*.hgt")))

    # 3. Delete unprojected baseline rasters (keeping only the _utm.tif versions)
    unprojected_rasters = [
        "ortho_final.tif", 
        "terrain_elevation_pro.tif", 
        "terrain_geoai_final.tif",
        "terrain_elevation_pro_utm.tif" # Keep the GeoAI one, drop the base pro one
    ]
    for raster in unprojected_rasters:
        files_to_delete.append(os.path.join(project_folder, raster))

    count = 0
    for f in files_to_delete:
        if os.path.exists(f):
            try:
                os.remove(f)
                count += 1
            except Exception as e:
                print(f"  [!] Could not delete {os.path.basename(f)}: {e}")
                
    print(f"[OK] Removed {count} intermediate files to save space.", flush=True)

def main():
    # If run from the Web UI, grab the arguments
    if len(sys.argv) >= 4:
        target_data = sys.argv[1]
        display_name = sys.argv[2]
        imagery_choice = sys.argv[3]
    else:
        # Fallback for manual testing
        target_data = None
        display_name = None
        imagery_choice = None

    pipeline = [
        "vectors_pipeline.py",     
        "ortho_elevation.py",      
        "terrain_elevation.py",    
        "geoai_terrain.py",        
        "reproject_coord.py",      
        "geoai_height.py"          
    ]

    print("GeoAI Digital Twin - Master Orchestrator", flush=True)
    print("-----------------------------------------", flush=True)
    
    project_folder = display_name 

    for script in pipeline:
        if not os.path.exists(script):
            if script == "reproject_coord.py" and os.path.exists("reproject_coords.py"):
                script = "reproject_coords.py"
        
        if script == "vectors_pipeline.py":
            if target_data: # Web Mode
                success = run_script(script, target_data, project_folder)
            else:           # Terminal Mode
                success = run_script(script)
                if success and os.path.exists(".current_project.txt"):
                    with open(".current_project.txt", "r") as f:
                        project_folder = f.read().strip()
                        
        elif script == "ortho_elevation.py" and imagery_choice:
            success = run_script(script, project_folder, imagery_choice)
            
        else:
            if project_folder:
                success = run_script(script, project_folder)
            else:
                success = run_script(script)

        if not success:
            break
    else:
        generate_web_assets(project_folder)
        generate_web_terrain(project_folder)
        cleanup_intermediate_files(project_folder)
        
        print(f"\n{'='*60}", flush=True)
        print(" [OK] MASTER PIPELINE COMPLETE", flush=True)
        print(" Your digital twin is ready for GEOVIA Packager.", flush=True)
        print(f"{'='*60}", flush=True)

    if os.path.exists(".current_project.txt"):
        os.remove(".current_project.txt")

if __name__ == "__main__":
    main()