/* Board + kiosk logic. One source of truth: /api/state. SSE only says
   "something changed" and triggers a refetch; a 5s poll backs it up, so a
   dropped stream can never freeze the screen. Plain ES5-ish, no deps. */
(function () {
  'use strict';
  var cfg = window.HS || {};
  var state = null;
  var carFilter = '';
  var answered = {};       // client_ids the operator already handled (in flight)
  var currentPopup = null; // client_id shown in the popup right now

  function api(path, body) {
    return fetch(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + cfg.token
      },
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json(); });
  }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function gap(ms, bestMs) {
    if (ms === bestMs) return '';
    var d = (ms - bestMs) / 1000;
    return '+' + d.toFixed(3);
  }

  function chips(lap) {
    var out = [];
    if (lap.tyre_compound) out.push(lap.tyre_compound.replace(/\s*\(.*\)$/, ''));
    (lap.aids || []).forEach(function (a) { out.push(a); });
    return out.map(function (c) { return '<span class="chip">' + esc(c) + '</span>'; }).join('');
  }

  function renderBoard() {
    var rows = document.getElementById('board-rows');
    var empty = document.getElementById('board-empty');
    var board = state.leaderboard || [];
    empty.hidden = board.length > 0;
    var bestMs = board.length ? board[0].lap_ms : 0;
    var inhouse = cfg.kind === 'inhouse';
    rows.innerHTML = board.slice(0, 20).map(function (lap) {
      var cls = 'b-row' + (lap.rank === 1 ? ' b-row--p1' : '');
      return '<li class="' + cls + '">' +
        '<span class="b-row__rank">' + lap.rank + '</span>' +
        '<span class="b-row__name">' + esc(lap.driver_name) +
        (inhouse ? '<span class="b-row__chips">' +
          '<span class="chip chip--car">' + esc(lap.car) + '</span>' + chips(lap) +
          '</span>' : '') +
        '</span>' +
        '<span class="b-row__gap">' + gap(lap.lap_ms, bestMs) + '</span>' +
        '<span class="b-row__time">' + esc(lap.lap_time) + '</span>' +
        '</li>';
    }).join('');
  }

  function renderRecent() {
    var ul = document.getElementById('recent-rows');
    ul.innerHTML = (state.recent || []).map(function (lap) {
      var name = lap.driver_name ? esc(lap.driver_name)
        : '<em class="b-pending">waiting for name…</em>';
      var flags = !lap.valid ? ' <span class="chip chip--invalid">' +
        (lap.cuts > 0 ? 'cut' : 'invalid') + '</span>' : '';
      return '<li><span class="b-recent__time">' + esc(lap.lap_time) + '</span>' +
        '<span class="b-recent__name">' + name + flags + '</span></li>';
    }).join('');
  }

  function renderCars() {
    var sel = document.getElementById('car-filter');
    var cars = state.cars || [];
    var show = cfg.kind === 'inhouse' && cars.length > 1;
    sel.hidden = !show;
    if (!show) return;
    var options = '<option value="">All cars</option>' + cars.map(function (c) {
      return '<option value="' + esc(c) + '"' +
        (c === carFilter ? ' selected' : '') + '>' + esc(c) + '</option>';
    }).join('');
    if (sel.innerHTML !== options) sel.innerHTML = options;
  }

  function renderDriverNames() {
    var dl = document.getElementById('driver-names');
    if (!dl) return;
    var names = {};
    (state.leaderboard || []).forEach(function (l) { names[l.driver_name] = 1; });
    (state.recent || []).forEach(function (l) { if (l.driver_name) names[l.driver_name] = 1; });
    dl.innerHTML = Object.keys(names).sort().map(function (n) {
      return '<option value="' + esc(n) + '">';
    }).join('');
  }

  function renderDriverBox() {
    var box = document.getElementById('driverbox');
    if (!box) return;
    var current = document.getElementById('driver-current');
    var name = state.event && state.event.current_driver;
    current.textContent = name ? ('Scoring laps to: ' + name) : 'No driver set — popup asks after each lap.';
  }

  function renderPopup() {
    var popup = document.getElementById('popup');
    if (!popup) return;
    var pending = (state.pending || []).filter(function (l) { return !answered[l.client_id]; });
    if (!pending.length) {
      popup.hidden = true;
      currentPopup = null;
      return;
    }
    var lap = pending[pending.length - 1]; // newest first: the person still standing there
    if (currentPopup !== lap.client_id) {
      currentPopup = lap.client_id;
      document.getElementById('popup-name').value = '';
      document.getElementById('popup-time').textContent = lap.lap_time;
      var meta = [lap.car, lap.track_config || lap.track].filter(Boolean).join(' · ');
      document.getElementById('popup-meta').textContent = meta;
    }
    var queue = document.getElementById('popup-queue');
    queue.textContent = pending.length > 1
      ? ('Nog ' + (pending.length - 1) + ' eerdere ronde(s) wachten op een naam.') : '';
    popup.hidden = false;
    document.getElementById('popup-name').focus();
  }

  function render() {
    if (!state || !state.event) return;
    renderBoard();
    renderRecent();
    renderCars();
    renderDriverNames();
    renderDriverBox();
    renderPopup();
  }

  function refresh() {
    var url = '/api/state?event=' + encodeURIComponent(cfg.event) +
      (carFilter ? '&car=' + encodeURIComponent(carFilter) : '');
    fetch(url).then(function (r) { return r.json(); }).then(function (data) {
      if (data && data.ok) { state = data; render(); setConn(true); }
    }).catch(function () { setConn(false); });
  }

  function setConn(ok) {
    var el = document.getElementById('conn-state');
    if (el) el.textContent = ok ? '' : 'reconnecting…';
  }

  // --- operator actions -----------------------------------------------------
  function saveName() {
    var input = document.getElementById('popup-name');
    var name = input.value.trim();
    if (!name || !currentPopup) return;
    var id = currentPopup;
    answered[id] = true;
    api('/api/laps/' + encodeURIComponent(id) + '/assign', { driver_name: name })
      .then(refresh);
    document.getElementById('popup').hidden = true;
    currentPopup = null;
  }

  function discardLap() {
    if (!currentPopup) return;
    var id = currentPopup;
    answered[id] = true;
    api('/api/laps/' + encodeURIComponent(id) + '/assign', { discard: true })
      .then(refresh);
    document.getElementById('popup').hidden = true;
    currentPopup = null;
  }

  if (cfg.operator) {
    document.getElementById('popup-save').addEventListener('click', saveName);
    document.getElementById('popup-discard').addEventListener('click', discardLap);
    document.getElementById('popup-name').addEventListener('keydown', function (e) {
      if (e.key === 'Enter') saveName();
    });
    document.getElementById('driver-set').addEventListener('click', function () {
      var name = document.getElementById('driver-input').value.trim();
      api('/api/current-driver', { name: name }).then(refresh);
    });
    document.getElementById('driver-clear').addEventListener('click', function () {
      document.getElementById('driver-input').value = '';
      api('/api/current-driver', { name: '' }).then(refresh);
    });
  }

  document.getElementById('car-filter').addEventListener('change', function () {
    carFilter = this.value;
    refresh();
  });

  // --- live -----------------------------------------------------------------
  function listen() {
    var es = new EventSource('/api/stream');
    es.onmessage = function () { refresh(); };
    es.onerror = function () { setConn(false); };
  }

  refresh();
  listen();
  setInterval(refresh, 5000); // belt and braces: never more than 5s stale
})();
