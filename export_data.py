import osmnx as ox
import os

place_name = "Shivajinagar, Bangalore"

# 1. Create a folder to hold our exported datasets
output_folder = "city_data"
os.makedirs(output_folder, exist_ok=True)

print(f"Extracting datasets for {place_name}...")

# 2. Fetch the different layers
print("- Downloading buildings...")
buildings = ox.features_from_place(place_name, {"building": True})

print("- Downloading waterways...")
water = ox.features_from_place(place_name, {"waterway": True, "natural": "water"})

print("- Downloading parks (Polygons)...")
parks = ox.features_from_place(place_name, {"leisure": "park"})

print("- Downloading individual trees (Points)...")
trees = ox.features_from_place(place_name, {"natural": "tree"})

# Group them in a list to loop through for saving
datasets = {
    "buildings": buildings,
    "water": water,
    "parks": parks,
    "trees": trees
}

print("\nSaving files to GeoJSON and Shapefile formats...")

# 3. Save the data
for name, data in datasets.items():
    if data.empty:
        print(f"Skipping {name} (No data found).")
        continue

    # -- SAVE AS GEOJSON --
    # GeoJSON is perfect for web apps, Digital Twins, and modern AI pipelines.
    geojson_path = os.path.join(output_folder, f"{name}.geojson")
    data.to_file(geojson_path, driver="GeoJSON")
    print(f"Saved: {geojson_path}")

    # -- SAVE AS SHAPEFILE --
    # Shapefiles are strict. They crash if attributes contain Python lists, 
    # so we must convert all text/data columns into plain strings first.
    shp_path = os.path.join(output_folder, name)
    os.makedirs(shp_path, exist_ok=True) # Shapefiles actually create 4-5 files, so we put them in a subfolder
    
    clean_data = data.copy()
    for col in clean_data.columns:
        if col != 'geometry':  # Keep the math shapes, convert everything else to text
            clean_data[col] = clean_data[col].astype(str)
            
    # Shapefiles also enforce a 10-character limit on column names, 
    # so GeoPandas will automatically truncate longer names (e.g., 'building:levels' -> 'building:l')
    try:
        clean_data.to_file(os.path.join(shp_path, f"{name}.shp"))
        print(f"Saved: {name}.shp")
    except Exception as e:
        print(f"Warning: Could not save Shapefile for {name}. Error: {e}")

print("\nExtraction complete! Check the 'city_data' folder.")