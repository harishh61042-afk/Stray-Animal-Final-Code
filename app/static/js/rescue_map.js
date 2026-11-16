/* Rescue map: shows the reports that match the filters and refreshes the pins from /map/api/reports.
   If the refresh fails the last known pins stay on the map and a short notice is shown. */
(function () {
  'use strict';

  var root = document.querySelector('[data-rescue-map]');
  if (!root || !window.PawMap || !window.PawMap.live) { return; }

  var dataEl = document.getElementById('rescue-map-data');
  var initial = [];
  try { initial = JSON.parse(dataEl ? dataEl.textContent : '[]'); } catch (e) { initial = []; }

  var statusEl = document.getElementById('map-refresh-status');
  var refreshBtn = document.getElementById('map-refresh');

  function toMarkers(items) {
    return (items || []).map(function (m) {
      return {
        lat: m.lat, lng: m.lng, level: m.level, color: m.color, title: m.title,
        subtitle: m.code + ' · ' + m.level + ' · ' + m.status + (m.place ? ' · ' + m.place : ''),
        url: m.url, linkLabel: 'Open report'
      };
    });
  }

  function say(text, kind) {
    if (!statusEl) { return; }
    statusEl.textContent = text;
    statusEl.className = 'small ' + (kind === 'error' ? 'text-danger' : 'text-secondary');
  }

  var live = window.PawMap.live({ id: 'rescue-map', markers: toMarkers(initial) });
  if (!live) { return; }

  var apiUrl = (root.getAttribute('data-api') || '') + window.location.search;
  var seconds = parseInt(root.getAttribute('data-refresh') || '60', 10);
  var busy = false;

  function refresh() {
    if (busy) { return; }
    busy = true;
    if (refreshBtn) { refreshBtn.disabled = true; }
    fetch(apiUrl, {
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
      credentials: 'same-origin'
    }).then(function (response) {
      if (!response.ok) { throw new Error('HTTP ' + response.status); }
      return response.json();
    }).then(function (data) {
      live.update(toMarkers(data.markers), false);
      var now = new Date();
      say('Updated at ' + now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' · ' + data.mapped + ' of ' + data.total + ' reports have a location.', 'ok');
    }).catch(function () {
      say('Could not refresh the map. Showing the last known positions.', 'error');
    }).then(function () {
      busy = false;
      if (refreshBtn) { refreshBtn.disabled = false; }
    });
  }

  if (refreshBtn) { refreshBtn.addEventListener('click', refresh); }
  window.setInterval(function () { if (!document.hidden) { refresh(); } }, Math.max(seconds, 15) * 1000);
})();
