# GeoTIFF to KMZ
A Python script to convert GeoTIFF images into KMZ Overlays.

This script takes a directory containing GeoTIFF images as input, and outputs a directory of matching KMZ Overlay files.  The resulting KMZ Overlay files can be used in applications such as Google Earth, ATAK, iTAK, etc.  The main use is to create overlays that can be used in both ATAK and iTAK.  Currently, ATAK natively supports GeoTIFF overlays, but iTAK does not.  Both platforms support KMZ overlays.  For an agency that needs to work with both platforms, data packages of the resulting KMZ files can be created and will work on either type of device.

# Why
GeoTIFFs have the benefit of great compression.  KMZs however only support JPEG or PNG as the image type (for the most part, some caveats here).  JPEG offers good compression, however they do not offer any transparency.  PNG offers transparency, however they are lossless and result in larger file sizes.  Transparency isn't absolutely necessary, but you can end up with black borders around your overlays if there is any transparent border that would normally be hidden in the GeoTIFF.  For aesthetic reasons, I prefer to use PNGs for the transparency support.  

This script attempts to minimize the file sizes of the resulting KMZs by compressing them as much as possible, and lowering the bit-depth and number of colors used.  The PNGs generated should be 8-bit and 256 colors.  In limited testing, there is minimal visual difference between the original GeoTIFFs and the resulting KMZs.  That being said, this was mainly created for, and tested on, blueprint overlays for buildings.  Since the blueprints don't contain a great deal of imagery, the difference with the original is acceptable.  YMMV.  If size isn't an issue, you can adjust the bit-depth and number of colors used.

# Requirements
* Python (Tested with version 3.13.3)
* GDAL
* Pillow

# Usage
```
python ./geotiff_to_kmz.py <input_directory> <output_directory>
```
The output directory tree will match the input directory tree.  So if you have a layout such as:

```
+---GeoTIFFs
    +---County_1
    ¦       County_1.tif
    ¦       
    +---County_2
    ¦       County_2.tif
    ¦       
    +---County_3
            County_3.tif
```
The output directory tree will look like:
```
+---KMZs
    +---County_1
    ¦       County_1.kmz
    ¦       
    +---County_2
    ¦       County_2.kmz
    ¦       
    +---County_3
            County_3.kmz
```
