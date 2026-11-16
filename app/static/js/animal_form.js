/* Animal form: map picker for the rescue location, and the capacity-override box (administrators). */
(function () {
  'use strict';

  var mapEl = document.getElementById('animal-map');
  if (mapEl && window.PawMap) {
    window.PawMap.picker({
      id: 'animal-map',
      latInput: 'latitude',
      lngInput: 'longitude',
      locateButton: 'animal-locate',
      statusEl: 'animal-geo'
    });
  } else if (mapEl) {
    var status = document.getElementById('animal-geo');
    if (status) {
      status.textContent = 'The map could not be loaded. You can type the coordinates instead.';
      status.className = 'pc-geo-status m-0 error';
    }
  }

  // the capacity override only makes sense once a shelter has been chosen
  var shelter = document.getElementById('shelter_id');
  var box = document.getElementById('override-box');
  if (shelter && box) {
    var refresh = function () { box.hidden = !shelter.value; };
    shelter.addEventListener('change', refresh);
    refresh();
  }
})();
