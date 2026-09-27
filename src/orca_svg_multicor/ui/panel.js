/* SVG Multicolor panel logic. Talks to Python through window.orca:
     page -> plugin: window.orca.postMessage({action: ...})
     plugin -> page: window.orca.onMessage(callback) receives {type: ...}
   No external libraries: the page must work offline inside OrcaSlicer. */
(function () {
  'use strict';

  var BOOT = window.SVGM_BOOT || {};
  var S = {
    lang: BOOT.lang || 'en',
    cat: BOOT.catalog || {},
    mode: BOOT.mode || 'page',
    settings: {},
    filaments: [],
    projectFilaments: [],
    filSig: null,
    inputs: { svgs: [], projects: [] },
    analysis: null,
    rows: {},             // per color: {name, nameEdited, filament, filEdited, enabled}
    busy: null,
    view: 'result',
    tab: 'new',
    lastDone: null,
    plateProject: '',
    status: { key: 'status.ready', params: null, cls: '' },
    logCount: 0,
    pendingAnalyze: null,
    quiet: false
  };
  var LIMIT = 64 * 1024 * 1024;
  var REANALYZE = ['size_mode', 'size_mm', 'max_colors', 'merge_tolerance', 'include_strokes',
                   'precision_mm', 'min_area_mm2', 'base_thickness_mm', 'base_margin_mm',
                   'base_shape', 'min_detail_mm'];

  function $(id) { return document.getElementById(id); }
  function each(sel, fn) { Array.prototype.forEach.call(document.querySelectorAll(sel), fn); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function basename(p) { return String(p || '').split(/[\\/]/).pop(); }
  function dirname(p) {
    var s = String(p || ''); var i = Math.max(s.lastIndexOf('\\'), s.lastIndexOf('/'));
    return i > 0 ? s.substring(0, i) : '';
  }
  function num(v, d) { var n = parseFloat(v); return isFinite(n) ? n : d; }
  function fmt(n, d) { return Number(n).toLocaleString(S.lang.replace('_', '-'), { maximumFractionDigits: d == null ? 1 : d }); }

  /* ------------------------------------------------------------ i18n */
  function t(key, params) {
    var s = S.cat[key];
    if (typeof s !== 'string' || !s) s = key;
    if (params) {
      s = s.replace(/\{(\w+)\}/g, function (m, k) {
        return Object.prototype.hasOwnProperty.call(params, k) ? String(params[k]) : m;
      });
    }
    return s;
  }

  function applyI18n() {
    document.documentElement.lang = S.lang.replace('_', '-');
    each('[data-i18n]', function (e) { e.textContent = t(e.getAttribute('data-i18n')); });
    each('[data-i18n-ph]', function (e) { e.placeholder = t(e.getAttribute('data-i18n-ph')); });
    each('[data-i18n-title]', function (e) {
      var v = t(e.getAttribute('data-i18n-title')); e.title = v; e.setAttribute('aria-label', v);
    });
    each('[data-i18n-aria]', function (e) { e.setAttribute('aria-label', t(e.getAttribute('data-i18n-aria'))); });
    updateRunLabel();
    renderStatus();
    renderFilaments();
    renderColors();
    renderAnalysisInfo();
    renderRecent();
    updateMergeOut();
  }

  /* ------------------------------------------------------------ bridge */
  var post = null;
  function findPost() {
    if (window.orca && typeof window.orca.postMessage === 'function') {
      return function (m) { window.orca.postMessage(m); };
    }
    if (window.chrome && window.chrome.webview && typeof window.chrome.webview.postMessage === 'function') {
      return function (m) { window.chrome.webview.postMessage(JSON.stringify(m)); };
    }
    return null;
  }
  function send(msg) {
    if (!post) post = findPost();
    if (!post) { logLine('e', 'no channel to the plugin'); return; }
    try { post(msg); } catch (e) { logLine('e', 'postMessage: ' + e); }
  }
  function start() {
    var tries = 0;
    (function wait() {
      var ready = window.orca && typeof window.orca.onMessage === 'function';
      if (ready || ++tries > 100) {
        if (ready) {
          window.orca.onMessage(receive);
        } else {
          window.addEventListener('message', function (ev) { receive(ev.data); });
          if (window.chrome && window.chrome.webview && window.chrome.webview.addEventListener) {
            window.chrome.webview.addEventListener('message', function (ev) { receive(ev.data); });
          }
        }
        post = findPost();
        send({ action: 'init' });
        return;
      }
      setTimeout(wait, 50);
    })();
  }

  /* ------------------------------------------------------------ status */
  function setStatus(key, params, cls, raw) {
    S.status = { key: key, params: params || null, cls: cls || '', raw: raw || null };
    renderStatus();
  }
  function renderStatus() {
    var st = S.status, txt = $('status_text');
    txt.textContent = st.raw != null ? st.raw : t(st.key, st.params);
    txt.className = 'status-text' + (st.cls === 'err' ? ' err' : '');
    $('status_dot').className = 'dot' + (S.busy ? ' busy' : st.cls === 'ok' ? ' ok' : st.cls === 'err' ? ' err' : '');
  }
  function setBar(pct) {
    var bar = $('bar');
    if (pct == null) { bar.className = 'bar'; $('bar_fill').style.width = '0'; return; }
    if (pct < 0) { bar.className = 'bar indeterminate'; $('bar_fill').style.width = ''; return; }
    bar.className = 'bar'; $('bar_fill').style.width = Math.max(2, pct) + '%';
    bar.setAttribute('aria-valuenow', String(pct));
  }
  function logLine(level, text) {
    var pre = $('log');
    var line = el('span', level === 'w' ? 'w' : level === 'e' ? 'e' : '', text + '\n');
    pre.appendChild(line);
    while (pre.childNodes.length > 400) pre.removeChild(pre.firstChild);
    pre.scrollTop = pre.scrollHeight;
    if ((level === 'w' || level === 'e') && pre.hidden) {
      S.logCount += 1;
      $('log_count').textContent = String(S.logCount);
      $('log_count').hidden = false;
    }
  }

  var ACTION_BUTTONS = ['btn_analyze', 'btn_run', 'btn_plate', 'btn_objects', 'btn_svg_pick',
                        'btn_prj_pick', 'btn_out_pick', 'btn_svg_upload', 'btn_prj_upload'];
  function begin(action, key, params) {
    S.busy = action;
    ACTION_BUTTONS.forEach(function (id) { var b = $(id); if (b) b.disabled = true; });
    if (key) setStatus(key, params, 'busy'); else renderStatus();
    setBar(-1);
    if (action === 'analyze') $('preview_spin').hidden = false;
  }
  function end() {
    S.busy = null;
    ACTION_BUTTONS.forEach(function (id) { var b = $(id); if (b) b.disabled = false; });
    $('preview_spin').hidden = true;
    setBar(null);
    renderStatus();
    if (S.pendingAnalyze) { var q = S.pendingAnalyze; S.pendingAnalyze = null; analyze(q); }
  }

  /* ------------------------------------------------------------ form */
  function readOpt(e) {
    if (e.type === 'checkbox') return e.checked;
    if (e.type === 'number' || e.type === 'range') return e.value === '' ? 0 : num(e.value, 0);
    if (e.id === 'base_filament') return parseInt(e.value, 10) || 1;
    return e.value;
  }
  function options() {
    var o = {};
    each('[data-opt]', function (e) { o[e.getAttribute('data-opt')] = readOpt(e); });
    return o;
  }
  function fillForm(s) {
    each('[data-opt], [data-opt-setting]', function (e) {
      var k = e.getAttribute('data-opt') || e.getAttribute('data-opt-setting');
      if (!(k in s)) return;
      var v = s[k];
      if (e.type === 'checkbox') e.checked = !!v;
      else if (k === 'apply_width_mm') e.value = v ? v : '';
      else e.value = v;
    });
    $('size_mm').disabled = $('size_mode').value === 'original';
    updateMergeOut();
  }
  function updateMergeOut() {
    var v = num($('merge_tolerance').value, 0);
    $('merge_out').textContent = v > 0 ? 'ΔE ' + v : t('opt.off');
  }

  function usingProject() { return S.tab === 'apply' && S.projectFilaments.length > 0; }
  function activeFilaments() { return usingProject() ? S.projectFilaments : S.filaments; }
  function filamentList(list) {
    list = list || activeFilaments();
    if (list.length) return list;
    var out = [];
    for (var i = 1; i <= 16; i++) out.push({ n: i, name: '', color: '' });
    return out;
  }
  function filamentOptions(select, value, list) {
    select.textContent = '';
    filamentList(list).forEach(function (f) {
      var o = el('option', null, f.name ? f.n + ' · ' + f.name : String(f.n));
      o.value = String(f.n);
      if (String(value) === String(f.n)) o.selected = true;
      select.appendChild(o);
    });
    if (value && !select.value) {
      var extra = el('option', null, String(value)); extra.value = String(value); extra.selected = true;
      select.appendChild(extra);
    }
  }
  function filamentColor(n) {
    var list = activeFilaments();
    for (var i = 0; i < list.length; i++) if (list[i].n === n) return list[i].color || '';
    return '';
  }

  /* ------------------------------------------------------------ renderers */
  function renderLanguages(list, setting) {
    var sel = $('lang');
    sel.textContent = '';
    var auto = el('option', null, t('ui.language_auto')); auto.value = 'auto';
    sel.appendChild(auto);
    (list || []).forEach(function (l) {
      var o = el('option', null, l.name); o.value = l.code; sel.appendChild(o);
    });
    sel.value = setting || 'auto';
    sel.setAttribute('data-langs', JSON.stringify(list || []));
  }

  function renderRecent() {
    var sel = $('svg_recent');
    var cur = sel.value;
    sel.textContent = '';
    var none = el('option', null, S.inputs.svgs.length ? t('src.choose') : t('src.none_in_folder'));
    none.value = '';
    sel.appendChild(none);
    S.inputs.svgs.forEach(function (p) {
      var o = el('option', null, basename(p)); o.value = p; sel.appendChild(o);
    });
    sel.value = cur;
    $('recent_field').title = S.inputs.folder || '';
  }

  function renderFilaments() {
    var strip = $('fil_strip');
    var list = activeFilaments();
    $('fil_title').textContent = t(usingProject() ? 'fil.project_title' : 'fil.title');
    $('btn_fil_sync').hidden = usingProject();
    strip.textContent = '';
    if (!list.length) {
      strip.appendChild(el('span', 'hint', t('fil.none')));
    } else {
      list.forEach(function (f) {
        var chip = el('span', 'fil-chip');
        var sw = el('i', 'sw' + (f.color ? '' : ' none'));
        if (f.color) sw.style.background = f.color;
        chip.appendChild(sw);
        chip.appendChild(document.createTextNode(String(f.n)));
        chip.title = f.name + (f.color ? '  ' + f.color : '  (' + t('fil.no_color') + ')');
        strip.appendChild(chip);
      });
    }
    filamentOptions($('base_filament'), S.settings.base_filament || $('base_filament').value || 1,
                    S.filaments);
  }

  function renderAnalysisInfo() {
    var a = S.analysis;
    var dims = $('dims'), warn = $('warnings');
    if (!a) { dims.textContent = ''; warn.hidden = true; return; }
    var parts = [t('prev.dims', { w: fmt(a.size_mm[0]), h: fmt(a.size_mm[1]) })];
    parts.push(a.raw_count !== a.colors.length
      ? t('prev.colors_reduced', { n: a.colors.length, raw: a.raw_count })
      : t('prev.colors', { n: a.colors.length }));
    dims.textContent = parts.join('  ·  ');
    warn.textContent = '';
    (a.warnings || []).forEach(function (w) { warn.appendChild(el('li', null, w)); });
    warn.hidden = !(a.warnings || []).length;
  }

  function renderPreview() {
    var a = S.analysis;
    var res = $('preview_result'), img = $('preview_original');
    $('preview_empty').hidden = !!a;
    if (!a) { res.hidden = true; img.hidden = true; return; }
    if (res.getAttribute('data-src') !== a.svg + a.preview.length) {
      res.innerHTML = a.preview;   // SVG built by the plugin: numbers and hex colors only
      res.setAttribute('data-src', a.svg + a.preview.length);
    }
    if (a.original) img.src = 'data:image/svg+xml;base64,' + a.original;
    else img.removeAttribute('src');
    res.hidden = S.view !== 'result';
    img.hidden = S.view !== 'original' || !a.original;
    if (S.view === 'original' && !a.original) res.hidden = false;
  }

  function highlight(color) {
    var stage = $('preview_result');
    stage.classList.toggle('focus', !!color);
    Array.prototype.forEach.call(stage.querySelectorAll('path'), function (p) {
      p.classList.toggle('on', p.getAttribute('data-key') === color);
    });
    each('.crow', function (r) { r.classList.toggle('hl', r.getAttribute('data-color') === color); });
  }

  function renderColors() {
    var box = $('colors');
    box.textContent = '';
    var a = S.analysis;
    if (!a || !a.colors.length) { $('colors_foot').hidden = true; return; }
    var biggest = a.colors[0].area_pct || 1;
    a.colors.forEach(function (c) {
      var st = S.rows[c.color];
      var row = el('div', 'crow' + (st.enabled ? '' : ' off'));
      row.setAttribute('role', 'listitem');
      row.setAttribute('data-color', c.color);

      var use = el('input', 'c-use'); use.type = 'checkbox'; use.checked = st.enabled;
      use.setAttribute('aria-label', t('col.use', { name: st.name }));
      use.addEventListener('change', function () {
        st.enabled = use.checked; row.classList.toggle('off', !use.checked); renderColorsFoot();
      });

      var sw = el('div', 'c-sw'); sw.style.background = c.color; sw.title = c.color;

      var main = el('div', 'c-main');
      var name = el('input'); name.type = 'text'; name.value = st.name; name.spellcheck = false;
      name.setAttribute('aria-label', t('col.name'));
      name.addEventListener('input', function () { st.name = name.value; st.nameEdited = true; });
      var meta = el('div', 'c-meta');
      meta.appendChild(el('code', null, c.color));
      meta.appendChild(el('span', null, t('col.shapes', { n: c.shapes })));
      if (c.merged && c.merged.length) {
        var m = el('span', 'tag merged', t('col.merged', { n: c.merged.length }));
        m.title = c.merged.join('  ');
        meta.appendChild(m);
      }
      if (c.background) {
        var b = el('span', 'tag bg', t('col.background'));
        b.title = t('col.background_hint');
        meta.appendChild(b);
      }
      main.appendChild(name); main.appendChild(meta);

      var area = el('div', 'c-area');
      area.appendChild(el('span', null, fmt(c.area_pct, c.area_pct < 1 ? 2 : 1) + '%'));
      var track = el('div', 'track'), fill = el('span');
      fill.style.width = Math.max(2, 100 * c.area_pct / biggest) + '%';
      track.appendChild(fill); area.appendChild(track);
      area.title = t('col.area', { mm2: fmt(c.area_mm2) });

      var fil = el('div', 'c-fil');
      var fsw = el('i', 'sw');
      var sel = el('select'); sel.setAttribute('aria-label', t('col.filament'));
      filamentOptions(sel, st.filament);
      var paint = function () {
        var col = filamentColor(parseInt(sel.value, 10));
        fsw.className = 'sw' + (col ? '' : ' none');
        fsw.style.background = col || '';
        fsw.title = col ? t('col.filament_color', { color: col }) : '';
      };
      sel.addEventListener('change', function () {
        st.filament = parseInt(sel.value, 10); st.filEdited = true; paint(); renderColorsFoot();
      });
      paint();
      fil.appendChild(fsw); fil.appendChild(sel);

      row.appendChild(use); row.appendChild(sw); row.appendChild(main); row.appendChild(area); row.appendChild(fil);
      row.addEventListener('mouseenter', function () { highlight(c.color); });
      row.addEventListener('mouseleave', function () { highlight(null); });
      row.addEventListener('focusin', function () { highlight(c.color); });
      row.addEventListener('focusout', function () { highlight(null); });
      box.appendChild(row);
    });
    renderColorsFoot();
  }

  function renderColorsFoot() {
    var a = S.analysis, foot = $('colors_foot'), count = $('colors_count');
    if (!a) { foot.hidden = true; return; }
    foot.hidden = false;
    var on = a.colors.filter(function (c) { return S.rows[c.color].enabled; });
    var used = {};
    on.forEach(function (c) { used[S.rows[c.color].filament] = 1; });
    var nFil = activeFilaments().length;
    var tooMany = nFil && Object.keys(used).some(function (n) { return parseInt(n, 10) > nFil; });
    var shared = Object.keys(used).length < on.length;
    var txt = t('col.count', { on: on.length, total: a.colors.length });
    count.className = '';
    if (tooMany) { txt += '  ·  ' + t('col.beyond_filaments', { n: nFil }); count.className = 'warn'; }
    else if (shared) { txt += '  ·  ' + t('col.shared'); }
    count.textContent = txt;
    $('btn_auto_fil').hidden = !activeFilaments().some(function (f) { return !!f.color; });
  }

  function mergeRows(colors, resetFilaments) {
    var rows = {};
    colors.forEach(function (c) {
      var old = S.rows[c.color];
      rows[c.color] = {
        name: old && old.nameEdited ? old.name : c.name,
        nameEdited: !!(old && old.nameEdited),
        filament: old && old.filEdited && !resetFilaments ? old.filament : c.filament,
        filEdited: !!(old && old.filEdited && !resetFilaments),
        enabled: old ? old.enabled : true,
        suggested: c.filament
      };
    });
    S.rows = rows;
  }

  function updateRunLabel() {
    $('btn_run_label').textContent = t(S.tab === 'apply' ? 'out.apply' : 'out.generate');
  }

  /* ------------------------------------------------------------ actions */
  function currentSvg() { return $('svg_path').value.trim(); }

  function analyze(opt) {
    opt = opt || {};
    var svg = currentSvg();
    if (!svg) { if (!opt.quiet) setStatus('error.no_svg', null, 'err'); return; }
    if (S.busy) { S.pendingAnalyze = opt; return; }
    S.quiet = !!opt.quiet;
    begin('analyze', opt.quiet ? null : 'status.analyzing', { name: basename(svg) });
    var fils = activeFilaments();
    S.analyzedWith = usingProject() ? 'project' : 'orca';
    send({ action: 'analyze', svg: svg, options: options(), filaments: fils.length ? fils : null });
  }
  var reTimer = null;
  function scheduleAnalyze() {
    if (!S.analysis && !currentSvg()) return;
    clearTimeout(reTimer);
    reTimer = setTimeout(function () { reTimer = null; analyze({ quiet: true }); }, 650);
  }

  function colorsPayload() {
    if (!S.analysis) return [];
    return S.analysis.colors.map(function (c) {
      var st = S.rows[c.color];
      return { color: c.color, name: st.name, filament: st.filament, enabled: st.enabled };
    });
  }

  function run() {
    if (S.busy) return;
    var svg = currentSvg();
    if (!svg) { setStatus('error.no_svg', null, 'err'); return; }
    if (reTimer || !S.analysis || S.analysis.svg_input !== svg) {
      clearTimeout(reTimer); reTimer = null;
      // colors must be known before generating; analyze, then the user confirms
      analyze();
      setStatus('status.analyze_first', null, '');
      return;
    }
    var msg = { svg: svg, options: options(), colors: colorsPayload(),
                output_folder: $('output_folder').value.trim(),
                filaments: activeFilaments().length ? activeFilaments() : null };
    if (S.tab === 'apply') {
      var prj = $('project_path').value.trim();
      if (!prj) { setStatus('error.no_project', null, 'err'); return; }
      if (!$('object_id').value) { setStatus('error.no_object', null, 'err'); return; }
      msg.action = 'apply'; msg.project = prj; msg.object_id = $('object_id').value;
      begin('apply', 'status.applying');
    } else {
      msg.action = 'generate';
      begin('generate', 'status.generating');
    }
    $('btn_open_file').hidden = true; $('btn_open_folder').hidden = true;
    send(msg);
  }

  function listObjects() {
    var prj = $('project_path').value.trim();
    if (!prj) { setStatus('error.no_project', null, 'err'); return; }
    if (S.busy) return;
    begin('objects', 'status.reading_project', { name: basename(prj) });
    send({ action: 'objects', project: prj });
  }

  function pick(kind, initial) {
    if (S.busy) return;
    begin('pick', 'status.picking');
    send({ action: 'pick', kind: kind, initial: initial || '' });
  }

  function upload(kind, input) {
    var f = input.files && input.files[0];
    input.value = '';
    if (!f) return;
    if (f.size > LIMIT) { setStatus('error.too_big', null, 'err'); return; }
    var r = new FileReader();
    r.onload = function () {
      begin('upload', 'status.uploading', { name: f.name });
      send({ action: 'upload', kind: kind, name: f.name, data: r.result, binary: kind !== 'svg' });
    };
    r.onerror = function () { setStatus('error.read_file', null, 'err'); };
    if (kind === 'svg') r.readAsText(f); else r.readAsDataURL(f);
  }

  function saveSetting(key, value) {
    S.settings[key] = value;
    var s = {}; s[key] = value;
    send({ action: 'save_settings', settings: s, quiet: true });
  }

  /* ------------------------------------------------------------ messages */
  function receive(data) {
    var m = data;
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { logLine('', m); return; } }
    if (!m || typeof m !== 'object') return;
    switch (m.type) {
      case 'init': onInit(m); break;
      case 'i18n':
        S.cat = m.catalog || S.cat; S.lang = m.lang || S.lang;
        renderLanguages(JSON.parse($('lang').getAttribute('data-langs') || '[]'), m.lang_setting);
        applyI18n();
        if (S.analysis) analyze({ quiet: true });   // default part names are translated
        break;
      case 'inputs': S.inputs = m; renderRecent(); break;
      case 'filaments': onFilaments(m); break;
      case 'picked': onPicked(m); break;
      case 'analysis': onAnalysis(m); break;
      case 'plate': onPlate(m); break;
      case 'objects': onObjects(m); break;
      case 'progress':
        if (S.busy) { setBar(m.pct); if (!S.quiet && m.text) setStatus(null, null, 'busy', m.text); }
        break;
      case 'log': logLine(m.level === 'warn' ? 'w' : m.level === 'error' ? 'e' : '', m.text); break;
      case 'done': onDone(m); break;
      case 'cancelled': end(); setStatus(null, null, '', m.text); break;
      case 'saved':
        if (S.busy === 'upload') end();
        if (!m.ok) setStatus(null, null, 'err', m.text);
        break;
      case 'error':
        logLine('e', m.text);
        if (S.busy) end();
        setStatus(null, null, 'err', m.text);
        break;
      default: break;
    }
  }

  function onInit(m) {
    S.cat = m.catalog || S.cat;
    S.lang = m.lang || S.lang;
    S.mode = m.mode || S.mode;
    S.settings = m.settings || {};
    fillForm(S.settings);
    renderLanguages(m.languages, m.lang_setting);
    onFilaments({ filaments: m.filaments, source: m.filament_source, silent: true, init: true });
    var badge = $('mode_badge');
    badge.hidden = S.mode === 'page';
    badge.textContent = S.mode === 'dev' ? 'dev' : 'v' + m.version;
    $('app').setAttribute('data-version', m.version || '');
    applyI18n();
    setStatus('status.ready');
    logLine('', 'SVG Multicolor ' + (m.version || '') + ' · ' + S.lang + ' · ' + (m.data_dir || ''));
  }

  function onFilaments(m) {
    var list = (m.filaments || []).map(function (f) {
      return { n: parseInt(f.n, 10), name: f.name || '', color: f.color || '' };
    });
    var sig = JSON.stringify(list);
    var changed = sig !== S.filSig;
    S.filSig = sig;
    S.filaments = list;
    if (!changed && m.silent) return;
    renderFilaments();
    if (changed && !m.init) {
      logLine('', t('log.filaments', { n: list.length }));
      if (S.analysis) analyze({ quiet: true });
      else renderColors();
    }
    if (!m.silent) {
      var noColor = list.filter(function (f) { return !f.color; }).length;
      setStatus(list.length ? 'status.filaments' : 'status.no_filaments',
                { n: list.length, missing: noColor }, list.length ? 'ok' : 'err');
      list.forEach(function (f) {
        logLine('', '  ' + f.n + ': ' + f.name + '  ' + (f.color || '(' + t('fil.no_color') + ')'));
      });
    }
  }

  function onPicked(m) {
    if (S.busy === 'pick' || S.busy === 'upload') end();
    if (m.failed) { setStatus(null, null, 'err', m.text); logLine('e', m.text); return; }
    if (!m.path) { setStatus('status.pick_cancelled'); return; }
    if (m.kind === 'svg') {
      $('svg_path').value = m.path;
      $('svg_recent').value = S.inputs.svgs.indexOf(m.path) >= 0 ? m.path : '';
      analyze();
    } else if (m.kind === 'project') {
      $('project_path').value = m.path;
      listObjects();
    } else if (m.kind === 'output') {
      $('output_folder').value = m.path;
      saveSetting('output_folder', m.path);
      setStatus('status.output_folder', { path: m.path }, 'ok');
    }
  }

  function onAnalysis(m) {
    var quiet = S.quiet;
    var sameFile = S.analysis && S.analysis.svg_input === currentSvg();
    m.svg_input = currentSvg();
    if (!sameFile) S.rows = {};
    mergeRows(m.colors, false);
    S.analysis = m;
    end();
    renderPreview();
    renderAnalysisInfo();
    renderColors();
    if (!quiet) {
      setStatus(m.raw_count !== m.colors.length ? 'status.analyzed_reduced' : 'status.analyzed',
                { n: m.colors.length, raw: m.raw_count }, 'ok');
    } else if (S.status.cls !== 'err') {
      setStatus('status.updated', null, 'ok');
    }
  }

  function onPlate(m) {
    end();
    $('plate_dirty').hidden = !m.dirty;
    var objs = m.objects || [];
    objs.forEach(function (o) {
      var size = o.size ? o.size.map(function (v) { return fmt(v); }).join(' × ') + ' mm' : '?';
      logLine('', '  [' + o.index + '] ' + o.name + '  ' + size + '  ' + t('objects.parts', { n: o.parts }));
    });
    if (!objs.length) { setStatus('status.plate_empty', null, 'err'); return; }
    if (!m.project) { setStatus('status.plate_unsaved', null, 'err'); return; }
    S.plateProject = m.project;
    $('project_path').value = m.project;
    setStatus(m.dirty ? 'apply.dirty' : 'status.plate_project', { name: basename(m.project) },
              m.dirty ? 'err' : 'ok');
    listObjects();
  }

  function filamentSourceChanged() {
    renderFilaments();
    renderColors();
    var now = usingProject() ? 'project' : 'orca';
    if (S.analysis && S.analyzedWith !== now) analyze({ quiet: true });
  }

  function onObjects(m) {
    end();
    S.projectFilaments = (m.filaments || []).map(function (f) {
      return { n: parseInt(f.n, 10), name: f.name || '', color: f.color || '' };
    });
    filamentSourceChanged();
    var sel = $('object_id');
    var prev = sel.value;
    sel.textContent = '';
    (m.objects || []).forEach(function (o) {
      var opt = el('option', null, o.label); opt.value = o.id; sel.appendChild(opt);
    });
    if (!(m.objects || []).length) {
      var none = el('option', null, t('apply.no_objects')); none.value = ''; sel.appendChild(none);
      setStatus('apply.no_objects', null, 'err');
      return;
    }
    if (prev) sel.value = prev;
    if (!sel.value) sel.selectedIndex = 0;
    setStatus('status.objects', { n: m.objects.length }, 'ok');
  }

  function onDone(m) {
    end();
    S.lastDone = m;
    setStatus(null, null, 'ok', m.text);
    $('btn_open_file').hidden = false;
    $('btn_open_folder').hidden = false;
    if (m.open_after) send({ action: 'open_path', path: m.path });
  }

  /* ------------------------------------------------------------ wiring */
  function wire() {
    $('lang').addEventListener('change', function () { send({ action: 'set_language', lang: $('lang').value }); });

    $('btn_svg_pick').addEventListener('click', function () { pick('svg', dirname(currentSvg())); });
    $('btn_svg_upload').addEventListener('click', function () { $('svg_file').click(); });
    $('svg_file').addEventListener('change', function () { upload('svg', $('svg_file')); });
    $('svg_path').addEventListener('keydown', function (e) { if (e.key === 'Enter') analyze(); });
    $('svg_path').addEventListener('change', function () { if (currentSvg()) analyze(); });
    $('svg_recent').addEventListener('change', function () {
      if ($('svg_recent').value) { $('svg_path').value = $('svg_recent').value; analyze(); }
    });
    $('btn_inputs').addEventListener('click', function () { send({ action: 'inputs' }); });
    $('btn_analyze').addEventListener('click', function () { analyze(); });

    $('size_mode').addEventListener('change', function () {
      $('size_mm').disabled = $('size_mode').value === 'original';
    });
    $('merge_tolerance').addEventListener('input', updateMergeOut);
    each('[data-opt]', function (e) {
      var k = e.getAttribute('data-opt');
      if (REANALYZE.indexOf(k) >= 0) e.addEventListener('change', scheduleAnalyze);
    });

    $('view_seg').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-view]'); if (!b) return;
      S.view = b.getAttribute('data-view');
      each('#view_seg button', function (x) { x.setAttribute('aria-selected', String(x === b)); });
      renderPreview();
    });
    $('tab_seg').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-tab]'); if (!b) return;
      S.tab = b.getAttribute('data-tab');
      each('#tab_seg button', function (x) { x.setAttribute('aria-selected', String(x === b)); });
      $('tab_new').hidden = S.tab !== 'new';
      $('tab_apply').hidden = S.tab !== 'apply';
      updateRunLabel();
      filamentSourceChanged();
    });

    $('btn_fil_sync').addEventListener('click', function () { send({ action: 'filaments' }); });
    $('btn_auto_fil').addEventListener('click', function () {
      if (!S.analysis) return;
      S.analysis.colors.forEach(function (c) {
        var st = S.rows[c.color]; st.filament = st.suggested; st.filEdited = false;
      });
      renderColors();
      setStatus('status.matched', null, 'ok');
    });

    $('btn_prj_pick').addEventListener('click', function () { pick('project', dirname($('project_path').value)); });
    $('btn_prj_upload').addEventListener('click', function () { $('prj_file').click(); });
    $('prj_file').addEventListener('change', function () { upload('project', $('prj_file')); });
    $('project_path').addEventListener('change', function () { if ($('project_path').value.trim()) listObjects(); });
    $('btn_plate').addEventListener('click', function () {
      if (S.busy) return; begin('plate', 'status.reading_plate'); send({ action: 'plate' });
    });
    $('btn_objects').addEventListener('click', listObjects);

    $('btn_out_pick').addEventListener('click', function () { pick('output', $('output_folder').value); });
    $('output_folder').addEventListener('change', function () { saveSetting('output_folder', $('output_folder').value.trim()); });
    $('open_after').addEventListener('change', function () { saveSetting('open_after', $('open_after').checked); });
    $('btn_out_project').addEventListener('click', function () {
      var p = $('project_path').value.trim() || S.plateProject || currentSvg();
      var d = dirname(p);
      if (!d) { setStatus('status.no_project_folder', null, 'err'); return; }
      $('output_folder').value = d;
      saveSetting('output_folder', d);
      setStatus('status.output_folder', { path: d }, 'ok');
    });

    $('btn_run').addEventListener('click', run);
    $('btn_save_defaults').addEventListener('click', function () {
      var s = options();
      s.output_folder = $('output_folder').value.trim();
      s.open_after = $('open_after').checked;
      send({ action: 'save_settings', settings: s });
      setStatus('status.saved', null, 'ok');
    });
    $('btn_reset_defaults').addEventListener('click', function () { send({ action: 'reset_settings' }); });

    $('btn_open_file').addEventListener('click', function () {
      if (S.lastDone) send({ action: 'open_path', path: S.lastDone.path });
    });
    $('btn_open_folder').addEventListener('click', function () {
      if (S.lastDone) send({ action: 'open_path', path: S.lastDone.folder });
    });
    $('btn_log').addEventListener('click', function () {
      var pre = $('log'); pre.hidden = !pre.hidden;
      $('btn_log').setAttribute('aria-expanded', String(!pre.hidden));
      if (!pre.hidden) { S.logCount = 0; $('log_count').hidden = true; pre.scrollTop = pre.scrollHeight; }
    });

    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    });

    // OrcaSlicer does not announce filament changes; check now and then
    setInterval(function () {
      if (!S.busy && !document.hidden) send({ action: 'filaments', silent: true });
    }, 20000);

    window.addEventListener('error', function (e) {
      logLine('e', 'script: ' + e.message + ' (' + e.lineno + ')');
    });
  }

  wire();
  applyI18n();
  start();
})();
