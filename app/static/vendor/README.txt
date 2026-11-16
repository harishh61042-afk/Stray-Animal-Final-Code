Optional offline copies of the front-end libraries
==================================================

By default PawConnect loads Bootstrap, Bootstrap Icons, Chart.js, Leaflet and the Inter font from public CDNs, so the
browser needs an internet connection. No account or API key is needed for any of them.

To use local copies instead (for example on a computer with a slow connection):

    python tools/download_vendor.py

then put  USE_LOCAL_VENDOR=1  in your .env file and restart PawConnect. The script fills this folder with:

    bootstrap/bootstrap.min.css
    bootstrap/bootstrap.bundle.min.js
    bootstrap-icons/bootstrap-icons.min.css
    bootstrap-icons/fonts/bootstrap-icons.woff2
    bootstrap-icons/fonts/bootstrap-icons.woff
    leaflet/leaflet.css
    leaflet/leaflet.js
    leaflet/images/layers.png, layers-2x.png, marker-icon.png, marker-icon-2x.png, marker-shadow.png
    chartjs/chart.umd.js

With local copies the Inter font is not used (the pages fall back to the system font). The map pictures
(OpenStreetMap tiles) always come from the internet; without a connection the map areas show a short notice
and every form still works with the address typed by hand.
