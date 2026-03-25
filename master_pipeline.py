import subprocess
import sys
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
        print(f"\n{'='*60}", flush=True)
        print(" [OK] MASTER PIPELINE COMPLETE", flush=True)
        print(" Your digital twin is ready for GEOVIA Packager.", flush=True)
        print(f"{'='*60}", flush=True)

    if os.path.exists(".current_project.txt"):
        os.remove(".current_project.txt")

if __name__ == "__main__":
    main()