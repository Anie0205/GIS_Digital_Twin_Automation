import subprocess
import sys
import os

def run_script(script_name):
    """Executes a python script and waits for it to complete."""
    print(f"\n{'='*60}")
    print(f" >>> STARTING PHASE: {script_name}")
    print(f"{'='*60}\n")
    
    try:
        # We use sys.executable to ensure it uses the same python environment
        process = subprocess.run([sys.executable, script_name], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error occurred in {script_name}. Pipeline halted.")
        return False
    except FileNotFoundError:
        print(f"\n[X] Script not found: {script_name}. Check your file names.")
        return False

def main():
    # Define the execution order
    pipeline = [
        "vectors_pipeline.py",     # Phase 1: Init & Vector Extraction
        "ortho_elevation.py",      # Phase 2: Satellite Texture
        "terrain_elevation.py",    # Phase 3: Baseline Elevation (SRTM)
        "geoai_terrain.py",        # Phase 4: AI Depth Fusion
        "reproject_coord.py",      # Phase 5: Metric Reprojection
        "geoai_height.py"          # Phase 6: 3D Building Extrusion
    ]

    print("GeoAI Digital Twin - Master Orchestrator")
    print("-----------------------------------------")
    
    for script in pipeline:
        if not os.path.exists(script):
            # Check for common naming variations
            if script == "reproject_coord.py" and os.path.exists("reproject_coords.py"):
                script = "reproject_coords.py"
        
        success = run_script(script)
        if not success:
            break
    else:
        print(f"\n{'='*60}")
        print(" [✓] MASTER PIPELINE COMPLETE")
        print(" Your digital twin is ready for GEOVIA Packager.")
        print(f"{'='*60}")

if __name__ == "__main__":
    main()