import osmnx as ox
import os
import geopandas as gpd
import pandas as pd
import tkinter as tk
import tkintermapview
import json

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# --- NEW: Version-Agnostic Extraction Helper ---
def fetch_bbox_safe(bbox, tags):
    """Handles API signature changes between OSMnx v1.x and v2.x"""
    try:
        # Try OSMnx v2.0+ format: bbox=(west, south, east, north)
        return ox.features_from_bbox((bbox[3], bbox[1], bbox[2], bbox[0]), tags=tags)
    except TypeError:
        # Fallback to OSMnx v1.x format: north, south, east, west
        return ox.features_from_bbox(bbox[0], bbox[1], bbox[2], bbox[3], tags=tags)
# -----------------------------------------------

def get_bbox_from_text(query):
    print(f"\n[?] Searching OpenStreetMap for '{query}'...")
    try:
        gdf = ox.geocode_to_gdf(query)
        official_name = gdf.iloc[0]['display_name']
        bounds = gdf.total_bounds 
        bbox = (bounds[3], bounds[1], bounds[2], bounds[0]) # (north, south, east, west)
        print(f"[✓] Location found: {official_name}")
        return bbox, query
    except Exception:
        print(f"[X] Could not find exact boundaries for '{query}'.")
        return None, None

def get_bbox_from_map():
    state = {"start_lat_lon": None, "current_poly": None, "final_bbox": None}
    root = tk.Tk()
    root.geometry("800x600")
    root.title("GeoAI - Click and Drag to Select Area")

    label = tk.Label(root, text="Left-Click and DRAG to draw your extraction area", font=("Helvetica", 12, "bold"))
    label.pack(pady=10)

    map_widget = tkintermapview.TkinterMapView(root, width=800, height=500, corner_radius=0)
    map_widget.pack(fill="both", expand=True)

    map_widget.set_tile_server("https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=22)
    map_widget.set_position(12.9716, 77.5946) 
    map_widget.set_zoom(14)

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
        label.config(text="Area Locked! Close window to start extraction.", fg="green")

    map_widget.canvas.bind("<Button-1>", on_button_press)
    map_widget.canvas.bind("<B1-Motion>", on_mouse_drag)
    map_widget.canvas.bind("<ButtonRelease-1>", on_button_release)
    root.mainloop()

    if state["final_bbox"]:
        name = f"Selection_{round(state['final_bbox'][0], 4)}_{round(state['final_bbox'][3], 4)}"
        return state["final_bbox"], name
    return None, None

def explore_available_tags(bbox):
    print("\n[?] Scouting available data tags. This takes a few seconds...")
    available_categories = {}
    categories_to_check = ['building', 'highway', 'natural', 'leisure', 'landuse', 'waterway', 'amenity', 'public_transport']
    
    for cat in categories_to_check:
        try:
            # Replaced direct call with our new safe helper
            data = fetch_bbox_safe(bbox, {cat: True})
            if not data.empty:
                available_categories[cat] = data[cat].value_counts().head(5).to_dict()
        except ox._errors.InsufficientResponseError:
            pass # Ignore if simply no data exists (Normal)
        except Exception as e:
            print(f"   [!] System error checking {cat}: {e}") # Expose real errors
            
    print("\n--- AVAILABLE DATA FOUND ---")
    for cat, tags in available_categories.items():
        print(f"-> Category: '{cat}'")
        for tag, count in tags.items():
            print(f"   - {tag} ({count} items)")
    return available_categories

def main():
    clear_screen()
    print("=======================================")
    print(" GeoAI 2D Vector Master Pipeline")
    print("=======================================\n")

    print("How would you like to target your extraction area?")
    print("  [1] Search by text\n  [2] Select visually on a map")
    ui_choice = input("Choice (1/2): ").strip()

    bbox, place_name = get_bbox_from_map() if ui_choice == '2' else get_bbox_from_text(input("\nEnter city: "))
    if not bbox: return

    available = explore_available_tags(bbox)
    if not available:
        print("[!] No usable vector data found. Check your selection area."); return

    selected_cats = input("\nWhat features to extract? (Comma separated, or Enter for all): ").strip().lower()
    targets = list(available.keys()) if selected_cats in ['', 'all'] else [c.strip() for c in selected_cats.split(',')]

    merge_choice = input("\nCombine datasets or separate? (c/s): ").strip().lower()
    format_choice = input("Format: [1] .geojson [2] .shp [3] Both: ").strip()

    print(f"\n[?] Extracting and reprojecting data...")
    extracted_data = {}
    for target in targets:
        try:
            # Replaced direct call with our new safe helper here as well
            data = fetch_bbox_safe(bbox, {target: True})
            if not data.empty:
                data_projected = ox.projection.project_gdf(data)
                extracted_data[target] = data_projected
        except Exception as e: print(f"  -> Failed '{target}': {e}")

    if not extracted_data: return
    local_epsg = extracted_data[list(extracted_data.keys())[0]].crs.to_epsg()

    folder_name = place_name.replace(", ", "_").replace(" ", "_").replace("/", "_")
    os.makedirs(folder_name, exist_ok=True)

    with open(os.path.join(folder_name, "metadata.json"), "w") as f:
        json.dump({"location": place_name, "epsg": f"EPSG:{local_epsg}", "bbox": bbox}, f, indent=4)

    def save_gdf(gdf, filename):
        clean_gdf = gdf.copy()
        for col in clean_gdf.columns:
            if col != 'geometry': clean_gdf[col] = clean_gdf[col].astype(str)
        if format_choice in ['1', '3']: clean_gdf.to_file(os.path.join(folder_name, f"{filename}.geojson"), driver="GeoJSON")
        if format_choice in ['2', '3']:
            shp_dir = os.path.join(folder_name, filename)
            os.makedirs(shp_dir, exist_ok=True)
            clean_gdf.to_file(os.path.join(shp_dir, f"{filename}.shp"))

    if merge_choice == 'c':
        save_gdf(gpd.GeoDataFrame(pd.concat(extracted_data.values(), ignore_index=True)), "combined_data")
    else:
        for name, gdf in extracted_data.items(): save_gdf(gdf, name)

    print(f"\n[✓] Done! Files saved in: ./{folder_name}/")

if __name__ == "__main__":
    main()