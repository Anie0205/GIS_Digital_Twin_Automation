import subprocess
import sys
import os

def run_pipeline():
    print(f"\n{'='*20} PHASE 1: INITIALIZATION {'='*20}")
    
    # Force UTF-8 environment for Windows compatibility
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    process = subprocess.Popen(
        [sys.executable, "vectors_pipeline.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding='utf-8', # Force UTF-8 reading
        env=env
    )

    detected_folder = None
    
    for line in process.stdout:
        # This will now print safely even with Unicode symbols
        print(line, end="") 
        if "PIPELINE_CONFIRMED_FOLDER:" in line:
            detected_folder = line.split("PIPELINE_CONFIRMED_FOLDER:")[1].strip()

    process.wait()

    if not detected_folder:
        print("\n[ERROR] Pipeline failed: Could not capture folder name from Phase 1.")
        return

    subsequent_phases = [
        "ortho_elevation.py",
        "terrain_elevation.py",
        "geoai_terrain.py",
        "reproject_coord.py",
        "geoai_height.py"
    ]

    print(f"\n[!] Handshake Successful. Project Folder Identified: {detected_folder}")
    
    for script in subsequent_phases:
        if not os.path.exists(script):
            continue
            
        print(f"\n{'='*20} RUNNING: {script} {'='*20}")
        try:
            # Pass the folder name and keep encoding consistent
            subprocess.run([sys.executable, script, detected_folder], check=True, env=env)
        except subprocess.CalledProcessError:
            print(f"\n[ERROR] Critical error in {script}. Stopping pipeline.")
            break
    else:
        print("\n" + "="*60)
        print(f" SUCCESS: Digital Twin for '{detected_folder}' is complete.")
        print("="*60)

if __name__ == "__main__":
    run_pipeline()