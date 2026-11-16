/* Dashboard helpers: filter buttons of the "Recent activity" table. */
(function () {
  'use strict';

  document.querySelectorAll('[data-feed-filter]').forEach(function (group) {
    var table = document.querySelector(group.getAttribute('data-feed-filter'));
    if (!table) { return; }
    var rows = table.querySelectorAll('tbody tr[data-kind]');
    var empty = table.querySelector('.db-feed-empty');

    group.querySelectorAll('button[data-kind]').forEach(function (button) {
      button.addEventListener('click', function () {
        var kind = button.getAttribute('data-kind');
        var shown = 0;
        group.querySelectorAll('button[data-kind]').forEach(function (other) {
          other.classList.toggle('active', other === button);
        });
        rows.forEach(function (row) {
          var match = !kind || row.getAttribute('data-kind') === kind;
          row.hidden = !match;
          if (match) { shown += 1; }
        });
        if (empty) { empty.hidden = shown !== 0; }
      });
    });
  });
})();
