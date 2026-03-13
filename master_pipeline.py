import subprocess
import sys
import os

# 1. Update run_script to accept extra arguments
def run_script(script_name, *args):
    """Executes a python script and waits for it to complete."""
    print(f"\n{'='*60}")
    print(f" >>> STARTING PHASE: {script_name}")
    print(f"{'='*60}\n")
    
    try:
        # Pass the extra arguments (like folder name) to the script
        process = subprocess.run([sys.executable, script_name, *args], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Error occurred in {script_name}. Pipeline halted.")
        return False
    except FileNotFoundError:
        print(f"\n[X] Script not found: {script_name}. Check your file names.")
        return False

def main():
    pipeline = [
        "vectors_pipeline.py",     
        "ortho_elevation.py",      
        "terrain_elevation.py",    
        "geoai_terrain.py",        
        "reproject_coord.py",      
        "geoai_height.py"          
    ]

    print("GeoAI Digital Twin - Master Orchestrator")
    print("-----------------------------------------")
    
    project_folder = None # Store the folder name here

    for script in pipeline:
        if not os.path.exists(script):
            if script == "reproject_coord.py" and os.path.exists("reproject_coords.py"):
                script = "reproject_coords.py"
        
        # 2. Handle Phase 1 and extract the folder name
        if script == "vectors_pipeline.py":
            success = run_script(script)
            if success and os.path.exists(".current_project.txt"):
                with open(".current_project.txt", "r") as f:
                    project_folder = f.read().strip()
        else:
            # 3. Pass the folder name to all subsequent scripts
            if project_folder:
                success = run_script(script, project_folder)
            else:
                success = run_script(script)

        if not success:
            break
    else:
        print(f"\n{'='*60}")
        print(" [✓] MASTER PIPELINE COMPLETE")
        print(" Your digital twin is ready for GEOVIA Packager.")
        print(f"{'='*60}")

    # 4. Clean up the temp file
    if os.path.exists(".current_project.txt"):
        os.remove(".current_project.txt")

if __name__ == "__main__":
    main()