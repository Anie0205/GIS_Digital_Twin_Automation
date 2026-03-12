import subprocess
import sys
import os

def run_pipeline():
    # 1. Execute Phase 1 and capture the folder name it generates
    print(f"\n{'='*20} PHASE 1: INITIALIZATION {'='*20}")
    
    # We use Popen so you can still see the map and interact with the terminal
    process = subprocess.Popen(
        [sys.executable, "vectors_pipeline.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    detected_folder = None
    
    # Stream the output to your terminal in real-time
    for line in process.stdout:
        print(line, end="")
        if "PIPELINE_CONFIRMED_FOLDER:" in line:
            detected_folder = line.split("PIPELINE_CONFIRMED_FOLDER:")[1].strip()

    process.wait()

    if not detected_folder:
        print("\n[X] Pipeline failed: Could not capture folder name from Phase 1.")
        return

    # 2. Define the remaining scripts in order
    subsequent_phases = [
        "ortho_elevation.py",
        "terrain_elevation.py",
        "geoai_terrain.py",
        "reproject_coord.py",
        "geoai_height.py"
    ]

    # 3. Automatically execute the rest of the scripts
    print(f"\n[!] Handshake Successful. Project Folder Identified: {detected_folder}")
    
    for script in subsequent_phases:
        if not os.path.exists(script):
            print(f"[?] Skipping {script} (File not found)")
            continue
            
        print(f"\n{'='*20} RUNNING: {script} {'='*20}")
        try:
            # Passes the detected_folder as sys.argv[1] to each script
            subprocess.run([sys.executable, script, detected_folder], check=True)
        except subprocess.CalledProcessError:
            print(f"\n[!] Critical error in {script}. Stopping pipeline.")
            break
    else:
        print("\n" + "="*60)
        print(f" SUCCESS: Digital Twin for '{detected_folder}' is complete.")
        print("="*60)

if __name__ == "__main__":
    run_pipeline()