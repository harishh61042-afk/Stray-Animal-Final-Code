/* PawConnect - behaviour shared by every page.
   Plain JavaScript, no build step. Needs Bootstrap's bundle for modals / dropdowns (falls back gracefully). */
(function () {
  'use strict';

  var doc = document;
  var body = doc.body;

  function qs(sel, root) { return (root || doc).querySelector(sel); }
  function qsa(sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); }
  function hasBootstrap() { return typeof window.bootstrap !== 'undefined'; }

  /* ------------------------------------------------------------------ theme */
  function applyTheme(theme, persist) {
    doc.documentElement.setAttribute('data-bs-theme', theme);
    if (persist) {
      try { localStorage.setItem('pc-theme', theme); } catch (e) { /* storage blocked - theme just lasts for this page */ }
    }
    qsa('[data-theme-toggle] i').forEach(function (icon) {
      icon.className = 'bi ' + (theme === 'dark' ? 'bi-sun' : 'bi-moon-stars');
    });
    window.dispatchEvent(new CustomEvent('pc:theme', { detail: { theme: theme } }));
  }

  function currentTheme() {
    return doc.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
  }

  qsa('[data-theme-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () { applyTheme(currentTheme() === 'dark' ? 'light' : 'dark', true); });
  });
  applyTheme(currentTheme(), false); // sync the toggle icon with the theme chosen by the inline script

  /* --------------------------------------------------------------- sidebar */
  function setSidebar(open) { body.classList.toggle('pc-sidebar-open', open); }
  var openBtn = qs('#pcSidebarOpen');
  var closeBtn = qs('#pcSidebarClose');
  var backdrop = qs('#pcBackdrop');
  if (openBtn) { openBtn.addEventListener('click', function () { setSidebar(true); }); }
  if (closeBtn) { closeBtn.addEventListener('click', function () { setSidebar(false); }); }
  if (backdrop) { backdrop.addEventListener('click', function () { setSidebar(false); }); }
  doc.addEventListener('keydown', function (event) { if (event.key === 'Escape') { setSidebar(false); } });
  qsa('.pc-sidebar .pc-nav-link[href]').forEach(function (link) {
    link.addEventListener('click', function () { setSidebar(false); });
  });
  window.addEventListener('resize', function () { if (window.innerWidth >= 992) { setSidebar(false); } });

  /* ------------------------------------------------------- confirm dialogs */
  var confirmModalEl = qs('#pcConfirmModal');
  var confirmOk = qs('#pcConfirmOk');
  var confirmState = { onOk: null };

  function askConfirm(trigger, onOk) {
    var message = trigger.getAttribute('data-confirm') || 'Are you sure?';
    var title = trigger.getAttribute('data-confirm-title') || 'Please confirm';
    var okLabel = trigger.getAttribute('data-confirm-ok') || 'Yes, continue';
    var danger = trigger.getAttribute('data-confirm-tone') === 'danger' ||
      /delete|remove|reject|cancel|discharge|suspend|deactivate|withdraw/i.test(message + ' ' + okLabel);

    if (!confirmModalEl || !confirmOk || !hasBootstrap()) {
      if (window.confirm(message)) { onOk(); }
      return;
    }
    qs('#pcConfirmTitle').textContent = title;
    qs('#pcConfirmMessage').textContent = message;
    confirmOk.textContent = okLabel;
    confirmOk.className = 'btn px-4 ' + (danger ? 'btn-danger' : 'btn-primary');
    var icon = qs('.pc-modal-icon', confirmModalEl);
    if (icon) {
      icon.classList.toggle('danger', danger);
      icon.innerHTML = '<i class="bi ' + (danger ? 'bi-exclamation-triangle' : 'bi-question-lg') + '"></i>';
    }
    confirmState.onOk = onOk;
    window.bootstrap.Modal.getOrCreateInstance(confirmModalEl).show();
  }

  if (confirmOk) {
    confirmOk.addEventListener('click', function () {
      var action = confirmState.onOk;
      confirmState.onOk = null;
      if (hasBootstrap()) { window.bootstrap.Modal.getOrCreateInstance(confirmModalEl).hide(); }
      if (action) { action(); }
    });
  }

  function submitForm(form, submitter) {
    form.setAttribute('data-confirmed', '1');
    if (typeof form.requestSubmit === 'function') {
      try { form.requestSubmit(submitter || undefined); return; } catch (e) { /* fall through */ }
    }
    form.submit();
  }

  // <form data-confirm="..."> : ask before the form is sent
  doc.addEventListener('submit', function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-confirm')) { return; }
    if (form.getAttribute('data-confirmed') === '1') { form.removeAttribute('data-confirmed'); return; }
    event.preventDefault();
    var submitter = event.submitter || null;
    askConfirm(form, function () { submitForm(form, submitter); });
  }, true);

  // <button|a data-confirm="..."> : ask before the click does its job
  doc.addEventListener('click', function (event) {
    var trigger = event.target.closest ? event.target.closest('button[data-confirm], a[data-confirm], input[data-confirm]') : null;
    if (!trigger) { return; }
    event.preventDefault();
    askConfirm(trigger, function () {
      if (trigger.tagName === 'A') { window.location.href = trigger.href; return; }
      if (trigger.form) { submitForm(trigger.form, trigger); }
    });
  });

  /* -------------------------------------------------- loading buttons/forms */
  function startLoading(button) {
    if (!button || button.classList.contains('is-loading')) { return; }
    button.classList.add('is-loading');
    button.setAttribute('data-original-html', button.innerHTML);
    var text = button.getAttribute('data-loading-text') || 'Please wait...';
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ' + text;
    button.setAttribute('aria-busy', 'true');
    button.disabled = true;
  }

  function stopLoading(button) {
    var original = button.getAttribute('data-original-html');
    if (original !== null) { button.innerHTML = original; }
    button.classList.remove('is-loading');
    button.removeAttribute('aria-busy');
    button.disabled = false;
  }

  doc.addEventListener('submit', function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || event.defaultPrevented) { return; }
    var buttons = qsa('[data-loading]', form);
    if (event.submitter && event.submitter.hasAttribute('data-loading')) { buttons = [event.submitter]; }
    // disable after the browser has collected the form data
    window.setTimeout(function () { buttons.forEach(startLoading); }, 0);
  });

  // Back/forward cache: never leave a button stuck in the loading state.
  window.addEventListener('pageshow', function (event) {
    if (event.persisted) { qsa('.is-loading').forEach(stopLoading); }
  });

  /* ------------------------------------------------------- flash messages */
  qsa('[data-autodismiss]').forEach(function (alertEl) {
    var delay = parseInt(alertEl.getAttribute('data-autodismiss'), 10) || 6000;
    window.setTimeout(function () {
      if (!alertEl.isConnected) { return; }
      if (hasBootstrap()) { window.bootstrap.Alert.getOrCreateInstance(alertEl).close(); } else { alertEl.remove(); }
    }, delay);
  });

  /* ----------------------------------------------------- filter auto-submit */
  qsa('[data-auto-submit]').forEach(function (field) {
    field.addEventListener('change', function () {
      var form = field.form || field.closest('form');
      if (form) {
        var page = form.querySelector('input[name="page"]');
        if (page) { page.value = '1'; }
        submitForm(form);
      }
    });
  });

  /* ---------------------------------------------------------- file previews */
  qsa('input[type="file"][data-preview]').forEach(function (input) {
    var holder = doc.createElement('div');
    holder.className = 'pc-upload-preview';
    holder.hidden = true;
    var error = doc.createElement('div');
    error.className = 'invalid-feedback d-block';
    error.hidden = true;
    input.insertAdjacentElement('afterend', holder);
    holder.insertAdjacentElement('beforebegin', error);
    var maxMb = parseFloat(input.getAttribute('data-max-mb')) || 8;
    var urls = [];

    input.addEventListener('change', function () {
      urls.forEach(function (url) { URL.revokeObjectURL(url); });
      urls = [];
      holder.innerHTML = '';
      error.hidden = true;
      var files = Array.prototype.slice.call(input.files || []);
      var tooBig = files.filter(function (file) { return file.size > maxMb * 1024 * 1024; });
      if (tooBig.length) {
        error.textContent = tooBig[0].name + ' is larger than ' + maxMb + ' MB. Please choose a smaller file.';
        error.hidden = false;
        input.value = '';
        holder.hidden = true;
        return;
      }
      files.forEach(function (file) {
        if (/^image\//.test(file.type)) {
          var img = doc.createElement('img');
          var url = URL.createObjectURL(file);
          urls.push(url);
          img.src = url;
          img.alt = file.name;
          holder.appendChild(img);
        } else {
          var chip = doc.createElement('span');
          chip.className = 'pc-chip';
          chip.innerHTML = '<i class="bi bi-file-earmark"></i>';
          chip.appendChild(doc.createTextNode(file.name));
          holder.appendChild(chip);
        }
      });
      holder.hidden = files.length === 0;
    });
  });

  /* ------------------------------------------------- conditional sections
     <div data-visible-when-field="role" data-visible-when-value="Rescuer,Veterinarian"> ... </div>
     The section is shown only while the named field has one of the listed values. */
  function fieldValues(scope, name) {
    var values = [];
    qsa('[name="' + name + '"]', scope).forEach(function (el) {
      if (el.type === 'radio' || el.type === 'checkbox') {
        if (el.checked) { values.push(el.value); }
      } else if (el.value !== '') {
        values.push(el.value);
      }
    });
    return values;
  }

  qsa('[data-visible-when-field]').forEach(function (section) {
    var name = section.getAttribute('data-visible-when-field');
    var wanted = (section.getAttribute('data-visible-when-value') || '').split(',').map(function (v) { return v.trim(); });
    var scope = section.closest('form') || doc;
    function refresh() {
      var current = fieldValues(scope, name);
      var show = current.some(function (v) { return wanted.indexOf(v) !== -1; });
      section.hidden = !show;
    }
    qsa('[name="' + name + '"]', scope).forEach(function (el) {
      el.addEventListener('change', refresh);
      el.addEventListener('input', refresh);
    });
    refresh();
  });

  /* ----------------------------------------------------------- small helpers */
  // <button data-copy="RPT-2026-00001">Copy</button>
  doc.addEventListener('click', function (event) {
    var btn = event.target.closest ? event.target.closest('[data-copy]') : null;
    if (!btn) { return; }
    var text = btn.getAttribute('data-copy');
    var done = function () {
      var original = btn.innerHTML;
      btn.innerHTML = '<i class="bi bi-check2"></i> Copied';
      window.setTimeout(function () { btn.innerHTML = original; }, 1600);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { legacyCopy(text, done); });
    } else {
      legacyCopy(text, done);
    }
  });

  function legacyCopy(text, done) {
    var area = doc.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    body.appendChild(area);
    area.select();
    try { doc.execCommand('copy'); done(); } catch (e) { window.prompt('Copy this text:', text); }
    body.removeChild(area);
  }

  // <button data-print>Print</button>
  doc.addEventListener('click', function (event) {
    var btn = event.target.closest ? event.target.closest('[data-print]') : null;
    if (btn) { window.print(); }
  });

  // Bootstrap tooltips
  if (hasBootstrap()) {
    qsa('[data-bs-toggle="tooltip"]').forEach(function (el) { new window.bootstrap.Tooltip(el); });
  }

  // CSRF token for fetch() calls made by other scripts: PawConnect.csrfToken()
  window.PawConnect = window.PawConnect || {};
  window.PawConnect.csrfToken = function () {
    var meta = qs('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  };
  window.PawConnect.confirm = askConfirm;
})();
