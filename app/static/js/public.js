/* Public pages: animal photo gallery and "copy link" buttons. */
(function () {
  'use strict';

  var main = document.getElementById('pb-gallery-main');
  document.querySelectorAll('[data-gallery-thumb]').forEach(function (thumb) {
    thumb.addEventListener('click', function () {
      if (!main) { return; }
      main.src = thumb.getAttribute('data-src');
      main.alt = thumb.getAttribute('data-alt') || main.alt;
      document.querySelectorAll('[data-gallery-thumb]').forEach(function (other) {
        other.classList.toggle('active', other === thumb);
        other.setAttribute('aria-pressed', other === thumb ? 'true' : 'false');
      });
    });
  });

  document.querySelectorAll('[data-copy-link]').forEach(function (button) {
    button.addEventListener('click', function () {
      var url = window.location.href;
      var label = button.querySelector('span');
      function done(text) {
        if (label) {
          var original = label.textContent;
          label.textContent = text;
          window.setTimeout(function () { label.textContent = original; }, 2000);
        }
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { done('Link copied'); }, function () { done('Copy failed'); });
      } else {
        var input = document.createElement('input');
        input.value = url;
        document.body.appendChild(input);
        input.select();
        try { document.execCommand('copy'); done('Link copied'); } catch (e) { done('Copy failed'); }
        document.body.removeChild(input);
      }
    });
  });
})();
