/* Sign-in / registration helpers: show-hide password, strength hint, location picker for shelters. */
(function () {
  'use strict';

  document.querySelectorAll('input[type="password"]').forEach(function (input) {
    var wrap = document.createElement('div');
    wrap.className = 'au-pw';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'au-pw-toggle';
    button.setAttribute('aria-label', 'Show password');
    button.innerHTML = '<i class="bi bi-eye"></i>';
    wrap.appendChild(button);
    button.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      button.innerHTML = '<i class="bi ' + (show ? 'bi-eye-slash' : 'bi-eye') + '"></i>';
    });
  });

  var strengthInput = document.querySelector('[data-strength-page] #password, [data-strength-page] #new_password');
  if (strengthInput) {
    var bar = document.createElement('div');
    bar.className = 'au-strength';
    bar.innerHTML = '<span></span>';
    var text = document.createElement('div');
    text.className = 'au-strength-text';
    var holder = strengthInput.closest('.au-pw') || strengthInput;
    holder.insertAdjacentElement('afterend', text);
    holder.insertAdjacentElement('afterend', bar);
    strengthInput.addEventListener('input', function () {
      var value = strengthInput.value;
      var score = 0;
      if (value.length >= 8) { score += 1; }
      if (/[A-Za-z]/.test(value) && /\d/.test(value)) { score += 1; }
      if (value.length >= 12) { score += 1; }
      if (/[A-Z]/.test(value) && /[a-z]/.test(value)) { score += 1; }
      if (/[^A-Za-z0-9]/.test(value)) { score += 1; }
      var colors = ['#e5484d', '#e5484d', '#f59f00', '#3b82f6', '#1f9d63', '#1f9d63'];
      var labels = ['', 'Too weak', 'Weak', 'Okay', 'Good', 'Strong'];
      bar.firstElementChild.style.width = (value ? Math.max(score, 1) * 20 : 0) + '%';
      bar.firstElementChild.style.background = colors[score];
      text.textContent = value ? labels[Math.max(score, 1)] + (value.length < 8 || !/\d/.test(value) || !/[A-Za-z]/.test(value) ? ' - use 8+ characters with letters and a number' : '') : '';
    });
  }

  var mapBox = document.getElementById('shelter-map');
  if (mapBox && window.PawMap) {
    var picker = window.PawMap.picker({ id: 'shelter-map', latInput: 'latitude', lngInput: 'longitude', locateButton: 'locate-btn', statusEl: 'geo-status' });
    // the map lives in a section that is hidden until the shelter role is chosen: resize it when it appears
    document.querySelectorAll('input[name="role"]').forEach(function (radio) {
      radio.addEventListener('change', function () {
        window.setTimeout(function () { if (picker && picker.map) { picker.map.invalidateSize(); } }, 80);
      });
    });
  }
})();
