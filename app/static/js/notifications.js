/* PawConnect notifications - polls the unread count, fills the bell dropdown and marks items as read.
   Configured through data-* attributes on its own <script> tag (see base.html / layouts/app.html):
     data-poll          seconds between checks (default 30)
     data-count-url     GET  -> {"count": 3}
     data-recent-url    GET  -> {"count": 3, "items": [{id, title, message, icon, link, is_read, created_at}]}
     data-read-url      POST -> mark one read; the URL ends in /0/read, "0" is replaced by the notification id
     data-read-all-url  POST -> mark everything read
     data-all-url       page that lists all notifications                                                   */
(function () {
  'use strict';

  var script = document.currentScript;
  if (!script) { return; }

  var pollSeconds = Math.max(10, parseInt(script.getAttribute('data-poll'), 10) || 30);
  var countUrl = script.getAttribute('data-count-url');
  var recentUrl = script.getAttribute('data-recent-url');
  var readUrl = script.getAttribute('data-read-url');
  var readAllUrl = script.getAttribute('data-read-all-url');
  var allUrl = script.getAttribute('data-all-url') || '#';

  var lastCount = null;
  var timer = null;
  var stopped = false;

  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function request(url, method) {
    return fetch(url, {
      method: method || 'GET',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf() },
      keepalive: method === 'POST'
    }).then(function (response) {
      var type = response.headers.get('content-type') || '';
      if (response.status === 401 || response.status === 403 || response.redirected || type.indexOf('json') === -1) {
        stopped = true; // signed out or session expired - stop asking
        throw new Error('not-authenticated');
      }
      if (!response.ok) { throw new Error('http-' + response.status); }
      return response.json();
    });
  }

  /* ------------------------------------------------------------ badges */
  function setBadges(count) {
    var text = count > 99 ? '99+' : String(count);
    Array.prototype.slice.call(document.querySelectorAll('[data-unread-badge]')).forEach(function (badge) {
      badge.textContent = text;
      badge.hidden = !(count > 0);
    });
  }

  /* -------------------------------------------------------------- list */
  function relativeTime(iso) {
    if (!iso) { return ''; }
    var seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (isNaN(seconds)) { return ''; }
    if (seconds < 45) { return 'just now'; }
    var minutes = Math.round(seconds / 60);
    if (minutes < 60) { return minutes + ' min ago'; }
    var hours = Math.round(minutes / 60);
    if (hours < 24) { return hours + ' hour' + (hours === 1 ? '' : 's') + ' ago'; }
    var days = Math.round(hours / 24);
    if (days < 30) { return days + ' day' + (days === 1 ? '' : 's') + ' ago'; }
    return new Date(iso).toLocaleDateString();
  }

  function itemNode(item) {
    var link = document.createElement('a');
    link.className = 'pc-notif-item' + (item.is_read ? '' : ' unread');
    link.href = item.link || allUrl;
    link.setAttribute('data-id', item.id);

    var icon = document.createElement('span');
    icon.className = 'pc-notif-icon';
    var glyph = document.createElement('i');
    glyph.className = 'bi ' + (item.icon || 'bi-bell');
    icon.appendChild(glyph);

    var text = document.createElement('div');
    text.className = 'pc-notif-text';
    var title = document.createElement('strong');
    title.textContent = item.title;
    var message = document.createElement('span');
    message.textContent = item.message || '';
    var time = document.createElement('small');
    time.textContent = relativeTime(item.created_at);
    text.appendChild(title);
    text.appendChild(message);
    text.appendChild(time);

    link.appendChild(icon);
    link.appendChild(text);
    link.addEventListener('click', function () {
      if (!item.is_read && readUrl) {
        request(readUrl.replace('/0/', '/' + item.id + '/'), 'POST').catch(function () { /* the target page marks it read too */ });
      }
    });
    return link;
  }

  function message(listEl, html) {
    listEl.innerHTML = '';
    var box = document.createElement('div');
    box.className = 'pc-notif-empty';
    box.innerHTML = html;
    listEl.appendChild(box);
  }

  function loadList() {
    var lists = Array.prototype.slice.call(document.querySelectorAll('[data-notif-list]'));
    if (!lists.length || !recentUrl) { return Promise.resolve(); }
    return request(recentUrl).then(function (data) {
      setBadges(data.count || 0);
      lastCount = data.count || 0;
      lists.forEach(function (listEl) {
        listEl.innerHTML = '';
        if (!data.items || !data.items.length) {
          message(listEl, '<i class="bi bi-bell-slash d-block fs-4 mb-2"></i>You have no notifications yet.');
          return;
        }
        data.items.forEach(function (item) { listEl.appendChild(itemNode(item)); });
      });
    }).catch(function (error) {
      if (error && error.message === 'not-authenticated') { return; }
      lists.forEach(function (listEl) {
        message(listEl, '<i class="bi bi-wifi-off d-block fs-4 mb-2"></i>Could not load notifications. Please try again.');
      });
    });
  }

  /* ----------------------------------------------------------- polling */
  function menuIsOpen() {
    return !!document.querySelector('[data-notif-root] .dropdown-menu.show');
  }

  function poll() {
    if (stopped || !countUrl) { return; }
    if (document.visibilityState === 'hidden') { schedule(); return; }
    request(countUrl).then(function (data) {
      var count = data.count || 0;
      setBadges(count);
      if (lastCount !== null && count !== lastCount && menuIsOpen()) { loadList(); }
      lastCount = count;
    }).catch(function () { /* offline / server restarting: try again next time */ }).then(schedule);
  }

  function schedule() {
    if (stopped) { return; }
    window.clearTimeout(timer);
    timer = window.setTimeout(poll, pollSeconds * 1000);
  }

  /* ------------------------------------------------------------ events */
  Array.prototype.slice.call(document.querySelectorAll('[data-notif-root]')).forEach(function (root) {
    root.addEventListener('show.bs.dropdown', loadList);
  });

  document.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('[data-notif-read-all]') : null;
    if (!button || !readAllUrl) { return; }
    event.preventDefault();
    request(readAllUrl, 'POST').then(function () {
      setBadges(0);
      lastCount = 0;
      Array.prototype.slice.call(document.querySelectorAll('.pc-notif-item.unread')).forEach(function (el) { el.classList.remove('unread'); });
    }).catch(function () { /* nothing else to do */ });
  });

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && !stopped) { poll(); }
  });

  schedule();
})();
