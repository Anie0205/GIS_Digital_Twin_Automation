from flask import Flask, render_template, request, Response, send_file
import time
import json
import os
import shutil
import subprocess
import sys

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stream_pipeline')  
def stream_pipeline():
    target_data = request.args.get('target', '') 
    display_name = request.args.get('name', 'Selected_Area').replace(" ", "_")
    imagery_choice = request.args.get('imagery', '3') # <--- NEW: Get the imagery choice
    
    def generate():
        def push_update(stage, detail, status="running"):
            data = json.dumps({"stage": stage, "detail": detail, "status": status})
            return f"data: {data}\n\n"

        # Dictionary to map script names to UI text
        stage_map = {
            "vectors_pipeline.py": ("Vector Pipeline", f"Extracting OpenStreetMap vectors for {display_name}..."),
            "ortho_elevation.py": ("Ortho Imagery", "Downloading and processing high-res satellite tiles..."),
            "terrain_elevation.py": ("Terrain Elevation", "Processing DEM baseline topologies..."),
            "geoai_terrain.py": ("GeoAI Synthesis", "Fusing imagery with elevation using Depth Models..."),
            "reproject_coord.py": ("Reprojection", "Converting coordinate references to local UTM..."),
            "reproject_coords.py": ("Reprojection", "Converting coordinate references to local UTM..."),
            "geoai_height.py": ("GeoAI Height Extrusion", "Calculating final 3D building metrics...")
        }

        try:
            # Call master_pipeline instead of individual scripts
            process = subprocess.Popen(
                [sys.executable, "-u", "master_pipeline.py", target_data, display_name, imagery_choice],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                encoding='utf-8',
                errors='replace',
                text=True,
                bufsize=1
            )
            
            # Read master_pipeline's console output live
            for line in process.stdout:
                print(line, end="") # Still print to Flask terminal for debugging
                
                # If master_pipeline announces a new phase, trigger a UI update
                if ">>> STARTING PHASE:" in line:
                    script_name = line.split(":")[-1].strip()
                    if script_name in stage_map:
                        stage, detail = stage_map[script_name]
                        yield push_update(stage, detail)

            process.wait()
            
            if process.returncode == 0:
                yield push_update("Compilation Complete", "3D Digital Twin datasets fully generated.", status="complete")
            else:
                yield push_update("Pipeline Failed", "An error occurred during master pipeline execution.", status="error")

        except Exception as e:
            yield push_update("Pipeline Failed", str(e), status="error")

    return Response(generate(), mimetype='text/event-stream')

@app.route('/download/<project_name>')
def download_project(project_name):
    if not os.path.exists(project_name):
        return "Project folder not found.", 404

    zip_filename = f"{project_name}_DigitalTwin"
    shutil.make_archive(zip_filename, 'zip', project_name)
    return send_file(f"{zip_filename}.zip", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)