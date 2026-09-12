import os
import sys
import traceback

from libs.Overture2STL import (
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

if __name__ == "__main__":
    cleanup_old_cache_files(DEFAULT_GEOJSON_CACHE_DIR, DEFAULT_CACHE_MAX_AGE_SECONDS)

    # Bounding box
    input_bbox = input(
        "Enter bounding box (long west, lat south, long east, lat north): "
    ).strip()
    try:
        bbox = [round(float(x.strip()), 6) for x in input_bbox.split(",")]
    except ValueError:
        print("Bounding box must be 4 comma-separated numbers.")
        sys.exit(1)
    if len(bbox) != 4:
        print(f"Bounding box must have exactly 4 comma-separated numbers (got {len(bbox)}).")
        sys.exit(1)

    width_m, height_m = bbox_size_meters(bbox)
    print(
        f"Given the provided bounding box, the dimensions of the area are roughly {round(width_m, 0)} m wide and {round(height_m, 0)} m high. Take this into account when editing object dimensions and scaling."
    )

    area_m2 = width_m * height_m
    if area_m2 > DEFAULT_AREA_WARNING_THRESHOLD_M2:
        confirm = input(
            f"This area is approximately {area_m2 / 1_000_000:.2f} km² "
            f"({area_m2:,.0f} m²), above the recommended limit of "
            f"{DEFAULT_AREA_WARNING_THRESHOLD_M2 / 1_000_000:.1f} km². "
            "Generating an STL for an area this large can take a long time "
            "and use significant memory. Continue? [y/N]: "
        ).strip().lower()
        if confirm != "y":
            print("Cancelled.")
            sys.exit(0)

    # Overture types
    types_list = ", ".join(map_types_default)
    overture_types_input = input(
        f"Comma-separated Overture map types to download ({types_list}): "
    ).strip()
    if overture_types_input != "":
        overture_types = [
            t.strip()
            for t in overture_types_input.split(",")
            if t.strip() and t.strip() in map_types_all
        ]
    else:
        overture_types = map_types_default

    # Polygon height mode
    polygon_height_mode_default = "e"
    input_height_mode = input(
        "Mode for use of the height settings below: f(ixed), l(owest), h(ighest), e(xplicit) (e): "
    ).strip()
    polygon_height_mode = (
        input_height_mode.strip().lower()[0]
        if len(input_height_mode) > 0
        else polygon_height_mode_default
    )
    if polygon_height_mode not in ["f", "l", "h", "e"]:
        polygon_height_mode = polygon_height_mode_default

    # Polygon height for generic use
    polygon_height_default = 3.0
    input_height = input(
        f"Default or limit height for buildings ({polygon_height_default} m): "
    ).strip()
    polygon_height = (
        float(input_height) if input_height != "" else polygon_height_default
    )

    # Polygon height for flat surfaces
    polygon_height_flat_default = 1.0
    input_height_flat = input(
        f"Default or limit height for flat areas ({polygon_height_flat_default} m): "
    ).strip()
    polygon_height_flat = (
        float(input_height_flat)
        if input_height_flat != ""
        else polygon_height_flat_default
    )

    # Line width
    line_width_default = 3.0
    input_line_width = input(
        f"Default or limit width for lines ({line_width_default} m): "
    ).strip()
    line_width = (
        float(input_line_width) if input_line_width != "" else line_width_default
    )

    # Line height
    line_height_default = 2.0
    input_line_height = input(
        f"Default or limit height for lines ({line_height_default} m): "
    ).strip()
    line_height = (
        float(input_line_height) if input_line_height != "" else line_height_default
    )

    # Point width/diameter
    point_width_default = 4.0
    input_point_width = input(
        f"Default width for points ({point_width_default} m): "
    ).strip()
    point_width = (
        float(input_point_width) if input_point_width != "" else point_width_default
    )

    # Point height
    point_height_default = 4.0
    input_point_height = input(
        f"Default height for points ({point_height_default} m): "
    ).strip()
    point_height = (
        float(input_point_height) if input_point_height != "" else point_height_default
    )

    # Scaling factor
    scale_percent_default = 100.0
    input_scale_percent = input(
        f"Scaling factor in percent ({scale_percent_default}%): "
    ).strip()
    scale_percent = (
        float(input_scale_percent)
        if input_scale_percent != ""
        else scale_percent_default
    )

    # Base height
    base_height_default = 2.0
    input_base_height = input(f"Base height ({base_height_default} mm): ").strip()
    base_height = (
        float(input_base_height) if input_base_height != "" else base_height_default
    )

    # Base margin
    base_margin_default = 5.0
    input_base_margin = input(f"Base margin ({base_margin_default} mm): ").strip()
    base_margin = (
        float(input_base_margin) if input_base_margin != "" else base_margin_default
    )

    # File name for STL and GeoJSON files
    input_outputfile = input(
        "File name for generated files without extension: "
    ).strip()

    filename_error = validate_output_filename(input_outputfile)
    if filename_error:
        print(filename_error)
        sys.exit(1)

    try:
        session_dir = make_session_dir(DEFAULT_OUTPUT_ROOT_DIR)
        output_stl_path = os.path.join(session_dir, input_outputfile)

        overture_to_stl(
            bbox,
            overture_types,
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
        )
        print(f"'{input_outputfile}.stl' was generated successfully (saved under '{session_dir}').")
    except OSError as e:
        print(
            f"Could not write output files for '{input_outputfile}': {e}\n"
            "Check that the file name is valid and that you have write access to the working directory."
        )
        sys.exit(1)
    except ValueError as e:
        print(
            f"No usable data to build from: {e}\n"
            "Try a larger bounding box, a different combination of map types, "
            "or verify that Overture data is available for this area."
        )
        sys.exit(1)
    except RuntimeError as e:
        print(f"Mesh generation failed: {e}")
        sys.exit(1)
    except Exception:
        print("Something went wrong when generating the STL file:")
        traceback.print_exc()
        sys.exit(1)
