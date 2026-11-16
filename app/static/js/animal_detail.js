/* Animal page: photo gallery, rescue-location map and the capacity override box. */
(function () {
  'use strict';

  // gallery: clicking a thumbnail shows that photo in the big frame
  var main = document.getElementById('an-gallery-main');
  var thumbs = document.querySelectorAll('[data-gallery-thumb]');
  Array.prototype.forEach.call(thumbs, function (thumb) {
    thumb.addEventListener('click', function () {
      if (!main) { return; }
      main.src = thumb.getAttribute('data-src');
      main.alt = thumb.getAttribute('data-alt') || main.alt;
      Array.prototype.forEach.call(thumbs, function (other) {
        other.classList.toggle('active', other === thumb);
        other.setAttribute('aria-pressed', other === thumb ? 'true' : 'false');
      });
    });
  });

  // where the animal was found
  var data = document.getElementById('animal-map-data');
  var box = document.getElementById('animal-location-map');
  if (data && box && window.PawMap) {
    var markers = [];
    try { markers = JSON.parse(data.textContent || '[]'); } catch (e) { markers = []; }
    window.PawMap.viewer({ id: 'animal-location-map', markers: markers, zoom: 15 });
  }

  // the capacity override only makes sense once a shelter was chosen
  var shelter = document.getElementById('shelter_id');
  var override = document.getElementById('override-box');
  if (shelter && override) {
    var refresh = function () { override.hidden = !shelter.value; };
    shelter.addEventListener('change', refresh);
    refresh();
  }
})();
