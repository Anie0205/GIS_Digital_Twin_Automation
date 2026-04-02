from flask import Flask, render_template, request, Response, send_file
from flask import send_from_directory
from flask_cors import CORS
import json
import os
import shutil
import subprocess
import sys

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/stream_pipeline')  
def stream_pipeline():
    target_data = request.args.get('target', '') 
    display_name = request.args.get('name', 'Selected_Area').replace(" ", "_")
    imagery_choice = request.args.get('imagery', '3')
    
    def generate():
        def push_update(stage, detail, status="running"):
            data = json.dumps({"stage": stage, "detail": detail, "status": status})
            return f"data: {data}\n\n"

        stage_map = {
            "vectors_pipeline.py": ("Vector Pipeline", f"Extracting OpenStreetMap vectors for {display_name}..."),
            "ortho_elevation.py": ("Ortho Imagery", "Downloading and processing high-res satellite tiles..."),
            "terrain_elevation.py": ("Terrain Elevation", "Processing DEM baseline topologies..."),
            "geoai_terrain.py": ("GeoAI Synthesis", "Fusing imagery with elevation using Depth Models..."),
            "reproject_coord.py": ("Reprojection", "Converting coordinate references to local UTM..."),
            "reproject_coords.py": ("Reprojection", "Converting coordinate references to local UTM..."),
            "geoai_height.py": ("GeoAI Height Extrusion", "Calculating final 3D building metrics...")
        }

        current_stage = "Initializing"

        try:
            # FORCE PYTHON TO UNBUFFER LOGS SO THE UI DOESN'T FREEZE
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            process = subprocess.Popen(
                [sys.executable, "-u", "master_pipeline.py", target_data, display_name, imagery_choice],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                encoding='utf-8',
                errors='replace',
                text=True,
                bufsize=1,
                env=env
            )
            
            # Grabs the text the millisecond it is generated
            for line in iter(process.stdout.readline, ''):
                sys.stdout.write(line)
                sys.stdout.flush() 
                
                clean_line = line.strip()
                if not clean_line: continue
                
                if ">>> STARTING PHASE:" in line:
                    script_name = line.split(":")[-1].strip()
                    if script_name in stage_map:
                        current_stage, default_detail = stage_map[script_name]
                        yield push_update(current_stage, f"Starting {current_stage}...")
                else:
                    # Pushes EVERYTHING directly to your Web UI
                    yield push_update(current_stage, clean_line)

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

@app.route('/projects/<project_name>/<path:filename>')
def serve_project_file(project_name, filename):
    return send_from_directory(project_name, filename)

@app.route('/vision/<project_name>')
def vision(project_name):
    return render_template('vision.html', project=project_name)

if __name__ == '__main__':
    IS_HF = "SPACE_ID" in os.environ 
    if IS_HF:
        app.run(host="0.0.0.0", port=7860)
    else:
        app.run(host="127.0.0.1", port=5000, debug=True)