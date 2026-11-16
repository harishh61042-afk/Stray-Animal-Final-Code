/* PawConnect maps - Leaflet + OpenStreetMap tiles (free, no API key).
   Load Leaflet first (macros: ui.map_head() / ui.map_scripts()), then call:

   PawMap.viewer({ id: 'map', markers: [{lat, lng, title, subtitle, url, level, color, icon}], zoom: 13 })
   PawMap.picker({ id: 'map', latInput: 'id_latitude', lngInput: 'id_longitude',
                   locateButton: 'locate-btn', statusEl: 'geo-status' })

   Everything degrades gracefully: when Leaflet or the map tiles cannot be loaded the page shows a short notice and
   the rest of the form / list keeps working (coordinates can always be typed in). */
(function () {
  'use strict';

  var DEFAULT_CENTER = [20.5937, 78.9629]; // India (used until the user picks a place)
  var LEVEL_COLORS = { Critical: '#e5484d', High: '#f59f00', Medium: '#3b82f6', Low: '#1f9d63' };
  var TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  var ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';

  function byId(idOrEl) { return typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl; }

  function notice(id, text) {
    var el = document.querySelector('[data-map-notice="' + id + '"]');
    if (!el) { return; }
    if (text) { el.textContent = text; el.hidden = false; } else { el.hidden = true; }
  }

  function validLat(v) { return typeof v === 'number' && isFinite(v) && v >= -90 && v <= 90; }
  function validLng(v) { return typeof v === 'number' && isFinite(v) && v >= -180 && v <= 180; }
  function toNumber(value) {
    if (value === null || value === undefined || String(value).trim() === '') { return NaN; }
    return Number(value);
  }

  function pinIcon(color, iconClass) {
    return window.L.divIcon({
      className: 'pc-marker',
      html: '<span style="--c:' + color + '"><i class="bi ' + (iconClass || 'bi-geo-alt-fill') + '"></i></span>',
      iconSize: [34, 34],
      iconAnchor: [17, 42],
      popupAnchor: [0, -38]
    });
  }

  function createMap(id, center, zoom) {
    var container = byId(id);
    if (!container) { return null; }
    if (typeof window.L === 'undefined') {
      notice(typeof id === 'string' ? id : container.id, 'The map could not be loaded (check your internet connection). Everything else on this page still works.');
      return null;
    }
    var map = window.L.map(container, { scrollWheelZoom: false }).setView(center || DEFAULT_CENTER, zoom || 5);
    var failures = 0;
    var layer = window.L.tileLayer(TILE_URL, { maxZoom: 19, attribution: ATTRIBUTION });
    layer.on('tileerror', function () {
      failures += 1;
      if (failures === 3) {
        notice(container.id, 'Map pictures could not be downloaded (no internet connection?). Locations are still saved and listed on this page.');
      }
    });
    layer.on('load', function () { if (failures < 3) { notice(container.id, ''); } });
    layer.addTo(map);
    // wheel zoom only after the map was clicked, so the page can still be scrolled
    map.on('focus', function () { map.scrollWheelZoom.enable(); });
    map.on('blur', function () { map.scrollWheelZoom.disable(); });
    window.setTimeout(function () { map.invalidateSize(); }, 250);
    return map;
  }

  function popupNode(m) {
    var box = document.createElement('div');
    if (m.title) {
      var title = document.createElement('div');
      title.className = 'pc-popup-title';
      title.textContent = m.title;
      box.appendChild(title);
    }
    if (m.subtitle) {
      var sub = document.createElement('div');
      sub.textContent = m.subtitle;
      box.appendChild(sub);
    }
    if (m.url) {
      var link = document.createElement('a');
      link.href = m.url;
      link.textContent = m.linkLabel || 'View details';
      link.className = 'fw-semibold d-inline-block mt-1';
      box.appendChild(link);
    }
    return box;
  }

  /* ----------------------------------------------------------- viewer */
  function viewer(options) {
    var markers = (options.markers || []).filter(function (m) { return validLat(Number(m.lat)) && validLng(Number(m.lng)); });
    var container = byId(options.id);
    if (!container) { return null; }
    if (!markers.length) {
      notice(container.id, options.emptyText || 'No locations to show on the map yet.');
    }
    var first = markers[0];
    var map = createMap(options.id, first ? [Number(first.lat), Number(first.lng)] : (options.center || DEFAULT_CENTER), options.zoom || (first ? 13 : 5));
    if (!map) { return null; }
    var bounds = [];
    markers.forEach(function (m) {
      var color = m.color || LEVEL_COLORS[m.level] || '#1f9d63';
      var point = [Number(m.lat), Number(m.lng)];
      bounds.push(point);
      var marker = window.L.marker(point, { icon: pinIcon(color, m.icon), title: m.title || '' }).addTo(map);
      if (m.title || m.subtitle || m.url) { marker.bindPopup(popupNode(m)); }
    });
    if (bounds.length > 1 && options.fitBounds !== false) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 15 });
    }
    return map;
  }

  /* ------------------------------------------------------------- live */
  // A map whose pins can be replaced later (the rescue map refreshes itself every minute).
  //   var map = PawMap.live({ id: 'map', markers: [...] });  map.update(newMarkers);
  function live(options) {
    var container = byId(options.id);
    if (!container) { return null; }
    var map = createMap(options.id, options.center || DEFAULT_CENTER, options.zoom || 5);
    if (!map) { return null; }
    var layer = window.L.layerGroup().addTo(map);
    var fitted = false;

    function update(markers, fit) {
      layer.clearLayers();
      var bounds = [];
      (markers || []).forEach(function (m) {
        var lat = Number(m.lat);
        var lng = Number(m.lng);
        if (!validLat(lat) || !validLng(lng)) { return; }
        var color = m.color || LEVEL_COLORS[m.level] || '#1f9d63';
        var marker = window.L.marker([lat, lng], { icon: pinIcon(color, m.icon), title: m.title || '' });
        if (m.title || m.subtitle || m.url) { marker.bindPopup(popupNode(m)); }
        marker.addTo(layer);
        bounds.push([lat, lng]);
      });
      if (bounds.length && (fit || !fitted)) {
        fitted = true;
        if (bounds.length === 1) { map.setView(bounds[0], 14); } else { map.fitBounds(bounds, { padding: [36, 36], maxZoom: 15 }); }
      }
      return bounds.length;
    }

    update(options.markers, true);
    return { map: map, update: update };
  }

  /* ----------------------------------------------------------- picker */
  function picker(options) {
    var latEl = byId(options.latInput);
    var lngEl = byId(options.lngInput);
    var statusEl = byId(options.statusEl);
    var locateBtn = byId(options.locateButton);
    var container = byId(options.id);
    var marker = null;
    var map = null;

    function status(text, kind) {
      if (!statusEl) { return; }
      statusEl.textContent = text || '';
      statusEl.className = 'pc-geo-status' + (kind ? ' ' + kind : '');
    }

    function readInputs() {
      var lat = toNumber(latEl && latEl.value);
      var lng = toNumber(lngEl && lngEl.value);
      return validLat(lat) && validLng(lng) ? [lat, lng] : null;
    }

    function writeInputs(lat, lng) {
      if (latEl) { latEl.value = lat.toFixed(6); latEl.dispatchEvent(new Event('change', { bubbles: true })); }
      if (lngEl) { lngEl.value = lng.toFixed(6); lngEl.dispatchEvent(new Event('change', { bubbles: true })); }
    }

    function place(lat, lng, zoom, fromMap) {
      if (!validLat(lat) || !validLng(lng)) { return; }
      writeInputs(lat, lng);
      if (!map) { return; }
      if (!marker) {
        marker = window.L.marker([lat, lng], { draggable: true, icon: pinIcon('#1f9d63', 'bi-geo-alt-fill') }).addTo(map);
        marker.on('dragend', function () {
          var p = marker.getLatLng();
          writeInputs(p.lat, p.lng);
          status('Location moved. Drag the pin or click the map to adjust it.', 'ok');
        });
      } else {
        marker.setLatLng([lat, lng]);
      }
      if (zoom) { map.setView([lat, lng], zoom); }
    }

    var start = readInputs();
    map = createMap(options.id, start || options.center || DEFAULT_CENTER, start ? 16 : (options.zoom || 5));
    if (map) {
      map.on('click', function (event) {
        place(event.latlng.lat, event.latlng.lng, null, true);
        status('Location selected on the map. Drag the pin to fine-tune it.', 'ok');
      });
      if (start) { place(start[0], start[1], 16, true); status('Location set. Drag the pin or click the map to change it.', 'ok'); }
    }

    // typing coordinates moves the pin
    [latEl, lngEl].forEach(function (input) {
      if (!input) { return; }
      input.addEventListener('input', function () {
        var p = readInputs();
        if (p && map) {
          if (!marker) { place(p[0], p[1], 16, true); } else { marker.setLatLng(p); map.panTo(p); }
        }
      });
    });

    function locate() {
      if (!('geolocation' in navigator)) {
        status('Your browser cannot detect its location. Click the map or type the coordinates instead.', 'error');
        return;
      }
      status('Finding your location...', '');
      if (locateBtn) { locateBtn.disabled = true; }
      navigator.geolocation.getCurrentPosition(function (pos) {
        if (locateBtn) { locateBtn.disabled = false; }
        place(pos.coords.latitude, pos.coords.longitude, 16, false);
        status('Location detected (accuracy about ' + Math.round(pos.coords.accuracy) + ' m). You can still drag the pin.', 'ok');
      }, function (err) {
        if (locateBtn) { locateBtn.disabled = false; }
        var text = 'Could not detect your location. Click the map or type the coordinates instead.';
        if (err && err.code === 1) { text = 'Location permission was denied. Click the map or type the coordinates instead.'; }
        else if (err && err.code === 2) { text = 'Your position is not available right now. Click the map or type the coordinates instead.'; }
        else if (err && err.code === 3) { text = 'Finding your location took too long. Try again or click the map.'; }
        status(text, 'error');
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
    }

    if (locateBtn) { locateBtn.addEventListener('click', locate); }
    if (container && options.autoLocate && !start) { locate(); }

    return { map: map, setPosition: function (lat, lng) { place(lat, lng, 16, false); }, locate: locate };
  }

  window.PawMap = { viewer: viewer, picker: picker, live: live, LEVEL_COLORS: LEVEL_COLORS };
})();
