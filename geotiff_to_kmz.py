__author__ = "Matt Geiman"
__email__ = "matt@geiman.org"
__version__ = "0.1.2"

"""

geotiff_to_kmz.py

This script takes a root folder containing a tree of GeoTIFF files, and converts them into
KMZ files.  Currently, it will spawn several processes to take advantage of multi-core
processors (works, but needs some tweaking - probably should limit the number of cores used)

Run the script as follows:

python ./geotiff_to_kmz.py <input_folder> <output_folder>


TODO:
    * Limit cores used, maybe set with flag
        - Currently, CTRL-c doesn't always catch, hopefully limiting cores fixes
        this.  Kill Python manually if you need to stop.

REQUIREMENTS:
    * GDAL
    * Pillow

"""


import os
import sys
import shutil
import zipfile
import tempfile
from osgeo import gdal, osr
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image

def geotiff_to_png(tiff_path, png_path, zlevel=9):
    """
    Convert GeoTIFF to PNG using GDAL with maximum compression.
    """
    ds = gdal.Open(tiff_path)
    if ds is None:
        raise Exception(f"Unable to open input GeoTIFF: {tiff_path}")
    # Export to PNG using ZLEVEL=9 for highest compression
    gdal.Translate(
        png_path, ds,
        format='PNG',
        outputType=gdal.GDT_Byte,
        creationOptions=[f'ZLEVEL={zlevel}', 'NBITS=8']
    )
    ds = None

def quantize_png_with_pillow(png_path, colors=16):
    """
    Quantize PNG file to a palette (PNG-8) with Pillow, preserving alpha.
    Uses FASTOCTREE, which works with RGBA images.
    """
    img = Image.open(png_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    quantized = img.quantize(colors=colors, method=Image.FASTOCTREE, dither=Image.FLOYDSTEINBERG)
    quantized.save(png_path, optimize=True)

def get_geotiff_bounds(tiff_path):
    """
    Get the geographic bounds (north, south, east, west) of the GeoTIFF for KML overlay.
    Handles both projected (e.g. EPSG:3857) and geographic CRS.
    """
    ds = gdal.Open(tiff_path)
    gt = ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize

    # Compute coordinates of all 4 corners
    corners = [
        (gt[0], gt[3]),  # top-left
        (gt[0] + cols * gt[1], gt[3]),  # top-right
        (gt[0], gt[3] + rows * gt[5]),  # bottom-left
        (gt[0] + cols * gt[1], gt[3] + rows * gt[5]),  # bottom-right
    ]

    # Get projection and handle coordinate transformation if needed
    srs = osr.SpatialReference(wkt=ds.GetProjection())
    epsg = None
    if srs.IsProjected():
        try:
            epsg = srs.GetAuthorityCode(None)
        except:
            epsg = None

    latlons = []
    if epsg == "3857":
        # Convert from Web Mercator to WGS84
        srs_3857 = osr.SpatialReference()
        srs_3857.ImportFromEPSG(3857)
        srs_4326 = osr.SpatialReference()
        srs_4326.ImportFromEPSG(4326)
        ct = osr.CoordinateTransformation(srs_3857, srs_4326)
        for x, y in corners:
            lon, lat, _ = ct.TransformPoint(x, y)
            latlons.append((lon, lat))
    else:
        # Assume already in WGS84
        for x, y in corners:
            latlons.append((y, x))

    # Get min/max values for KML LatLonBox
    lats = [lat for lat, lon in latlons]
    lons = [lon for lat, lon in latlons]
    north = max(lats)
    south = min(lats)
    east = max(lons)
    west = min(lons)
    return north, south, east, west

def generate_kml(image_name, north, south, east, west, kml_path):
    """
    Generate a simple KML with a GroundOverlay referencing the PNG image.
    """
    kml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <GroundOverlay>
    <name>{image_name}</name>
    <Icon>
      <href>{image_name}</href>
    </Icon>
    <color>ffffffff</color>
    <LatLonBox>
      <north>{north}</north>
      <south>{south}</south>
      <east>{east}</east>
      <west>{west}</west>
    </LatLonBox>
  </GroundOverlay>
</kml>
'''
    with open(kml_path, 'w') as f:
        f.write(kml_content)

def create_kmz(kml_path, image_path, kmz_path):
    """
    Bundle the KML and PNG into a single KMZ file.
    """
    with zipfile.ZipFile(kmz_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(kml_path, arcname='doc.kml')
        zf.write(image_path, arcname=os.path.basename(image_path))

def cleanup_aux_xml(tif_path):
    """
    Clean up any leftover .aux.xml files that GDAL sometimes creates.
    """
    aux_xml = tif_path + '.aux.xml'
    if os.path.exists(aux_xml):
        try:
            os.remove(aux_xml)
        except Exception:
            pass
    # Also check for .tiff.aux.xml
    if tif_path.lower().endswith('.tif'):
        alt_aux_xml = tif_path[:-4] + '.tiff.aux.xml'
        if os.path.exists(alt_aux_xml):
            try:
                os.remove(alt_aux_xml)
            except Exception:
                pass

def convert_tif_to_kmz_task(args):
    """
    Main function for processing a single TIFF to KMZ.
    Called in parallel by the batch script.
    """
    tif_path, kmz_path = args
    base = os.path.splitext(os.path.basename(tif_path))[0]
    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = os.path.join(tmpdir, base + ".png")
        kml_path = os.path.join(tmpdir, "doc.kml")
        try:
            # Step 1: Convert to PNG (GDAL)
            geotiff_to_png(tif_path, png_path, zlevel=9)
            # Step 2: Quantize PNG to 16 colors with Pillow (retaining transparency)
            quantize_png_with_pillow(png_path, colors=256)
            # Step 3: Get bounds for KML overlay
            north, south, east, west = get_geotiff_bounds(tif_path)
            # Step 4: Generate the KML overlay
            generate_kml(os.path.basename(png_path), north, south, east, west, kml_path)
            # Step 5: Bundle into KMZ
            create_kmz(kml_path, png_path, kmz_path)
            result = (tif_path, "OK")
        except Exception as e:
            result = (tif_path, f"FAILED: {e}")
        finally:
            # Always clean up any .aux.xml files
            cleanup_aux_xml(tif_path)
        return result

def gather_tif_tasks(root_in, root_out):
    """
    Recursively walk the input directory and create a list of all TIFFs to process,
    along with their corresponding output KMZ paths in the new tree.
    """
    tasks = []
    for dirpath, dirnames, filenames in os.walk(root_in):
        rel_dir = os.path.relpath(dirpath, root_in)
        out_dir = os.path.join(root_out, rel_dir)
        os.makedirs(out_dir, exist_ok=True)

        for fname in filenames:
            if fname.lower().endswith('.tif') or fname.lower().endswith('.tiff'):
                tif_path = os.path.join(dirpath, fname)
                kmz_name = os.path.splitext(fname)[0] + ".kmz"
                kmz_path = os.path.join(out_dir, kmz_name)
                tasks.append((tif_path, kmz_path))
    return tasks

if __name__ == "__main__":
    # Usage check
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} input_root_folder output_root_folder")
        sys.exit(1)
    root_in = sys.argv[1]
    root_out = sys.argv[2]
    tasks = gather_tif_tasks(root_in, root_out)
    print(f"[+] Found {len(tasks)} GeoTIFF files to process.")

    # Process all tasks in parallel for speed
    with ProcessPoolExecutor() as executor:
        future_to_task = {executor.submit(convert_tif_to_kmz_task, task): task for task in tasks}
        for i, future in enumerate(as_completed(future_to_task), 1):
            tif_path, status = future.result()
            print(f"[{i}/{len(tasks)}] {tif_path}: {status}")

