/* Volunteer task form: click the map (or use the current location) to set the place of the task. */
(function () {
  'use strict';

  var mapEl = document.getElementById('task-map');
  if (!mapEl) { return; }
  if (window.PawMap) {
    window.PawMap.picker({
      id: 'task-map',
      latInput: 'latitude',
      lngInput: 'longitude',
      locateButton: 'task-locate',
      statusEl: 'task-geo'
    });
  } else {
    var status = document.getElementById('task-geo');
    if (status) {
      status.textContent = 'The map could not be loaded. You can type the coordinates instead.';
      status.className = 'pc-geo-status m-0 error';
    }
  }
})();
