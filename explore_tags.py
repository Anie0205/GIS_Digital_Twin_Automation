import osmnx as ox

place_name = "Shivajinagar, Bangalore"
print(f"Scouting available data tags in {place_name}...\n")

# A helper function to fetch a broad category and count the specific tags inside it
def explore_category(category_key):
    try:
        # Setting the value to True fetches ALL features that have this key
        data = ox.features_from_place(place_name, {category_key: True})
        
        print(f"--- '{category_key.upper()}' TAGS FOUND ---")
        # .value_counts() counts how many times each specific tag appears
        counts = data[category_key].value_counts()
        print(counts)
        print("-" * 30 + "\n")
        
    except ox._errors.InsufficientResponseError:
        print(f"--- No '{category_key}' tags found in this area. ---\n")
    except Exception as e:
        print(f"Error exploring '{category_key}': {e}\n")

# Let's explore the three main categories where parks, trees, and water usually hide
explore_category("leisure")
explore_category("landuse")
explore_category("natural")
