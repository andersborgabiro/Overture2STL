import functools
from typing import Optional

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs


def record_batch_reader(overture_type, bbox=None) -> Optional[pa.RecordBatchReader]:
    """
    Return a pyarrow RecordBatchReader for the desired bounding box and s3 path
    """
    path = _dataset_path(overture_type)

    if bbox:
        xmin, ymin, xmax, ymax = bbox
        filter = (
            (pc.field("bbox", "xmin") < xmax)
            & (pc.field("bbox", "xmax") > xmin)
            & (pc.field("bbox", "ymin") < ymax)
            & (pc.field("bbox", "ymax") > ymin)
        )
    else:
        filter = None

    dataset = ds.dataset(
        path, filesystem=fs.S3FileSystem(anonymous=True, region="us-west-2")
    )
    batches = dataset.to_batches(filter=filter)

    # to_batches() can yield many batches with no rows. I've seen
    # this cause downstream crashes or other negative effects. For
    # example, the ParquetWriter will emit an empty row group for
    # each one bloating the size of a parquet file. Just omit
    # them so the RecordBatchReader only has non-empty ones. Use
    # the generator syntax so the batches are streamed out
    non_empty_batches = (b for b in batches if b.num_rows > 0)

    geoarrow_schema = geoarrow_schema_adapter(dataset.schema)
    reader = pa.RecordBatchReader.from_batches(geoarrow_schema, non_empty_batches)
    return reader


def geoarrow_schema_adapter(schema: pa.Schema) -> pa.Schema:
    """
    Convert a geoarrow-compatible schema to a proper geoarrow schema

    This assumes there is a single "geometry" column with WKB formatting

    Parameters
    ----------
    schema: pa.Schema

    Returns
    -------
    pa.Schema
    A copy of the input schema with the geometry field replaced with
    a new one with the proper geoarrow ARROW:extension metadata

    """
    geometry_field_index = schema.get_field_index("geometry")
    geometry_field = schema.field(geometry_field_index)
    geoarrow_geometry_field = geometry_field.with_metadata(
        {b"ARROW:extension:name": b"geoarrow.wkb"}
    )

    geoarrow_schema = schema.set(geometry_field_index, geoarrow_geometry_field)

    return geoarrow_schema


type_theme_map = {
    "address": "addresses",
    "bathymetry": "base",
    "building": "buildings",
    "building_part": "buildings",
    "division": "divisions",
    "division_area": "divisions",
    "division_boundary": "divisions",
    "place": "places",
    "segment": "transportation",
    "connector": "transportation",
    "infrastructure": "base",
    "land": "base",
    "land_cover": "base",
    "land_use": "base",
    "water": "base",
}


# Last known-good release, used only as a fallback if the release listing
# below ever fails (e.g. the S3 "list" API is unreachable while "get" still
# works). Safe to leave stale since it's not the normal code path.
_FALLBACK_RELEASE = "2026-07-22.0"


@functools.lru_cache(maxsize=1)
def _latest_release() -> str:
    """
    Discover the most recent Overture release folder available in the public
    S3 bucket (releases are published as top-level "release/<date>.<n>/"
    prefixes), so this doesn't need to be hardcoded and bumped by hand every
    time Overture publishes a new one. Cached for the life of the process,
    since it doesn't change during a single run and every call would
    otherwise re-list the bucket.
    """
    try:
        s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")
        infos = s3.get_file_info(
            fs.FileSelector("overturemaps-us-west-2/release", recursive=False)
        )
        releases = [
            info.path.rsplit("/", 1)[-1]
            for info in infos
            if info.type == fs.FileType.Directory
        ]
        if not releases:
            raise RuntimeError("No release folders found in the S3 bucket.")

        def sort_key(release_name):
            date_part, _, minor_part = release_name.partition(".")
            return (date_part, int(minor_part) if minor_part.isdigit() else 0)

        return max(releases, key=sort_key)
    except Exception as e:
        print(f"Could not determine latest Overture release, falling back to "
              f"'{_FALLBACK_RELEASE}': {e}")
        return _FALLBACK_RELEASE


def _dataset_path(overture_type: str) -> str:
    """
    Returns the s3 path of the Overture dataset to use. This assumes overture_type has
    been validated, e.g. by the CLI

    """
    # Map of sub-partition "type" to parent partition "theme" for forming the
    # complete s3 path. Could be discovered by reading from the top-level s3
    # location but this allows to only read the files in the necessary partition.
    theme = type_theme_map[overture_type]
    release = _latest_release()
    return f"overturemaps-us-west-2/release/{release}/theme={theme}/type={overture_type}/"
