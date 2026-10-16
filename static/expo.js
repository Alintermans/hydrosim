/* HydroSim Expo screen. Two sources: /api/state (ranking, latest runs,
   stats) and /api/expo/state (what the autopilot is doing). SSE pings say
   which one changed; a 5 s poll backs both up. The screen never takes input —
   the autopilot owns the keyboard and tells us what the visitor typed. */
(function () {
  'use strict';
  var cfg = window.HS || {};
  var board = null;      // /api/state
  var stage = null;      // /api/expo/state
  var stageAt = 0;       // performance.now() when `stage` arrived
  var lastStageKey = '';

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }
  function setHTML(el, html) {
    if (el.__last === html) return;   // no DOM churn, no re-played animations
    el.__last = html;
    el.innerHTML = html;
  }
  function key(name) { return (name || '').trim().toLowerCase(); }
  function fmt(ms) {
    if (ms == null || ms < 0) return '–:––.–––';
    var m = Math.floor(ms / 60000), s = Math.floor(ms % 60000 / 1000), x = ms % 1000;
    return m + ':' + (s < 10 ? '0' : '') + s + '.' + ('00' + x).slice(-3);
  }
  function fmtClock(ms) {   // running clock: tenths are enough and calmer
    var m = Math.floor(ms / 60000), s = Math.floor(ms % 60000 / 1000),
        t = Math.floor(ms % 1000 / 100);
    return m + ':' + (s < 10 ? '0' : '') + s + '.' + t;
  }
  function gap(ms) { return (ms >= 0 ? '+' : '−') + (Math.abs(ms) / 1000).toFixed(3); }

  function get(path) {
    return fetch(path, { headers: { 'Authorization': 'Bearer ' + cfg.token },
                         cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function conn(ok) {
    var el = document.getElementById('x-conn');
    el.classList.toggle('x-conn--down', !ok);
    document.getElementById('x-conn-text').textContent = ok ? 'Live' : 'Verbinding herstellen…';
  }

  function loadBoard() {
    return get('/api/state?event=' + encodeURIComponent(cfg.event))
      .then(function (s) { board = s; conn(true); render(); })
      .catch(function () { conn(false); });
  }
  function loadStage() {
    return get('/api/expo/state')
      .then(function (s) { stage = s; stageAt = performance.now(); render(); })
      .catch(function () { conn(false); });
  }

  // ---- ranking --------------------------------------------------------
  // The visitor's lap (named or not yet) as a row: while the autopilot is
  // between "finished" and "result" it's highlighted — and inserted as a
  // ghost when it isn't on the board yet because it has no name.
  function youEntry() {
    if (!stage || !stage.result) return null;
    if (['finished', 'naming', 'result'].indexOf(stage.phase) < 0) return null;
    var lap = stage.result.lap;
    return { lap: lap, name: lap.driver_name || stage.name || '',
             ghost: !lap.driver_name };
  }

  function rankedRows() {
    var rows = (board && board.leaderboard || []).map(function (l) {
      return { name: l.driver_name, ms: l.lap_ms, you: false };
    });
    var you = youEntry();
    if (you) {
      var k = key(you.name);
      if (!you.ghost) {
        rows.forEach(function (r) { if (key(r.name) === k) r.you = true; });
      } else {
        rows = rows.filter(function (r) { return !k || key(r.name) !== k; });
        rows.push({ name: you.name, ms: you.lap.lap_ms, you: true, ghost: true });
        rows.sort(function (a, b) { return a.ms - b.ms; });
      }
    }
    return rows;
  }

  function rowHeight(list) {
    if (!list.__rowH) {
      var probe = document.createElement('li');
      probe.className = 'x-row';
      probe.style.visibility = 'hidden';
      probe.innerHTML = '<span class="x-row__rank">1</span>';
      list.appendChild(probe);
      var gapPx = parseFloat(getComputedStyle(list).rowGap) || 0;
      list.__rowH = probe.offsetHeight + gapPx;
      list.removeChild(probe);
      list.__last = null;
    }
    return list.__rowH;
  }

  function rowHTML(r, rank, best) {
    var cls = 'x-row';
    if (rank <= 3) cls += ' x-row--p' + rank;
    if (r.you) cls += ' x-row--you';
    var name = r.ghost && !r.name ? 'Jouw ronde' : r.name;
    return '<li class="' + cls + '">' +
      '<span class="x-row__rank">' + rank + '</span>' +
      '<span class="x-row__name">' + esc(name) +
        (r.you ? '<span class="x-row__tag">JIJ</span>' : '') + '</span>' +
      '<span class="x-row__time">' + fmt(r.ms) + '</span>' +
      '<span class="x-row__gap">' + (rank === 1 ? '' : gap(r.ms - best)) + '</span></li>';
  }

  function renderBoard() {
    var list = document.getElementById('x-rows');
    var rows = rankedRows();
    document.getElementById('x-empty').hidden = rows.length > 0;
    if (!rows.length) { setHTML(list, ''); return; }
    var cap = Math.max(4, Math.floor((list.clientHeight + 4) / rowHeight(list)));
    var best = rows[0].ms;
    var hi = -1;
    rows.forEach(function (r, i) { if (r.you && hi < 0) hi = i; });
    var html = '';
    if (rows.length <= cap || hi < cap) {
      rows.slice(0, cap).forEach(function (r, i) { html += rowHTML(r, i + 1, best); });
    } else {
      // Far down the ranking: keep the podium, then a window around "you".
      var podium = 3, win = cap - podium - 1;
      var start = Math.max(podium, Math.min(hi - Math.floor(win / 2), rows.length - win));
      rows.slice(0, podium).forEach(function (r, i) { html += rowHTML(r, i + 1, best); });
      html += '<li class="x-row x-row--skip">⋯</li>';
      rows.slice(start, start + win).forEach(function (r, i) {
        html += rowHTML(r, start + i + 1, best);
      });
    }
    setHTML(list, html);
  }

  // ---- header stats + latest runs -------------------------------------
  function renderStats() {
    var lb = board.leaderboard || [];
    var cells = [['Bestuurders', board.stats ? board.stats.drivers : lb.length],
                 ['Ritten vandaag', board.stats ? board.stats.laps_today : 0]];
    if (lb.length) cells.unshift(['Record', fmt(lb[0].lap_ms)]);
    setHTML(document.getElementById('x-stats'), cells.map(function (c) {
      return '<div class="x-stat"><span class="x-stat__label">' + c[0] +
        '</span><span class="x-stat__value">' + esc(c[1]) + '</span></div>';
    }).join(''));
  }

  function rankOf(lap) {
    var k = key(lap.driver_name);
    var faster = (board.leaderboard || []).filter(function (l) {
      return l.lap_ms < lap.lap_ms && key(l.driver_name) !== k;
    }).length;
    return faster + 1;
  }

  function renderRecent() {
    var runs = (board.recent || []).filter(function (l) { return l.valid; }).slice(0, 6);
    setHTML(document.getElementById('x-recent'), runs.map(function (l) {
      var rank = rankOf(l);
      return '<li class="x-run' + (rank <= 3 ? ' x-run--top' : '') + '">' +
        '<span class="x-run__top"><span class="x-run__rank">P' + rank + '</span>' +
        '<span>' + fmt(l.lap_ms) + '</span></span>' +
        '<span class="x-run__name">' + esc(l.driver_name || 'naam volgt…') + '</span></li>';
    }).join(''));
  }

  // ---- stage ----------------------------------------------------------
  function fact(label, value) {
    return '<div class="x-fact"><span class="x-fact__label">' + label +
      '</span><span class="x-fact__value">' + value + '</span></div>';
  }
  function leaderFact() {
    var lb = board && board.leaderboard || [];
    if (!lb.length) return fact('Te kloppen', 'Nog niemand <small>wees de eerste!</small>');
    return fact('Te kloppen', fmt(lb[0].lap_ms) + '<small>' + esc(lb[0].driver_name) + '</small>');
  }
  function todayFact() {
    var today = new Date().toDateString();
    var lb = (board && board.leaderboard || []).filter(function (l) {
      return new Date(l.recorded_at).toDateString() === today;
    });
    if (!lb.length) return '';
    return fact('Snelste vandaag', fmt(lb[0].lap_ms) + '<small>' + esc(lb[0].driver_name) + '</small>');
  }
  function placeHTML(res) {
    return '<div class="x-place"><span class="x-place__p">P' + res.rank + '</span>' +
      '<span class="x-place__of">van ' + res.total + ' bestuurder' +
      (res.total === 1 ? '' : 's') + '</span></div>';
  }
  function resultFacts(res) {
    var out = fact('Rondetijd', fmt(res.lap.lap_ms));
    if (res.leader && !res.record) out += fact('Achterstand op P1', gap(res.gap_ms));
    if (res.total > 1) out += fact('Sneller dan', res.beaten_pct + '% <small>van de bestuurders</small>');
    return '<div class="x-facts">' + out + '</div>';
  }

  function stageHTML() {
    var st = stage;
    var res = st && st.result;
    var offline = !st || st.age_s == null || st.age_s > 20;
    if (offline) {
      return '<p class="kicker kicker--sky"><span>Even geduld</span></p>' +
        '<h2 class="x-big">De simulator <em>start op</em>…</h2>' +
        '<p class="x-sub">Zo meteen kan je rijden.</p>';
    }
    switch (st.phase) {
      case 'starting':
        return '<p class="kicker kicker--heat"><span>Maak je klaar</span></p>' +
          '<h2 class="x-big">Handen aan het <em>stuur</em></h2>' +
          '<p class="x-sub">De Radical wordt klaargezet op Spa-Francorchamps. ' +
          'Rechterpedaal = gas, middelste pedaal = rem. Schakelen gaat vanzelf.</p>' +
          '<div class="x-bar x-bar--load"><span class="x-bar__fill"></span></div>';
      case 'driving':
        if (st.elapsed_ms == null) {
          return '<p class="kicker kicker--heat"><span>Op de baan</span></p>' +
            '<h2 class="x-big">Rij naar de <em>startlijn</em></h2>' +
            '<p class="x-sub">De tijd begint te lopen zodra je over de streep rijdt. Gas geven!</p>' +
            '<div class="x-facts">' + leaderFact() + '</div>';
        }
        return '<p class="kicker kicker--heat"><span>Op de baan · 1 ronde</span></p>' +
          '<div id="x-clock" class="x-clock">' + fmtClock(st.elapsed_ms || 0) + '</div>' +
          '<div class="x-bar"><span class="x-bar__fill" style="width:' +
            Math.round((st.progress || 0) * 100) + '%"></span></div>' +
          '<div class="x-facts">' + leaderFact() + '</div>';
      case 'finished':
        if (!res) return '<h2 class="x-big"><em>Finish!</em></h2>';
        return '<p class="kicker kicker--heat"><span>Finish!</span></p>' +
          '<div class="x-clock x-clock--heat">' + fmt(res.lap.lap_ms) + '</div>' +
          placeHTML(res);
      case 'naming':
        if (!res) break;
        var left = st.deadline_s;
        return '<div class="x-place"><span class="x-clock x-clock--heat">' +
            fmt(res.lap.lap_ms) + '</span></div>' +
          '<p class="x-sub">Dat is <b>P' + res.rank + '</b> van ' + res.total +
            (res.record ? ' — <b>een nieuw record!</b>' : '') + '</p>' +
          '<p class="kicker kicker--sky"><span>Typ je naam op het toetsenbord</span></p>' +
          '<div class="x-name">' + (st.name ? esc(st.name) :
            '<span class="x-name__ph">Je naam</span>') + '<span class="x-caret"></span></div>' +
          '<p class="x-hint">Druk op <b>ENTER</b> om op het klassement te komen' +
            (left != null ? ' · nog <b id="x-left">' + Math.ceil(left) + '</b> s' : '') + '</p>';
      case 'result':
        if (!res) break;
        var who = res.lap.driver_name || st.name || '';
        return '<p class="kicker kicker--heat"><span>' +
            (res.record ? 'Nieuw record' : 'Goed gereden') + '</span></p>' +
          '<h2 class="x-big">Proficiat, <em>' + esc(who) + '</em>!</h2>' +
          (res.record ? '<span class="x-record">Snelste ooit op deze stand</span>' : '') +
          placeHTML(res) + resultFacts(res) +
          (res.own_best ? '<p class="x-hint">Je beste tijd blijft <b>' +
            fmt(res.own_best.lap_ms) + '</b></p>' : '');
      case 'message':
        return '<p class="kicker kicker--sky"><span>Info</span></p>' +
          '<h2 class="x-big">' + esc(st.message || 'Even geduld') + '</h2>';
    }
    // idle
    return '<p class="kicker kicker--sky"><span>Sim challenge</span></p>' +
      '<h2 class="x-big x-pulse">Druk op <span class="x-key">START</span><br>op het stuur</h2>' +
      '<p class="x-sub">Rij één ronde Spa-Francorchamps in de Radical. ' +
        'Zet jij de snelste tijd van de dag?</p>' +
      '<div class="x-facts">' + leaderFact() + todayFact() + '</div>';
  }

  function render() {
    if (!board) return;
    renderStats();
    renderBoard();
    renderRecent();
    var el = document.getElementById('x-stage');
    var phase = stage && stage.age_s != null && stage.age_s <= 20 ? stage.phase : 'offline';
    el.setAttribute('data-phase', phase);
    // The clock and countdown tick locally; strip them from the change key so
    // a heartbeat doesn't rebuild (and re-animate) the stage.
    var html = stageHTML();
    var stageKey = html.replace(/<div id="x-clock"[^<]*<\/div>/, '')
                       .replace(/<b id="x-left">\d+<\/b>/, '');
    if (stageKey !== lastStageKey) {
      lastStageKey = stageKey;
      setHTML(document.getElementById('x-stage-body'), html);
    }
  }

  // Running clock between autopilot updates (it reports ~1x per second).
  function tick() {
    if (stage && stage.phase === 'driving' && stage.elapsed_ms != null) {
      var c = document.getElementById('x-clock');
      if (c) c.textContent = fmtClock(stage.elapsed_ms + (performance.now() - stageAt));
    }
    if (stage && stage.phase === 'naming' && stage.deadline_s != null) {
      var l = document.getElementById('x-left');
      if (l) l.textContent = Math.max(0, Math.ceil(stage.deadline_s - (performance.now() - stageAt) / 1000));
    }
  }
  setInterval(tick, 100);

  var resizeT;
  window.addEventListener('resize', function () {
    clearTimeout(resizeT);
    resizeT = setTimeout(function () {
      document.getElementById('x-rows').__rowH = 0;
      render();
    }, 150);
  });

  function connect() {
    if (!window.EventSource) return;
    var es = new EventSource('/api/stream');
    es.onmessage = function (e) {
      var kind = '';
      try { kind = JSON.parse(e.data).kind; } catch (_) { /* ping */ }
      if (kind === 'expo') loadStage(); else { loadBoard(); loadStage(); }
    };
    es.onerror = function () { conn(false); };
    es.onopen = function () { conn(true); };
  }

  loadBoard().then(loadStage);
  connect();
  setInterval(function () { loadBoard(); loadStage(); }, 5000);
})();
