"""
Business Finder v2 — Streamlit web app (free to host on Streamlit Community Cloud)

Search for businesses across a neighborhood, city, or an entire state/region
using free OpenStreetMap data (Nominatim + Overpass API). No API key needed.

Key improvements over v1:
  - Uses actual administrative boundary polygons for large-area searches
    instead of a bounding box (much more accurate for states/regions).
  - Queries multiple free Overpass mirrors with automatic retry/failover.
  - Fetches once, then filters/sorts/paginates locally (no re-fetching
    the API on every UI interaction).
  - Multi-type search, map view, richer data fields, CSV/JSON/Excel export.
"""

import io
import time
import difflib
import requests
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
HEADERS = {"User-Agent": "business-finder-app/2.0 (personal/free use)"}

# tag_key, tag_value pairs per business type. Grouped by category purely
# for readability; the app flattens this into one lookup dict.
TYPE_MAP = {}


def _add(names, tags):
    for n in names:
        TYPE_MAP[n] = tags


_add(["restaurant"], [("amenity", "restaurant")])
_add(["cafe", "coffee shop"], [("amenity", "cafe")])
_add(["bar"], [("amenity", "bar")])
_add(["pub"], [("amenity", "pub")])
_add(["fast food"], [("amenity", "fast_food")])
_add(["ice cream shop"], [("amenity", "ice_cream")])
_add(["food court"], [("amenity", "food_court")])
_add(["nightclub"], [("amenity", "nightclub")])
_add(["biergarten"], [("amenity", "biergarten")])
_add(["bakery"], [("shop", "bakery")])
_add(["butcher"], [("shop", "butcher")])
_add(["deli"], [("shop", "deli")])
_add(["greengrocer", "vegetable shop"], [("shop", "greengrocer")])

_add(["hospital"], [("amenity", "hospital")])
_add(["clinic"], [("amenity", "clinics")])
_add(["dentist"], [("amenity", "dentist")])
_add(["doctor", "physician"], [("amenity", "doctors")])
_add(["pharmacy", "chemist"], [("amenity", "pharmacy")])
_add(["veterinary", "vet"], [("amenity", "veterinary")])
_add(["optician"], [("shop", "optician")])
_add(["physiotherapist"], [("healthcare", "physiotherapist")])

_add(["salon", "hair salon", "hairdresser"], [("shop", "hairdresser")])
_add(["beauty salon"], [("shop", "beauty")])
_add(["spa"], [("leisure", "spa")])
_add(["massage"], [("shop", "massage")])
_add(["tattoo parlor"], [("shop", "tattoo")])
_add(["nail salon"], [("shop", "beauty"), ("beauty", "nails")])

_add(["supermarket"], [("shop", "supermarket")])
_add(["grocery", "convenience store"], [("shop", "convenience")])
_add(["mall", "shopping mall"], [("shop", "mall")])
_add(["department store"], [("shop", "department_store")])
_add(["clothing store", "clothes shop"], [("shop", "clothes")])
_add(["shoe store"], [("shop", "shoes")])
_add(["jewelry store"], [("shop", "jewelry")])
_add(["electronics store"], [("shop", "electronics")])
_add(["mobile phone shop"], [("shop", "mobile_phone")])
_add(["bookstore"], [("shop", "books")])
_add(["stationery shop"], [("shop", "stationery")])
_add(["toy store"], [("shop", "toys")])
_add(["sports shop"], [("shop", "sports")])
_add(["bicycle shop"], [("shop", "bicycle")])
_add(["car dealership"], [("shop", "car")])
_add(["car repair", "auto repair", "mechanic"], [("shop", "car_repair")])
_add(["hardware store"], [("shop", "hardware")])
_add(["furniture store"], [("shop", "furniture")])
_add(["florist"], [("shop", "florist")])
_add(["pet shop"], [("shop", "pet")])
_add(["gift shop"], [("shop", "gift")])
_add(["second hand shop", "thrift store"], [("shop", "second_hand")])

_add(["bank"], [("amenity", "bank")])
_add(["atm"], [("amenity", "atm")])
_add(["money transfer", "money exchange"], [("amenity", "money_transfer")])
_add(["insurance agency"], [("office", "insurance")])

_add(["school"], [("amenity", "school")])
_add(["college"], [("amenity", "college")])
_add(["university"], [("amenity", "university")])
_add(["kindergarten", "preschool"], [("amenity", "kindergarten")])
_add(["driving school"], [("shop", "driving_school")])
_add(["language school"], [("office", "educational_institution")])

_add(["laundry", "laundromat"], [("shop", "laundry")])
_add(["dry cleaning"], [("shop", "dry_cleaning")])
_add(["travel agency"], [("shop", "travel_agency")])
_add(["real estate agency"], [("office", "estate_agent")])
_add(["lawyer", "law firm"], [("office", "lawyer")])
_add(["accountant"], [("office", "accountant")])
_add(["coworking space"], [("office", "coworking")])
_add(["print shop"], [("shop", "copyshop")])

_add(["hotel"], [("tourism", "hotel")])
_add(["guest house", "lodge"], [("tourism", "guest_house")])
_add(["hostel"], [("tourism", "hostel")])
_add(["motel"], [("tourism", "motel")])
_add(["campsite"], [("tourism", "camp_site")])

_add(["gas station", "petrol pump", "fuel station"], [("amenity", "fuel")])
_add(["car wash"], [("amenity", "car_wash")])
_add(["car rental"], [("amenity", "car_rental")])

_add(["cinema", "movie theater"], [("amenity", "cinema")])
_add(["theatre"], [("amenity", "theatre")])
_add(["museum"], [("tourism", "museum")])
_add(["art gallery"], [("tourism", "gallery")])
_add(["bowling alley"], [("leisure", "bowling_alley")])
_add(["casino"], [("amenity", "casino")])

_add(["gym", "fitness center"], [("leisure", "fitness_centre")])
_add(["park"], [("leisure", "park")])
_add(["sports center"], [("leisure", "sports_centre")])
_add(["swimming pool"], [("leisure", "swimming_pool")])
_add(["stadium"], [("leisure", "stadium")])

_add(["temple", "church", "mosque", "place of worship"],
     [("amenity", "place_of_worship")])

_add(["post office"], [("amenity", "post_office")])
_add(["police station"], [("amenity", "police")])
_add(["courthouse"], [("amenity", "courthouse")])
_add(["town hall"], [("amenity", "townhall")])
_add(["embassy"], [("office", "diplomatic")])

_add(["internet cafe"], [("amenity", "internet_cafe")])


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=3600)
def geocode_location(location_text):
    """Resolve a place name to either an OSM boundary area id (preferred
    for cities/regions/states) or a bounding box (fallback)."""
    params = {
        "q": location_text,
        "format": "json",
        "limit": 1,
        "polygon_geojson": 0,
    }
    resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None

    top = results[0]
    south, north, west, east = map(float, top["boundingbox"])
    info = {
        "display_name": top["display_name"],
        "south": south, "north": north, "west": west, "east": east,
        "area_id": None,
    }

    osm_type = top.get("osm_type")
    osm_id = top.get("osm_id")
    if osm_type == "relation" and osm_id:
        info["area_id"] = 3600000000 + int(osm_id)
    elif osm_type == "way" and osm_id:
        info["area_id"] = 2400000000 + int(osm_id)

    return info


def _resolve_types(selected_types, custom_types_text):
    """Turn UI selections into a list of (tag_key, tag_value) pairs to
    search for, plus a list of free-text fallback terms for anything
    not found in TYPE_MAP."""
    tag_pairs = []
    fallback_terms = []
    suggestions = []

    terms = list(selected_types)
    if custom_types_text:
        terms += [t.strip() for t in custom_types_text.split(",") if t.strip()]

    for term in terms:
        key = term.strip().lower()
        if key in TYPE_MAP:
            tag_pairs.extend(TYPE_MAP[key])
        else:
            fallback_terms.append(key)
            close = difflib.get_close_matches(key, TYPE_MAP.keys(), n=1, cutoff=0.6)
            if close:
                suggestions.append((key, close[0]))

    return tag_pairs, fallback_terms, suggestions


def build_overpass_query(place, tag_pairs, fallback_terms, max_results):
    if place.get("area_id"):
        scope_setup = f"area({place['area_id']})->.searchArea;"
        scope = "(area.searchArea)"
    else:
        bbox_str = f"{place['south']},{place['west']},{place['north']},{place['east']}"
        scope_setup = ""
        scope = f"({bbox_str})"

    clauses = []
    for tag_key, tag_val in tag_pairs:
        for kind in ("node", "way"):
            clauses.append(f'{kind}["{tag_key}"="{tag_val}"]{scope};')

    for term in fallback_terms:
        safe_val = term.replace(" ", "_")
        for kind in ("node", "way"):
            clauses.append(f'{kind}["amenity"="{safe_val}"]{scope};')
            clauses.append(f'{kind}["shop"="{safe_val}"]{scope};')
            clauses.append(f'{kind}["name"~"{term}",i]{scope};')

    body = "\n  ".join(clauses)
    query = (
        f"[out:json][timeout:180][maxsize:1073741824];\n"
        f"{scope_setup}\n"
        f"(\n  {body}\n);\n"
        f"out center tags {max_results};"
    )
    return query


def query_overpass(query, status_placeholder=None):
    """Try each free Overpass mirror in turn, with a couple of retries
    each, since these public servers are frequently overloaded."""
    last_error = None
    for mirror in OVERPASS_MIRRORS:
        for attempt in range(2):
            try:
                if status_placeholder:
                    status_placeholder.write(f"Querying {mirror.split('/')[2]} (attempt {attempt + 1})...")
                resp = requests.post(mirror, data={"data": query}, headers=HEADERS, timeout=120)
                if resp.status_code == 200:
                    return resp.json().get("elements", [])
                last_error = f"{mirror} returned HTTP {resp.status_code}"
            except requests.RequestException as e:
                last_error = f"{mirror} failed: {e}"
            time.sleep(2)
    raise RuntimeError(f"All Overpass mirrors failed. Last error: {last_error}")


def extract_row(el):
    tags = el.get("tags", {})
    name = tags.get("name", "Unnamed")

    addr_parts = [
        tags.get("addr:housenumber", ""), tags.get("addr:street", ""),
        tags.get("addr:suburb", ""), tags.get("addr:city", ""),
        tags.get("addr:state", ""), tags.get("addr:postcode", ""),
    ]
    address = ", ".join([p for p in addr_parts if p]) or tags.get("addr:full", "")

    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")

    return {
        "Name": name,
        "Category": (tags.get("amenity") or tags.get("shop") or tags.get("leisure")
                     or tags.get("tourism") or tags.get("office") or tags.get("healthcare") or ""),
        "Cuisine": tags.get("cuisine", ""),
        "Brand": tags.get("brand", ""),
        "Address": address,
        "Phone": tags.get("phone", tags.get("contact:phone", "")),
        "Email": tags.get("email", tags.get("contact:email", "")),
        "Website": tags.get("website", tags.get("contact:website", "")),
        "Facebook": tags.get("contact:facebook", ""),
        "Instagram": tags.get("contact:instagram", ""),
        "Opening Hours": tags.get("opening_hours", ""),
        "Wheelchair Access": tags.get("wheelchair", ""),
        "Latitude": lat,
        "Longitude": lon,
        "Maps Link": f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else "",
    }


def run_search(location, selected_types, custom_types_text, max_results, status_placeholder):
    place = geocode_location(location)
    if not place:
        return None, "Could not find that location. Try adding city/state/country.", []

    tag_pairs, fallback_terms, suggestions = _resolve_types(selected_types, custom_types_text)
    if not tag_pairs and not fallback_terms:
        return None, "Please select or enter at least one business type.", []

    query = build_overpass_query(place, tag_pairs, fallback_terms, max_results)
    elements = query_overpass(query, status_placeholder)

    rows = [extract_row(el) for el in elements]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["Name", "Address", "Latitude", "Longitude"])
    return {"place": place, "df": df}, None, suggestions


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Business Finder", page_icon="🔎", layout="wide")
st.title("🔎 Business Finder")
st.caption("Powered by free OpenStreetMap data (Nominatim + Overpass). Works for neighborhoods, cities, or whole states/regions.")

with st.sidebar:
    st.header("Search")
    location = st.text_input("Location", placeholder="e.g. Karnataka, India  or  Texas, USA")
    selected_types = st.multiselect("Business type(s)", sorted(TYPE_MAP.keys()))
    custom_types_text = st.text_input("Other type(s), comma-separated", placeholder="e.g. escape room, comic shop")
    max_results = st.slider("Max results", min_value=100, max_value=5000, value=1000, step=100,
                             help="Large regions can return thousands of results. Higher limits take longer and may time out on free servers.")
    search_clicked = st.button("Search", type="primary", use_container_width=True)
    st.caption("Tip: for very large regions, narrow the business type or lower max results if searches time out.")

if search_clicked:
    if not location:
        st.warning("Please enter a location.")
    else:
        status_placeholder = st.empty()
        with st.spinner("Searching..."):
            result, error, suggestions = run_search(
                location, selected_types, custom_types_text, max_results, status_placeholder
            )
        status_placeholder.empty()

        if error:
            st.error(error)
        else:
            st.session_state["result"] = result
            st.session_state["page"] = 0
            if suggestions:
                for term, close in suggestions:
                    st.info(f"'{term}' isn't a recognized type — used a free-text match instead. Did you mean **{close}**?")

# ---------------------------------------------------------------------------
# Results (persisted in session_state so filtering/sorting/paging doesn't
# re-fetch from the API)
# ---------------------------------------------------------------------------

if "result" in st.session_state:
    place = st.session_state["result"]["place"]
    df = st.session_state["result"]["df"]

    st.success(f"Area: {place['display_name']}")

    if df.empty:
        st.info("No results found. Try a broader area, a different type, or check spelling.")
    else:
        st.write(f"**{len(df)} unique businesses found**")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            categories = sorted([c for c in df["Category"].unique() if c])
            cat_filter = st.multiselect("Filter by category", categories)
        with col2:
            name_filter = st.text_input("Filter by name contains")
        with col3:
            phone_only = st.checkbox("Has phone only")
        with col4:
            website_only = st.checkbox("Has website only")

        sort_col, sort_dir = st.columns(2)
        with sort_col:
            sort_by = st.selectbox("Sort by", ["Name", "Category", "Address"])
        with sort_dir:
            ascending = st.radio("Order", ["Ascending", "Descending"], horizontal=True) == "Ascending"

        filtered = df.copy()
        if cat_filter:
            filtered = filtered[filtered["Category"].isin(cat_filter)]
        if name_filter:
            filtered = filtered[filtered["Name"].str.contains(name_filter, case=False, na=False)]
        if phone_only:
            filtered = filtered[filtered["Phone"].astype(bool)]
        if website_only:
            filtered = filtered[filtered["Website"].astype(bool)]
        filtered = filtered.sort_values(by=sort_by, ascending=ascending)

        st.write(f"Showing {len(filtered)} of {len(df)} results")

        tab_table, tab_map = st.tabs(["Table", "Map"])

        with tab_table:
            page_size = st.selectbox("Rows per page", [25, 50, 100, 200], index=1)
            total_pages = max(1, (len(filtered) - 1) // page_size + 1)
            page = st.session_state.get("page", 0)
            page = min(page, total_pages - 1)

            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.button("◀ Previous", disabled=page <= 0):
                    page -= 1
            with nav3:
                if st.button("Next ▶", disabled=page >= total_pages - 1):
                    page += 1
            with nav2:
                st.write(f"Page {page + 1} of {total_pages}")
            st.session_state["page"] = page

            start = page * page_size
            st.dataframe(
                filtered.iloc[start:start + page_size].drop(columns=["Latitude", "Longitude"]),
                use_container_width=True, hide_index=True,
            )

        with tab_map:
            map_df = filtered.dropna(subset=["Latitude", "Longitude"])
            if map_df.empty:
                st.info("No mappable coordinates in the current results.")
            else:
                st.map(map_df.rename(columns={"Latitude": "lat", "Longitude": "lon"})[["lat", "lon"]],
                       use_container_width=True)

        st.subheader("Export")
        exp1, exp2, exp3 = st.columns(3)
        with exp1:
            st.download_button("Download CSV", filtered.to_csv(index=False).encode("utf-8"),
                                "business_results.csv", "text/csv", use_container_width=True)
        with exp2:
            st.download_button("Download JSON", filtered.to_json(orient="records", indent=2),
                                "business_results.json", "application/json", use_container_width=True)
        with exp3:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                filtered.to_excel(writer, index=False, sheet_name="Businesses")
            st.download_button("Download Excel", buf.getvalue(), "business_results.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True)
else:
    st.info("Enter a location and business type(s) in the sidebar, then click Search.")
