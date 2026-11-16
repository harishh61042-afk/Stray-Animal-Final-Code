/* Volunteer task page: show the task on the map and keep the progress slider's number in sync. */
(function () {
  'use strict';

  // Range sliders with a number next to them: <input type="range" data-range-output="some-output-id">
  Array.prototype.forEach.call(document.querySelectorAll('input[type="range"][data-range-output]'), function (range) {
    var output = document.getElementById(range.getAttribute('data-range-output'));
    if (!output) { return; }
    function update() { output.textContent = range.value + '%'; }
    range.addEventListener('input', update);
    update();
  });

  // Map with the place of the task (only when the page has one).
  var holder = document.getElementById('task-marker');
  if (!holder || !document.getElementById('task-map') || !window.PawMap) { return; }
  var markers = [];
  try { markers = JSON.parse(holder.textContent || '[]'); } catch (e) { markers = []; }
  window.PawMap.viewer({ id: 'task-map', markers: markers, zoom: 15 });
})();
