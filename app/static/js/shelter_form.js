/* Shelter profile form: click the map (or use the current location) to set the shelter's pin. */
(function () {
  'use strict';

  var mapEl = document.getElementById('shelter-map');
  if (!mapEl) { return; }
  if (window.PawMap) {
    window.PawMap.picker({
      id: 'shelter-map',
      latInput: 'latitude',
      lngInput: 'longitude',
      locateButton: 'shelter-locate',
      statusEl: 'shelter-geo'
    });
  } else {
    var status = document.getElementById('shelter-geo');
    if (status) {
      status.textContent = 'The map could not be loaded. You can type the coordinates instead.';
      status.className = 'pc-geo-status m-0 error';
    }
  }
})();
