/* Board + kiosk logic, rendering the Claude Design markup. One source of
   truth: /api/state. SSE only says "something changed" and triggers a refetch;
   a 5s poll backs it up, so a dropped stream can never freeze the screen. */
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

  function setHTML(el, html) {
    // Only touch the DOM when the content actually changed: replacing
    // innerHTML restarts every row's lapIn animation, and doing that on each
    // 5s poll made the whole board visibly "reload". Now the animation only
    // plays when a lap or name really arrives.
    if (el.__lastHTML === html) return;
    el.__lastHTML = html;
    el.innerHTML = html;
  }

  function gap(ms, bestMs) {
    if (ms === bestMs) return '';
    return '+' + ((ms - bestMs) / 1000).toFixed(3);
  }

  function chipList(lap) {
    var out = [];
    if (lap.tyre_compound) out.push(lap.tyre_compound.replace(/\s*\(.*\)$/, ''));
    (lap.aids || []).forEach(function (a) { out.push(a); });
    return out;
  }

  function rowClass(rank) {
    var cls = 'b-row';
    if (rank <= 3) cls += ' b-row--podium b-row--p' + rank;
    return cls;
  }

  function boardCapacity(total) {
    // How many rows fit comfortably? Rows must never squeeze into slivers:
    // derive a count from the available height (min ~48px per row unit; a
    // podium row takes two units) and hand the overflow to the "+ N more"
    // tile. Small screens scroll instead and keep 20.
    var perRow = cfg.kind === 'inhouse' ? 1 : 2;
    if (window.innerWidth <= 900) return 17;
    var el = document.getElementById('board-rows');
    var height = el.clientHeight || 600;
    var gapPx = 10, minUnit = 48;
    var units = Math.max(8, Math.floor((height + gapPx) / (minUnit + gapPx)));
    var podiumUnits = Math.min(3, total) * 2;
    return Math.max(perRow, (units - podiumUnits) * perRow);
  }

  function renderBoard() {
    var rows = document.getElementById('board-rows');
    var empty = document.getElementById('board-empty');
    var board = state.leaderboard || [];
    empty.hidden = board.length > 0;
    var bestMs = board.length ? board[0].lap_ms : 0;
    var inhouse = cfg.kind === 'inhouse';

    var stdTotal = Math.max(0, board.length - 3);
    var cap = boardCapacity(board.length);
    var shown = stdTotal;
    var hidden = 0;
    if (stdTotal > cap) {
      shown = Math.max(0, cap - 1); // one cell goes to the "+ N more" tile
      hidden = stdTotal - shown;
    }
    var moreTile = hidden > 0
      ? '<li class="b-row b-row--more" data-more>+ ' + hidden +
        ' more driver' + (hidden === 1 ? '' : 's') + ' · full ranking</li>'
      : '';

    setHTML(rows, board.slice(0, 3 + shown).map(function (lap) {
      var who = inhouse
        ? '<span class="b-row__who"><span class="b-row__name">' +
          esc(lap.driver_name) + '</span><span class="b-row__chips">' +
          '<span class="chip chip--car">' + esc(lap.car) + '</span>' +
          chipList(lap).map(function (c) {
            return '<span class="chip">' + esc(c) + '</span>';
          }).join('') + '</span></span>'
        : '<span class="b-row__name">' + esc(lap.driver_name) + '</span>';
      return '<li class="' + rowClass(lap.rank) + '" data-driver="' +
        esc(lap.driver_name) + '">' +
        '<span class="b-row__rank">' + lap.rank + '</span>' + who +
        '<span class="b-row__gap">' + gap(lap.lap_ms, bestMs) + '</span>' +
        '<span class="b-row__time">' + esc(lap.lap_time) + '</span>' +
        '</li>';
    }).join('') + moreTile);
  }

  function renderRecent() {
    var ul = document.getElementById('recent-rows');
    var inhouse = cfg.kind === 'inhouse';
    setHTML(ul, (state.recent || []).slice(0, inhouse ? 6 : 8).map(function (lap) {
      var pending = !lap.driver_name && lap.valid;
      // Invalid laps never get the popup, so don't promise a name for them.
      var name = lap.driver_name ? esc(lap.driver_name)
        : (lap.valid ? 'waiting for name…' : '–');
      var flag = !lap.valid
        ? ' <span class="chip chip--cut">' + (lap.cuts > 0 ? 'Cut' : 'Invalid') + '</span>'
        : '';
      return '<li class="' + (pending ? 'is-pending' : '') + '">' +
        '<span class="b-recent__time">' + esc(lap.lap_time) + '</span>' +
        '<span class="b-recent__name"><span>' + name + '</span>' + flag + '</span></li>';
    }).join(''));
  }

  function renderMeta() {
    var box = document.getElementById('meta-cells');
    if (!box || !state.event) return;
    var stats = state.stats || {};
    var cell = function (label, value) {
      return '<div class="b-meta__cell"><span class="b-meta__label">' + label +
        '</span><span class="b-meta__value">' + esc(value) + '</span></div>';
    };
    var cells;
    if (cfg.kind === 'inhouse') {
      cells = [cell('Track', state.event.track_filter || 'any'),
               cell('Drivers', stats.drivers != null ? stats.drivers : '–'),
               cell('Laps today', stats.laps_today != null ? stats.laps_today : '–')];
    } else {
      var car = state.event.car_filter ||
        ((state.cars || []).length === 1 ? state.cars[0] : 'any');
      cells = [cell('Track', state.event.track_filter || 'any'),
               cell('Car', car),
               cell('Laps today', stats.laps_today != null ? stats.laps_today : '–'),
               cell('Drivers', stats.drivers != null ? stats.drivers : '–')];
    }
    setHTML(box, cells.join(''));
  }

  function renderCars() {
    var sel = document.getElementById('car-filter');
    if (!sel) return;
    var cars = state.cars || [];
    setHTML(sel, '<option value="">All cars</option>' + cars.map(function (c) {
      return '<option value="' + esc(c) + '"' +
        (c === carFilter ? ' selected' : '') + '>' + esc(c) + '</option>';
    }).join(''));
  }

  function renderDriverNames() {
    var dl = document.getElementById('driver-names');
    if (!dl) return;
    var names = {};
    (state.leaderboard || []).forEach(function (l) { names[l.driver_name] = 1; });
    (state.recent || []).forEach(function (l) { if (l.driver_name) names[l.driver_name] = 1; });
    setHTML(dl, Object.keys(names).sort().map(function (n) {
      return '<option value="' + esc(n) + '">';
    }).join(''));
  }

  function renderDriverBox() {
    var current = document.getElementById('driver-current');
    if (!current) return;
    var name = state.event && state.event.current_driver;
    current.textContent = name ? ('Scoring laps to: ' + name)
      : 'No driver set — the popup asks after each lap.';
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
      var meta = document.getElementById('popup-meta');
      var sub = [lap.track_config || lap.track,
                 (lap.tyre_compound || '').toLowerCase()]
        .filter(Boolean).join(' · ');
      meta.innerHTML = '<span>' + esc(lap.car) + '</span>' +
        (sub ? '<span class="sub">' + esc(sub) + '</span>' : '');
    }
    closeDetail(); // the name popup takes priority over a browsing detour
    closeRanking();
    var queue = document.getElementById('popup-queue');
    var older = pending.length - 1;
    queue.hidden = older < 1;
    if (older >= 1) {
      document.getElementById('popup-queue-text').textContent = older === 1
        ? '1 older lap is still waiting for a name'
        : older + ' older laps are still waiting for a name';
    }
    popup.hidden = false;
    document.getElementById('popup-name').focus();
  }

  // --- driver detail card (click a name on the board) -----------------------
  var detailTimer = null;
  var rankingTimer = null;

  function closeDetail() {
    var el = document.getElementById('detail');
    if (el) el.hidden = true;
    if (detailTimer) { clearTimeout(detailTimer); detailTimer = null; }
  }

  function closeRanking() {
    var el = document.getElementById('ranking');
    if (el) el.hidden = true;
    if (rankingTimer) { clearTimeout(rankingTimer); rankingTimer = null; }
  }

  function fmtClock(iso) {
    try {
      return new Date(iso).toLocaleTimeString('nl-BE',
        { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return ''; }
  }

  function fmtWhen(iso) {
    // "today 15:12" / "yesterday 09:46" / "12 aug 09:46" / "12 aug 2025 09:46".
    // In-house timing spans weeks, so a bare clock time says nothing.
    try {
      var d = new Date(iso);
      var now = new Date();
      var day = function (x) { return new Date(x.getFullYear(), x.getMonth(), x.getDate()); };
      var diffDays = Math.round((day(now) - day(d)) / 86400000);
      var clock = d.toLocaleTimeString('nl-BE', { hour: '2-digit', minute: '2-digit' });
      if (diffDays === 0) return 'today ' + clock;
      if (diffDays === 1) return 'yesterday ' + clock;
      var opts = { day: 'numeric', month: 'short' };
      if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric';
      return d.toLocaleDateString('nl-BE', opts) + ' ' + clock;
    } catch (e) { return ''; }
  }

  function statCell(label, value) {
    return '<div class="detail__stat"><span class="detail__stat-label">' +
      label + '</span><span class="detail__stat-value">' + value + '</span></div>';
  }

  // --- circuit map: where the lap gains or loses time vs P1 -----------------
  var COL_MID = [62, 88, 112], COL_SKY = [85, 190, 236], COL_HEAT = [219, 88, 39];

  function lerpColor(a, b, f) {
    return 'rgb(' + a.map(function (v, i) {
      return Math.round(v + (b[i] - v) * f);
    }).join(',') + ')';
  }

  function segColor(diffMs) {
    var f = Math.max(-1, Math.min(1, diffMs / 120)); // ±120 ms per segment
    return f < 0 ? lerpColor(COL_MID, COL_SKY, -f) : lerpColor(COL_MID, COL_HEAT, f);
  }

  function bestTraceLap(laps, wantMs) {
    var have = (laps || []).filter(function (l) { return l.trace && l.valid; });
    if (!have.length) return null;
    for (var i = 0; i < have.length; i++) {
      if (have[i].lap_ms === wantMs) return have[i];
    }
    have.sort(function (a, b) { return a.lap_ms - b.lap_ms; });
    return have[0];
  }

  function buildMap(you, leader, isLeader) {
    var geo = (leader && leader.trace) || (you && you.trace);
    if (!geo) return '';
    var k = geo.x.length;
    var minX = Math.min.apply(null, geo.x), maxX = Math.max.apply(null, geo.x);
    var minZ = Math.min.apply(null, geo.z), maxZ = Math.max.apply(null, geo.z);
    var W = 560, H = 340, P = 24;
    var s = Math.min((W - 2 * P) / ((maxX - minX) || 1),
                     (H - 2 * P) / ((maxZ - minZ) || 1));
    var ox = (W - (maxX - minX) * s) / 2, oz = (H - (maxZ - minZ) * s) / 2;
    function px(i) { return ((geo.x[i] - minX) * s + ox).toFixed(1); }
    function pz(i) { return ((geo.z[i] - minZ) * s + oz).toFixed(1); }
    var compare = !isLeader && you && you.trace && leader && leader.trace;
    var segs = '';
    for (var i = 0; i < k; i++) {
      var j = (i + 1) % k;
      var col = '#55BEEC';
      if (compare) {
        var dtY = (j ? you.trace.t[j] : you.lap_ms) - you.trace.t[i];
        var dtL = (j ? leader.trace.t[j] : leader.lap_ms) - leader.trace.t[i];
        col = segColor(dtY - dtL);
      }
      segs += '<line x1="' + px(i) + '" y1="' + pz(i) + '" x2="' + px(j) +
        '" y2="' + pz(j) + '" stroke="' + col +
        '" stroke-width="9" stroke-linecap="round"/>';
    }
    var start = '<circle cx="' + px(0) + '" cy="' + pz(0) +
      '" r="7" fill="#021E37" stroke="#FFFFFF" stroke-width="3"/>';
    var legend = compare
      ? '<span class="detail__legend"><i style="background:#55BEEC"></i>faster than P1' +
        '<i style="background:#DB5827"></i>slower than P1</span>'
      : '<span class="detail__legend">' +
        (isLeader ? 'The benchmark lap — everyone is compared to this one.'
                  : 'No comparison available yet.') + '</span>';
    return '<div class="detail__mapwrap"><div class="detail__attempts">' +
      '<h4>Circuit · vs P1</h4>' + legend + '</div>' +
      '<svg class="detail__map" viewBox="0 0 ' + W + ' ' + H +
      '" role="img">' + segs + start + '</svg></div>';
  }

  function buildDetail(name, laps, leaderLaps) {
    var entry = null;
    (state.leaderboard || []).forEach(function (l) {
      if (l.driver_name === name) entry = l;
    });
    if (!entry || !laps.length) return '';
    var board = state.leaderboard;
    var subs = ['P' + entry.rank];
    if (entry.rank === 1) {
      subs.push('fastest lap of the event');
    } else {
      subs.push(gap(entry.lap_ms, board[0].lap_ms) + ' behind P1');
      var ahead = board[entry.rank - 2];
      if (ahead && entry.rank > 2) {
        subs.push(gap(entry.lap_ms, ahead.lap_ms) + ' behind P' + ahead.rank);
      }
    }

    var best = entry;
    var chipsHtml = '<span class="chip chip--car">' + esc(best.car) + '</span>' +
      chipList(best).map(function (c) {
        return '<span class="chip">' + esc(c) + '</span>';
      }).join('');

    var stats = [];
    stats.push(statCell('Track', esc(best.track_config || best.track || '–')));
    if (best.session_type) stats.push(statCell('Session', esc(best.session_type)));
    stats.push(statCell('Driven', fmtWhen(best.recorded_at)));
    if (best.air_temp != null) stats.push(statCell('Air', best.air_temp.toFixed(1) + ' °C'));
    if (best.road_temp != null) stats.push(statCell('Road', best.road_temp.toFixed(1) + ' °C'));
    if (best.grip != null) stats.push(statCell('Grip', (best.grip * 100).toFixed(1) + '%'));
    if (best.fuel_rate != null) stats.push(statCell('Fuel use', '×' + best.fuel_rate));
    if (best.tyre_rate != null) stats.push(statCell('Tyre wear', '×' + best.tyre_rate));
    if (best.damage_rate != null) stats.push(statCell('Damage', '×' + best.damage_rate));

    var valid = laps.filter(function (l) { return l.valid; });
    var summary = laps.length + ' lap' + (laps.length === 1 ? '' : 's') +
      ' · ' + valid.length + ' valid';
    if (valid.length > 1) {
      var chrono = valid.slice().reverse(); // endpoint is newest-first
      var improved = chrono[0].lap_ms - entry.lap_ms;
      if (improved > 0) summary += ' · improved ' + (improved / 1000).toFixed(3) + 's';
    }

    var isLeader = entry.rank === 1;
    var youLap = bestTraceLap(laps, entry.lap_ms);
    var leaderEntry = board[0];
    var leaderLap = isLeader ? youLap
      : bestTraceLap(leaderLaps, leaderEntry ? leaderEntry.lap_ms : 0);
    var mapHtml = buildMap(youLap, leaderLap, isLeader);

    var history = laps.slice(0, 10).map(function (l) {
      var tag = '';
      if (l.lap_ms === entry.lap_ms && l.valid) {
        tag = '<span class="chip chip--best">Best</span>';
      } else if (!l.valid) {
        tag = '<span class="chip chip--cut">' + (l.cuts > 0 ? 'Cut' : 'Invalid') + '</span>';
      }
      return '<li><span class="detail__lap-time' + (l.valid ? '' : ' is-dim') + '">' +
        esc(l.lap_time) + '</span>' + tag +
        '<span class="detail__lap-when">' + fmtWhen(l.recorded_at) + '</span></li>';
    }).join('');
    var more = laps.length > 10 ? '<p class="detail__more">+ ' +
      (laps.length - 10) + ' earlier lap(s)</p>' : '';

    return '<p class="kicker kicker--sky detail__kicker"><span>Lap detail</span></p>' +
      '<div class="detail__head">' +
      '<span class="detail__rank">P' + entry.rank + '</span>' +
      '<div class="detail__who"><h3>' + esc(name) + '</h3>' +
      '<span class="detail__sub">' + subs.slice(1).join(' · ') + '</span></div>' +
      '<span class="detail__time">' + esc(entry.lap_time) + '</span></div>' +
      '<div class="detail__chips">' + chipsHtml + '</div>' +
      '<div class="detail__stats">' + stats.join('') + '</div>' +
      mapHtml +
      '<div class="detail__attempts"><h4>Attempts</h4>' +
      '<span class="detail__summary">' + summary + '</span></div>' +
      '<ul class="detail__laps">' + history + '</ul>' + more;
  }

  function fetchLaps(name) {
    return fetch('/api/driver-laps?event=' + encodeURIComponent(cfg.event) +
                 '&name=' + encodeURIComponent(name))
      .then(function (r) { return r.json(); })
      .then(function (d) { return (d && d.ok && d.laps) || []; })
      .catch(function () { return []; });
  }

  function openDetail(name) {
    var leaderName = ((state.leaderboard || [])[0] || {}).driver_name;
    var wants = [fetchLaps(name)];
    if (leaderName && leaderName !== name) wants.push(fetchLaps(leaderName));
    Promise.all(wants).then(function (results) {
      var html = buildDetail(name, results[0], results[1] || []);
      if (!html) return;
      closeRanking();
      document.getElementById('detail-body').innerHTML = html;
      document.getElementById('detail').hidden = false;
      if (detailTimer) clearTimeout(detailTimer);
      if (cfg.operator) { // kiosk: never leave the board hidden for long
        detailTimer = setTimeout(closeDetail, 45000);
      }
    });
  }

  // --- full-ranking modal ---------------------------------------------------
  function renderRankingList() {
    var ol = document.getElementById('ranking-list');
    if (!ol) return;
    var board = state.leaderboard || [];
    var bestMs = board.length ? board[0].lap_ms : 0;
    setHTML(ol, board.map(function (lap) {
      return '<li data-driver="' + esc(lap.driver_name) + '"' +
        (lap.rank <= 3 ? ' class="is-podium"' : '') + '>' +
        '<span class="ranking__rank">' + lap.rank + '</span>' +
        '<span class="ranking__name">' + esc(lap.driver_name) + '</span>' +
        '<span class="ranking__gap">' + gap(lap.lap_ms, bestMs) + '</span>' +
        '<span class="ranking__time">' + esc(lap.lap_time) + '</span></li>';
    }).join(''));
  }

  function openRanking() {
    if (!state || !(state.leaderboard || []).length) return;
    renderRankingList();
    document.getElementById('ranking').hidden = false;
    if (rankingTimer) clearTimeout(rankingTimer);
    if (cfg.operator) rankingTimer = setTimeout(closeRanking, 60000);
  }

  document.getElementById('board-rows').addEventListener('click', function (e) {
    if (e.target.closest('li[data-more]')) { openRanking(); return; }
    var row = e.target.closest('li[data-driver]');
    if (row) openDetail(row.getAttribute('data-driver'));
  });
  window.addEventListener('resize', function () {
    if (state) render();
  });
  document.getElementById('ranking-list').addEventListener('click', function (e) {
    var row = e.target.closest('li[data-driver]');
    if (row) openDetail(row.getAttribute('data-driver'));
  });
  document.getElementById('detail-close').addEventListener('click', closeDetail);
  document.getElementById('detail').addEventListener('click', function (e) {
    if (e.target === this) closeDetail();
  });
  document.getElementById('ranking-btn').addEventListener('click', openRanking);
  document.getElementById('ranking-close').addEventListener('click', closeRanking);
  document.getElementById('ranking').addEventListener('click', function (e) {
    if (e.target === this) closeRanking();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeDetail(); closeRanking(); }
  });

  function render() {
    if (!state || !state.event) return;
    renderBoard();
    renderRecent();
    renderMeta();
    renderCars();
    renderDriverNames();
    renderDriverBox();
    renderPopup();
    var btn = document.getElementById('ranking-btn');
    if (btn) btn.hidden = !(state.leaderboard || []).length;
    var ranking = document.getElementById('ranking');
    if (ranking && !ranking.hidden) renderRankingList(); // stays live
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
    var text = document.getElementById('conn-text');
    if (!el || !text) return;
    el.classList.toggle('is-down', !ok);
    text.textContent = ok ? 'Live feed connected' : 'Reconnecting…';
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
    var driverSet = document.getElementById('driver-set');
    if (driverSet) { // the driver box only renders on the ingesting instance
      driverSet.addEventListener('click', function () {
        var name = document.getElementById('driver-input').value.trim();
        api('/api/current-driver', { name: name }).then(refresh);
      });
      document.getElementById('driver-clear').addEventListener('click', function () {
        document.getElementById('driver-input').value = '';
        api('/api/current-driver', { name: '' }).then(refresh);
      });
    }
  }

  var filterSel = document.getElementById('car-filter');
  if (filterSel) {
    filterSel.addEventListener('change', function () {
      carFilter = this.value;
      refresh();
    });
  }

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
