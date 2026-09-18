"""
Business Finder — Streamlit web app (free to host on Streamlit Community Cloud)

Enter a location + business type, get a list of matching businesses
using free OpenStreetMap data (Nominatim + Overpass API). No API key needed.
"""

import time
import pandas as pd
import requests
import streamlit as st

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "business-finder-streamlit-app/1.0"}

TYPE_MAP = {
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "coffee shop": [("amenity", "cafe")],
    "bar": [("amenity", "bar")],
    "pub": [("amenity", "pub")],
    "fast food": [("amenity", "fast_food")],
    "bakery": [("shop", "bakery")],
    "gym": [("leisure", "fitness_centre")],
    "fitness center": [("leisure", "fitness_centre")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "spa": [("leisure", "spa"), ("shop", "beauty")],
    "pharmacy": [("amenity", "pharmacy")],
    "chemist": [("amenity", "pharmacy")],
    "hospital": [("amenity", "hospital")],
    "clinic": [("amenity", "clinics")],
    "dentist": [("amenity", "dentist")],
    "doctor": [("amenity", "doctors")],
    "hotel": [("tourism", "hotel")],
    "lodge": [("tourism", "guest_house")],
    "supermarket": [("shop", "supermarket")],
    "grocery": [("shop", "supermarket"), ("shop", "grocery")],
    "mall": [("shop", "mall")],
    "clothing store": [("shop", "clothes")],
    "electronics store": [("shop", "electronics")],
    "bookstore": [("shop", "books")],
    "bank": [("amenity", "bank")],
    "atm": [("amenity", "atm")],
    "school": [("amenity", "school")],
    "college": [("amenity", "college")],
    "university": [("amenity", "university")],
    "petrol pump": [("amenity", "fuel")],
    "gas station": [("amenity", "fuel")],
    "car repair": [("shop", "car_repair")],
    "car wash": [("amenity", "car_wash")],
    "park": [("leisure", "park")],
    "movie theater": [("amenity", "cinema")],
    "cinema": [("amenity", "cinema")],
    "temple": [("amenity", "place_of_worship")],
    "church": [("amenity", "place_of_worship")],
    "mosque": [("amenity", "place_of_worship")],
    "post office": [("amenity", "post_office")],
    "police station": [("amenity", "police")],
    "veterinary": [("amenity", "veterinary")],
    "pet shop": [("shop", "pet")],
    "furniture store": [("shop", "furniture")],
    "hardware store": [("shop", "hardware")],
    "jewelry store": [("shop", "jewelry")],
    "laundry": [("shop", "laundry")],
    "real estate agency": [("office", "estate_agent")],
    "coworking space": [("office", "coworking")],
}


@st.cache_data(show_spinner=False, ttl=3600)
def geocode_location(location_text):
    params = {"q": location_text, "format": "json", "limit": 1}
    resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    top = results[0]
    south, north, west, east = map(float, top["boundingbox"])
    return {
        "display_name": top["display_name"],
        "south": south, "north": north, "west": west, "east": east,
    }


def build_overpass_query(bbox, business_type):
    bbox_str = f"{bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']}"
    key = business_type.strip().lower()
    tag_pairs = TYPE_MAP.get(key)

    clauses = []
    if tag_pairs:
        for tag_key, tag_val in tag_pairs:
            for kind in ("node", "way"):
                clauses.append(f'{kind}["{tag_key}"="{tag_val}"]({bbox_str});')
    else:
        safe_val = key.replace(" ", "_")
        for kind in ("node", "way"):
            clauses.append(f'{kind}["amenity"="{safe_val}"]({bbox_str});')
            clauses.append(f'{kind}["shop"="{safe_val}"]({bbox_str});')
            clauses.append(f'{kind}["name"~"{key}",i]({bbox_str});')

    return "[out:json][timeout:60];\n(\n  " + "\n  ".join(clauses) + "\n);\nout center tags;"


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_businesses(bbox, business_type):
    query = build_overpass_query(bbox, business_type)
    resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=90)
    resp.raise_for_status()
    return resp.json().get("elements", [])


def extract_row(el):
    tags = el.get("tags", {})
    name = tags.get("name", "Unnamed")
    addr_parts = [
        tags.get("addr:housenumber", ""), tags.get("addr:street", ""),
        tags.get("addr:suburb", ""), tags.get("addr:city", ""),
        tags.get("addr:postcode", ""),
    ]
    address = ", ".join([p for p in addr_parts if p]) or tags.get("addr:full", "")
    phone = tags.get("phone", tags.get("contact:phone", ""))
    website = tags.get("website", tags.get("contact:website", ""))
    hours = tags.get("opening_hours", "")
    category = (tags.get("amenity") or tags.get("shop") or tags.get("leisure")
                or tags.get("tourism") or tags.get("office") or "")
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    maps_link = f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else ""
    return {
        "Name": name, "Category": category, "Address": address,
        "Phone": phone, "Website": website, "Hours": hours,
        "Maps Link": maps_link,
    }


st.set_page_config(page_title="Business Finder", page_icon="🔎", layout="wide")
st.title("🔎 Free Business Finder")
st.caption("Powered by OpenStreetMap (Nominatim + Overpass) — no API key, no cost.")

col1, col2 = st.columns(2)
with col1:
    location = st.text_input("Location", placeholder="e.g. Indiranagar, Bangalore")
with col2:
    business_type = st.text_input("Business type", placeholder="e.g. restaurant, gym, pharmacy")

if st.button("Search", type="primary"):
    if not location or not business_type:
        st.warning("Please enter both a location and a business type.")
    else:
        with st.spinner(f"Looking up '{location}'..."):
            place = geocode_location(location)
        if not place:
            st.error("Could not find that location. Try adding city/state/country.")
        else:
            st.success(f"Found: {place['display_name']}")
            with st.spinner(f"Searching for '{business_type}' businesses..."):
                time.sleep(1)
                elements = fetch_businesses(place, business_type)

            if not elements:
                st.info("No results found. Try a broader location or different keyword.")
            else:
                rows = [extract_row(el) for el in elements]
                df = pd.DataFrame(rows).drop_duplicates(subset=["Name", "Address"])
                st.write(f"**{len(df)} unique businesses found**")
                st.dataframe(df, use_container_width=True, hide_index=True)
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("Download as CSV", csv, "business_results.csv", "text/csv")
