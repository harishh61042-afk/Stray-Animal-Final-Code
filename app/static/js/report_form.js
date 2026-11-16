/* Report form: map pin, "use my location" and the description counter.
   The form is fully usable without JavaScript or a working map - the address fields are what the rescue team reads. */
(function () {
  'use strict';

  var form = document.querySelector('[data-report-form]');
  if (!form) { return; }

  var statusEl = document.getElementById('geo-status');
  var locateBtn = document.getElementById('locate-btn');

  function say(text, kind) {
    if (!statusEl) { return; }
    statusEl.textContent = text;
    statusEl.className = 'pc-geo-status' + (kind ? ' ' + kind : '');
  }

  if (window.PawMap) {
    window.PawMap.picker({
      id: 'report-map',
      latInput: 'latitude',
      lngInput: 'longitude',
      locateButton: 'locate-btn',
      statusEl: 'geo-status'
    });
  } else {
    // maps.js could not be loaded (offline / blocked): still offer "use my location" and typed coordinates
    say('The map could not be loaded. Please write the address clearly; you can also use your current location.', 'error');
    if (locateBtn) {
      locateBtn.addEventListener('click', function () {
        if (!('geolocation' in navigator)) { say('Your browser cannot detect its location.', 'error'); return; }
        say('Finding your location...', '');
        navigator.geolocation.getCurrentPosition(function (pos) {
          document.getElementById('latitude').value = pos.coords.latitude.toFixed(6);
          document.getElementById('longitude').value = pos.coords.longitude.toFixed(6);
          say('Location detected. It will be sent with your report.', 'ok');
        }, function () {
          say('Could not detect your location. Please write the address instead.', 'error');
        }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
      });
    }
  }

  // description counter
  var area = document.getElementById('animal_description');
  var counter = document.getElementById('desc-counter');
  if (area && counter) {
    var max = parseInt(area.getAttribute('maxlength') || '2000', 10);
    var update = function () {
      var n = area.value.length;
      counter.textContent = n + ' / ' + max;
      counter.classList.toggle('over', n > max);
    };
    area.addEventListener('input', update);
    update();
  }
})();
