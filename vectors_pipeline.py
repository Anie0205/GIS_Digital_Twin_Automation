import os
import sys
import json
import time
import datetime
import tkinter as tk
import tkintermapview
import osmnx as ox
import geopandas as gpd
import pandas as pd
from pyproj import Transformer

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_utm_epsg(lat, lon):
    zone = int((lon + 180) / 6) + 1
    epsg_base = 32600 if lat >= 0 else 32700
    return f"EPSG:{epsg_base + zone}"

def force_perfect_square_and_metrics(bbox_raw, target_epsg):
    n, s, e, w = bbox_raw
    transformer_to_utm = Transformer.from_crs("EPSG:4326", target_epsg, always_xy=True)
    x_min_raw, y_min_raw = transformer_to_utm.transform(w, s)
    x_max_raw, y_max_raw = transformer_to_utm.transform(e, n)
    
    width_m = x_max_raw - x_min_raw
    height_m = y_max_raw - y_min_raw
    side_length_m = max(width_m, height_m)
    
    cx, cy = (x_min_raw + x_max_raw) / 2, (y_min_raw + y_max_raw) / 2
    
    x_min, x_max = cx - (side_length_m / 2), cx + (side_length_m / 2)
    y_min, y_max = cy - (side_length_m / 2), cy + (side_length_m / 2)

    transformer_to_wgs = Transformer.from_crs(target_epsg, "EPSG:4326", always_xy=True)
    w_new, s_new = transformer_to_wgs.transform(x_min, y_min)
    e_new, n_new = transformer_to_wgs.transform(x_max, y_max)
    
    metric_dict = {
        "X_Min": round(x_min, 3),
        "X_Max": round(x_max, 3),
        "Y_Min": round(y_min, 3),
        "Y_Max": round(y_max, 3),
        "Side_Length_Meters": round(side_length_m, 3)
    }
    return (n_new, s_new, e_new, w_new), metric_dict

def get_bbox_from_text(query):
    print(f"\n[?] Searching OpenStreetMap for '{query}'...")
    try:
        gdf = ox.geocode_to_gdf(query)
        official_name = gdf.iloc[0]['display_name']
        bounds = gdf.total_bounds 
        bbox = (bounds[3], bounds[1], bounds[2], bounds[0])
        print(f"[OK] Location found: {official_name}")
        return bbox, query.replace(" ", "_").replace(",", "")
    except Exception:
        print(f"[X] Could not find exact boundaries for '{query}'.")
        return None, None

def get_bbox_from_map():
    state = {"start_lat_lon": None, "current_poly": None, "final_bbox": None}
    root = tk.Tk()
    root.geometry("800x650")
    root.title("GeoAI - Click and Drag to Select Area")
    label = tk.Label(root, text="Right-Click and DRAG to draw your extraction area", font=("Helvetica", 12, "bold"))
    label.pack(pady=5)
    map_widget = tkintermapview.TkinterMapView(root, width=800, height=500, corner_radius=0)
    map_widget.pack(fill="both", expand=True)
    map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=22)
    map_widget.set_position(28.56, 77.24) 
    map_widget.set_zoom(12)

    def confirm_selection():
        if state["final_bbox"]: root.quit() 
        else: label.config(text="Please draw an area first!", fg="red")

    btn = tk.Button(root, text="Confirm Selection", command=confirm_selection, font=("Helvetica", 12, "bold"), bg="green", fg="white")
    btn.pack(pady=10)

    def on_button_press(event):
        state["start_lat_lon"] = map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        if state["current_poly"]: state["current_poly"].delete()

    def on_mouse_drag(event):
        if state["start_lat_lon"] is None: return
        curr_lat_lon = map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        if state["current_poly"]: state["current_poly"].delete()
        n, s = max(state["start_lat_lon"][0], curr_lat_lon[0]), min(state["start_lat_lon"][0], curr_lat_lon[0])
        e, w = max(state["start_lat_lon"][1], curr_lat_lon[1]), min(state["start_lat_lon"][1], curr_lat_lon[1])
        path = [(n, w), (n, e), (s, e), (s, w), (n, w)]
        state["current_poly"] = map_widget.set_path(path, color="yellow", width=3)

    def on_button_release(event):
        curr_lat_lon = map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        n, s = max(state["start_lat_lon"][0], curr_lat_lon[0]), min(state["start_lat_lon"][0], curr_lat_lon[0])
        e, w = max(state["start_lat_lon"][1], curr_lat_lon[1]), min(state["start_lat_lon"][1], curr_lat_lon[1])
        state["final_bbox"] = (n, s, e, w)
        label.config(text="Area Selected! Click 'Confirm Selection' below to proceed.", fg="blue")

    def on_closing():
        state["final_bbox"] = None
        root.quit()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    map_widget.canvas.bind("<Button-3>", on_button_press)
    map_widget.canvas.bind("<B3-Motion>", on_mouse_drag)
    map_widget.canvas.bind("<ButtonRelease-3>", on_button_release)
    root.mainloop()
    root.withdraw() 
    if state["final_bbox"]: return state["final_bbox"], f"Selection_{round(state['final_bbox'][0], 4)}"
    return None, None

def fetch_bbox_safe(bbox, tags):
    try: return ox.features_from_bbox((bbox[3], bbox[1], bbox[2], bbox[0]), tags=tags)
    except TypeError: return ox.features_from_bbox(bbox[0], bbox[1], bbox[2], bbox[3], tags=tags)

def explore_available_tags(bbox):
    print("\n[?] Scouting available data tags in your referential area. This takes a few seconds...")
    available_categories = {}
    categories_to_check = ['building', 'highway', 'natural', 'leisure', 'landuse', 'waterway', 'amenity', 'public_transport']
    for cat in categories_to_check:
        try:
            data = fetch_bbox_safe(bbox, {cat: True})
            if not data.empty: available_categories[cat] = data[cat].value_counts().head(5).to_dict()
        except Exception: pass 
    print("\n--- AVAILABLE DATA FOUND ---")
    for cat, tags in available_categories.items():
        print(f"-> Category: '{cat}'")
        for tag, count in tags.items(): print(f"   - {tag} ({count} items)")
    return available_categories

def main():
    clear_screen()
    print("==================================================")
    print(" GeoAI Phase 1: Init & Vector Extraction")
    print("==================================================\n")

    # --- WEB HOOK ---
    if len(sys.argv) > 2:
        target_data = sys.argv[1]
        project_name = sys.argv[2]
        user_id = "Web_User"
        
        parts = target_data.split(',')
        if len(parts) == 4 and not any(c.isalpha() for c in target_data):
            bbox_raw = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
        else:
            bbox_raw, _ = get_bbox_from_text(target_data)

        if not bbox_raw:
            print("\n[X] Initialization aborted. Location not resolved.")
            sys.exit(1)
        selected_cats = 'all'

    # --- ORIGINAL TERMINAL MODE ---
    else:
        user_id = input("Enter User ID / Creator Name: ").strip()
        print("\nHow would you like to target your digital twin area?")
        print("  [1] Search by text")
        print("  [2] Select visually on a map")
        ui_choice = input("Choice (1/2): ").strip()
        bbox_raw, place_name = get_bbox_from_map() if ui_choice == '2' else get_bbox_from_text(input("\nEnter city/location: "))
        if not bbox_raw:
            print("\n[X] Initialization aborted. No area selected.")
            return
        custom_name = input(f"\nEnter Project Folder Name (Press Enter to use '{place_name}'): ").strip()
        project_name = custom_name.replace(" ", "_") if custom_name else place_name
        selected_cats = None 

    # --- SHARED PROCESSING LOGIC ---
    center_lat = (bbox_raw[0] + bbox_raw[1]) / 2
    center_lon = (bbox_raw[2] + bbox_raw[3]) / 2
    target_epsg = get_utm_epsg(center_lat, center_lon)

    print("\n[?] Adjusting selection to meet Dassault GEOVIA 1:1 metric aspect ratio...")
    bbox_squared, metric_bounds = force_perfect_square_and_metrics(bbox_raw, target_epsg)

    # --- NEW: HARD AREA LIMIT ---
    max_allowed_meters = 5000 # 3km max limit
    if metric_bounds['Side_Length_Meters'] > max_allowed_meters:
        print(f"\n[X] CRITICAL ERROR: Selected area ({metric_bounds['Side_Length_Meters']}m) is too large!")
        print(f"[X] Maximum allowed size is {max_allowed_meters}m to prevent server crashes.")
        sys.exit(1)

    os.makedirs(project_name, exist_ok=True)
    metadata = {
        "location": project_name.replace("_", " "),
        "created_by": user_id,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "epsg": target_epsg,
        "bbox": bbox_squared,           
        "referential_id": project_name,
        "bbox_metric_utm": metric_bounds 
    }
    
    with open(os.path.join(project_name, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=4)
        
    print(f"\n[OK] Project '{project_name}' Initialized.")
    print(f"[!] Target EPSG locked to: {target_epsg}")
    print(f"[!] GEOVIA Referential Limits Saved (Square Size: {metric_bounds['Side_Length_Meters']}m)")
    print(f"    Lower-Left (SW): X={metric_bounds['X_Min']}, Y={metric_bounds['Y_Min']}")
    print(f"    Upper-Right (NE): X={metric_bounds['X_Max']}, Y={metric_bounds['Y_Max']}")

    available = explore_available_tags(bbox_squared)
    if not available:
        print("[!] No usable vector data found in this bounding box."); return

    if selected_cats is None:
        selected_cats = input("\nWhat features to extract? (Comma separated, or Enter for all): ").strip().lower()
    
    targets = list(available.keys()) if selected_cats in ['', 'all'] else [c.strip() for c in selected_cats.split(',')]

    print(f"\n[?] Extracting pure WGS84 vector data...")
    for target in targets:
        try:
            data = fetch_bbox_safe(bbox_squared, {target: True})
            if not data.empty:
                clean_gdf = data.copy()
                for col in clean_gdf.columns:
                    if col != 'geometry': clean_gdf[col] = clean_gdf[col].astype(str)
                out_path = os.path.join(project_name, f"{target}.geojson")
                clean_gdf.to_file(out_path, driver="GeoJSON")
                print(f"  [OK] Saved {target}.geojson")
            
            # --- NEW: ANTI-BAN RATE LIMITING ---
            time.sleep(1.5) 
            
        except Exception as e: 
            print(f"  [X] Failed '{target}': {e}")
    print(f"\n[OK] Phase 1 Complete! Data safely deposited into ./{project_name}/")

    with open(".current_project.txt", "w") as f:
        f.write(project_name)

if __name__ == "__main__":
    main()