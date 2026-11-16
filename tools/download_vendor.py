#!/usr/bin/env python3
"""Download the front-end libraries into app/static/vendor so the web pages work without the public CDNs.

    python tools/download_vendor.py            download what is missing
    python tools/download_vendor.py --force    download everything again

Afterwards put  USE_LOCAL_VENDOR=1  in your .env file and restart PawConnect.
You need an internet connection once, while this script runs. Only the Python standard library is used.
The map pictures (OpenStreetMap tiles) are always loaded from the internet, whatever this setting says.
"""
import sys
import urllib.error
import urllib.request
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "app" / "static" / "vendor"

# The versions are the same ones the pages load from the CDNs (see CDN in app/template_utils.py).
BOOTSTRAP = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist"
ICONS = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font"
LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist"
CHARTJS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist"

FILES = {  # path inside app/static/vendor -> where it comes from
    "bootstrap/bootstrap.min.css": f"{BOOTSTRAP}/css/bootstrap.min.css",
    "bootstrap/bootstrap.bundle.min.js": f"{BOOTSTRAP}/js/bootstrap.bundle.min.js",
    "bootstrap-icons/bootstrap-icons.min.css": f"{ICONS}/bootstrap-icons.min.css",
    "bootstrap-icons/fonts/bootstrap-icons.woff2": f"{ICONS}/fonts/bootstrap-icons.woff2",
    "bootstrap-icons/fonts/bootstrap-icons.woff": f"{ICONS}/fonts/bootstrap-icons.woff",
    "leaflet/leaflet.css": f"{LEAFLET}/leaflet.css",
    "leaflet/leaflet.js": f"{LEAFLET}/leaflet.js",
    "leaflet/images/layers.png": f"{LEAFLET}/images/layers.png",
    "leaflet/images/layers-2x.png": f"{LEAFLET}/images/layers-2x.png",
    "leaflet/images/marker-icon.png": f"{LEAFLET}/images/marker-icon.png",
    "leaflet/images/marker-icon-2x.png": f"{LEAFLET}/images/marker-icon-2x.png",
    "leaflet/images/marker-shadow.png": f"{LEAFLET}/images/marker-shadow.png",
    "chartjs/chart.umd.js": f"{CHARTJS}/chart.umd.js",
}


def download(address, target):
    """Fetch ``address`` and save it as ``target``. Raises OSError / URLError on failure."""
    request = urllib.request.Request(address, headers={"User-Agent": "PawConnect-vendor-download"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data:
        raise OSError("the server sent an empty file")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def main(argv):
    force = "--force" in argv
    failed = []
    for relative, address in FILES.items():
        target = VENDOR / relative
        if target.exists() and target.stat().st_size > 0 and not force:
            print(f"  already there  {relative}")
            continue
        try:
            download(address, target)
            print(f"  downloaded     {relative}")
        except (OSError, urllib.error.URLError) as error:  # URLError is an OSError, listed for readers
            failed.append(relative)
            print(f"  FAILED         {relative}  ({error})")
    if failed:
        print(f"\n{len(failed)} file(s) could not be downloaded. Check your internet connection and run this again.")
        return 1
    print("\nDone. Now put  USE_LOCAL_VENDOR=1  in your .env file and restart PawConnect.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
