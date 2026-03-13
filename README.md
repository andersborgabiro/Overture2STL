# Overture2STL

A Python application that converts Overture map data to a cohesive STL model.

![IMG_20250511_093003-s](https://github.com/user-attachments/assets/c81e3633-2c0e-4e5e-a607-4f73b2dcbaba)

## Usage

This is working code, that has generated consistent results for me, but still early such, so expect some rough edges.

Install the dependencies listed in requirements.txt.

For Overture2STL-CLI:
- Start with "python Overture2STL-CLI.py"
- Use https://boundingbox.klokantech.com/ to select the area to generate an STL for. Select CSV for the output, that is then entered into Overture2STL-CLI.

For Overture2STL-CLI-SL:
- Start with "streamlit run Overture2STL-SL.py"
- This variant has an integrated map that you use to select your area of interest.

Downloading data takes a rather long time, but once downloaded for a certain area (based on the bounding box) the generated files will be re-used unless you delete them.

You adjust what types of data are included by adding to or removing from the Overture map types. See "Overture map types explained" for information about what they contain.

Some areas contain lots of more or less irrelevant points that Overture2Stl will render as small cylinders. To avoid them altogether set the point-related dimensions to 0.

Be aware that STLs are dimension-less. Overture2STL uses meters that all (?) slicers will treat as millimeters. Often that's good enough, but expect to have to scale down larger areas. Take that into account when you set the scaling factor and  different dimensions.

Experiment / Iterate :)!

## References

- [Overture Maps Foundation](https://overturemaps.org/)
- [Overture Maps Documentation](https://docs.overturemaps.org/)

## Attribution

Slightly modified source code from [Overture Maps CLI](https://github.com/OvertureMaps/overturemaps-py) is used (core.py and cli.py under libs).
