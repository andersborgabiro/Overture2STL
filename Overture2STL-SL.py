# TODO Separate bounding box for STL from bounding box for map (completely separate)

import os
import traceback

import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import Draw
from branca.element import MacroElement
from folium.template import Template

from libs.Overture2STL import (
    bbox_string,
    bbox_size_meters,
    map_types_default,
    map_types_all,
    overture_to_stl,
    validate_output_filename,
    make_session_dir,
    cleanup_old_cache_files,
    DEFAULT_GEOJSON_CACHE_DIR,
    DEFAULT_OUTPUT_ROOT_DIR,
    DEFAULT_CACHE_MAX_AGE_SECONDS,
    DEFAULT_AREA_WARNING_THRESHOLD_M2,
)

# Run once per browser session (i.e. on page load), not on every rerun
# triggered by widget interactions, since scanning the cache is unnecessary
# I/O to repeat on every click.
if "cache_cleanup_done" not in st.session_state:
    cleanup_old_cache_files(DEFAULT_GEOJSON_CACHE_DIR, DEFAULT_CACHE_MAX_AGE_SECONDS)
    st.session_state["cache_cleanup_done"] = True


# Must be called first
# TODO Consider layout="wide"
st.set_page_config(page_title="Overture to STL", page_icon="🗺", layout="centered", initial_sidebar_state="collapsed")

st.title("🗺 Overture to STL Generator")

# Styling got fixing height issue with Folium
custom_css = """
<style>
.map-container {
    height: 500px !important;
    width: 100%;
    overflow: hidden;
}
.map-container > * {
    height: 100% !important;
}
iframe {
    height: 500px !important;
}
</style>
"""

st.markdown(custom_css, unsafe_allow_html=True)

# Bounding Box
st.header("Bounding Box")

st.write(
    "Draw a rectangle on the map to select the area. You can zoom and pan as needed. Drawing a new rectangle replaces the previous one."
)

# Initialize session state for bbox
if "bbox" not in st.session_state:
    st.session_state["bbox"] = [13.133869, 55.675416, 13.267422, 55.744661]  # Lund, Sweden
bbox = st.session_state["bbox"]

# The map's initial location must never change across reruns: streamlit-folium
# fingerprints the map's own init script to decide whether to remount it, and
# any change (e.g. re-centering on the freshly drawn bbox) makes it look like
# a different map and forces a full remount, wiping any drawn shapes. So this
# is computed once and frozen. There's no need to feed the user's live pan/zoom
# back into the map afterwards: as long as it isn't remounted, the browser-side
# Leaflet map keeps its own view state on its own between reruns. (Doing so was
# tried and reverted: the center computed from returned bounds is a flat
# lat/lng average, which isn't quite the same point Leaflet reports as the
# true center under its Mercator projection, so re-applying it every rerun
# made the map nudge itself, re-triggering another rerun in an endless loop.)
if "initial_view" not in st.session_state:
    st.session_state["initial_view"] = {
        "center": [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2],
        "zoom": 14,
    }
initial_view = st.session_state["initial_view"]

m = folium.Map(
    location=initial_view["center"],
    zoom_start=initial_view["zoom"],
    tiles="OpenStreetMap",
    width="100%",
    height=500,
)

Draw(
    export=False,
    draw_options={
        "polyline": False,
        "polygon": False,
        "circle": False,
        "marker": False,
        "circlemarker": False,
        "rectangle": True,
    },
    edit_options={"edit": True, "remove": True},
).add_to(m)


# Force a single rectangle: whenever a new one is drawn, remove any other
# shapes from the Draw plugin's own layer group so only the latest remains.
# streamlit-folium renames the map and the Draw plugin's layer group to the
# fixed names "map_div" and "drawnItems" in the script it sends to the
# browser, so this must be added as a real script-macro child of the map
# (not injected as raw HTML) and reference those fixed names directly.
class SingleRectangleEnforcer(MacroElement):
    _template = Template(
        """
        {% macro script(this, kwargs) %}
        map_div.on('draw:created', function (e) {
            drawnItems.eachLayer(function (layer) {
                if (layer !== e.layer) {
                    drawnItems.removeLayer(layer);
                }
            });
        });
        {% endmacro %}
        """
    )


SingleRectangleEnforcer().add_to(m)

map_data = st_folium(m, height=500, width="100%")

#st.write(map_data)

# If a rectangle was drawn, use that as a bounding box
if map_data and map_data.get("last_active_drawing"):
    coords = map_data["last_active_drawing"]["geometry"]["coordinates"][0]
    lons = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    st.session_state["bbox"] = bbox

bbox_csv = bbox_string(bbox)
width_m, height_m = bbox_size_meters(bbox)
st.info(
    f"Bounding box: {bbox_csv}  \n"
    f"The dimensions of the area are roughly {round(width_m, 0)} m wide and {round(height_m, 0)} m high. Take this into account when editing object dimensions and scaling."
)

# Map Types
st.header("Map Types")
selected_types = []
cols = st.columns(3)
for i, t in enumerate(map_types_all):
    checked = t in map_types_default
    with cols[i % 3]:
        if st.checkbox(t, value=checked, key=f"maptype_{t}"):
            selected_types.append(t)

# Height Mode
st.header("Height Mode")
height_mode = st.selectbox(
    "Mode for use of the height settings below:",
    [
        ("f", "Fixed"),
        ("l", "Lowest allowed, otherwise explicit"),
        ("h", "Highest allowed, otherwise explicit"),
        ("e", "Explicit"),
    ],
    format_func=lambda x: x[1],
    index=3,
)
polygon_height_mode = height_mode[0]

# --- Numerical Parameters ---
st.header("Model Parameters")

col1, col2, col3 = st.columns(3)

with col1:
    polygon_height = st.number_input(
        "Default/limit height for buildings (m)",
        min_value=0.0,
        value=3.0,
        step=0.1,
    )
    polygon_height_flat = st.number_input(
        "Default/limit height for flat areas (m)",
        min_value=0.0,
        value=1.0,
        step=0.1,
    )
    line_width = st.number_input(
        "Default/limit width for lines (m)",
        min_value=0.0,
        value=3.0,
        step=0.1,
    )
with col2:
    line_height = st.number_input(
        "Default/limit height for lines (m)",
        min_value=0.0,
        value=2.0,
        step=0.1,
    )
    point_width = st.number_input(
        "Default width for points (m)",
        min_value=0.0,
        value=4.0,
        step=0.1,
    )
    point_height = st.number_input(
        "Default height for points (m)",
        min_value=0.0,
        value=4.0,
        step=0.1,
    )
with col3:
    scale_percent = st.number_input(
        "Scaling factor (%)",
        min_value=0.1,
        value=100.0,
        step=1.0,
    )
    base_height = st.number_input(
        "Base height (mm)",
        min_value=0.0,
        value=2.0,
        step=0.1,
    )
    base_margin = st.number_input(
        "Base margin (mm)",
        min_value=0.0,
        value=5.0,
        step=0.1,
    )

# --- Output File ---

st.header("Output")
outputfile = st.text_input(
    "File name for generated files (without extension)", value=""
)

if "perform" in st.session_state and st.session_state["perform"]:
    with st.status("Generating STL...", expanded=True) as status:
        try:
            session_dir = make_session_dir(DEFAULT_OUTPUT_ROOT_DIR)
            output_stl_path = os.path.join(session_dir, outputfile)

            overture_to_stl(
                bbox,
                selected_types,
                polygon_height_mode,
                polygon_height,
                polygon_height_flat,
                line_width,
                line_height,
                point_width,
                point_height,
                scale_percent,
                base_margin,
                base_height,
                output_stl_path,
                progress_callback=status.write,
            )

            with open(f"{output_stl_path}.stl", "rb") as stl_file:
                # Stored in session_state (not just rendered here) because
                # st.download_button triggers its own rerun when clicked, and
                # that rerun no longer has "perform" set, so a button rendered
                # only inside this block would disappear on the very click
                # meant to use it.
                st.session_state["last_stl"] = {
                    "filename": f"{outputfile}.stl",
                    "data": stl_file.read(),
                }

            status.update(label="STL generated successfully", state="complete", expanded=False)
            st.success(f"'{outputfile}.stl' was generated successfully (saved under '{session_dir}').")
        except OSError as e:
            status.update(label="STL generation failed", state="error")
            st.error(
                f"Could not write output files for '{outputfile}': {e}\n\n"
                "Check that the file name is valid and that you have write access to the working directory."
            )
        except ValueError as e:
            status.update(label="STL generation failed", state="error")
            st.error(
                f"No usable data to build from: {e}\n\n"
                "Try a larger bounding box, a different combination of map types, "
                "or verify that Overture data is available for this area."
            )
        except RuntimeError as e:
            status.update(label="STL generation failed", state="error")
            st.error(f"Mesh generation failed: {e}")
        except Exception as e:
            status.update(label="STL generation failed", state="error")
            st.error(f"Something went wrong when generating the STL file: {e}")
            with st.expander("Show error details"):
                st.code(traceback.format_exc())

        st.session_state["perform"] = False

@st.dialog("Large area selected")
def confirm_large_area(area_m2):
    st.write(
        f"The selected area is approximately **{area_m2 / 1_000_000:.2f} km²** "
        f"({area_m2:,.0f} m²), above the recommended limit of "
        f"{DEFAULT_AREA_WARNING_THRESHOLD_M2 / 1_000_000:.1f} km². Generating an STL "
        "for an area this large can take a long time and use significant memory."
    )
    cancel_col, continue_col = st.columns(2)
    with cancel_col:
        if st.button("Cancel", use_container_width=True):
            st.rerun()
    with continue_col:
        if st.button("Continue", type="primary", use_container_width=True):
            st.session_state["perform"] = True
            st.rerun()


# --- Generate STL Button ---
if st.button("Generate STL"):
    filename_error = validate_output_filename(outputfile)
    if filename_error:
        st.error(filename_error)
    elif not bbox or len(bbox) != 4:
        st.error("Please select a bounding box on the map.")
    elif not selected_types:
        st.error("Please select at least one map type.")
    else:
        area_m2 = width_m * height_m
        if area_m2 > DEFAULT_AREA_WARNING_THRESHOLD_M2:
            confirm_large_area(area_m2)
        else:
            st.session_state["perform"] = True
            # The generation-check block above runs before this button in
            # script order, so without forcing an immediate rerun here, this
            # click's flag would only be picked up on the *next* unrelated
            # interaction (i.e. the button would seem to need two presses).
            st.rerun()

if "last_stl" in st.session_state:
    st.download_button(
        label=f"Download {st.session_state['last_stl']['filename']}",
        data=st.session_state["last_stl"]["data"],
        file_name=st.session_state["last_stl"]["filename"],
        mime="model/stl",
    )

st.caption("Powered by Overture2STL by Abiro 2026, licensed under the MIT License.")
