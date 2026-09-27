/* SVG Multicolor page. Talks to the plugin through the bridge OrcaSlicer injects:
     page -> plugin: window.orca.postMessage({action: ...})
     plugin -> page: window.orca.onMessage(callback) receives {type: ...}
   Language and theme are OrcaSlicer's; defaults live in the plugin's Config tab.
   No external resources: the page must work offline inside OrcaSlicer. */
(function () {
  'use strict';

  var BOOT = window.SVGM_BOOT || {};
  var S = {
    lang: BOOT.lang || 'en',
    cat: BOOT.catalog || {},
    mode: BOOT.mode || 'page',
    settings: {},
    filaments: [],
    filSig: null,
    svg: '',
    analysis: null,
    rows: {},            // per color: {name, nameEdited, filament, filEdited, enabled, suggested}
    busy: null,
    quiet: false,
    pendingAnalyze: null,
    view: 'auto',        // auto = on the object when there is a surface, else the result
    target: 'plate',
    plate: null,
    plateApply: false,
    plateReadAt: 0,
    faces: null,         // {project, object_id, mtime, list, chosen}
    faceWant: null,      // the surface the user picked, found again after a new save
    facesApply: false,
    pendingFaces: null,
    lastDone: null,
    status: { key: 'status.ready', params: null, cls: '', raw: null }
  };
  var LIMIT = 64 * 1024 * 1024;
  var REANALYZE = ['size_mode', 'size_mm', 'max_colors', 'merge_tolerance', 'include_strokes',
                   'precision_mm', 'min_area_mm2', 'min_detail_mm', 'base_thickness_mm',
                   'base_margin_mm', 'base_shape'];
  var PLACEMENT = ['rotation', 'apply_width_mm', 'fit'];

  function $(id) { return document.getElementById(id); }
  function each(sel, fn) { Array.prototype.forEach.call(document.querySelectorAll(sel), fn); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function basename(p) { return String(p || '').split(/[\\/]/).pop(); }
  function num(v, d) { var n = parseFloat(v); return isFinite(n) ? n : d; }
  function fmt(n, d) {
    return Number(n).toLocaleString(S.lang.replace('_', '-'), { maximumFractionDigits: d == null ? 1 : d });
  }

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
    each('[data-i18n-title]', function (e) { e.title = t(e.getAttribute('data-i18n-title')); });
    each('[data-i18n-aria]', function (e) { e.setAttribute('aria-label', t(e.getAttribute('data-i18n-aria'))); });
    renderSvgLine();
    renderStatus();
    renderBaseFilament();
    renderColors();
    renderPlate();
    renderFaces();
    updateTarget();
    renderAnalysisInfo();
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
    if (!post) { console.warn('[svg multicolor] no channel to the plugin'); return; }
    try { post(msg); } catch (e) { console.warn('[svg multicolor] postMessage', e); }
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
    S.status = { key: key, params: params || null, cls: cls || '', raw: raw == null ? null : raw };
    renderStatus();
  }
  function renderStatus() {
    var st = S.status, txt = $('status_text');
    txt.textContent = st.raw != null ? st.raw : t(st.key, st.params);
    txt.className = 'status-text' + (st.cls === 'err' ? ' err' : '');
    txt.title = txt.textContent;
    $('status_dot').className = 'dot' + (S.busy ? ' busy' : st.cls === 'ok' ? ' ok' : st.cls === 'err' ? ' err' : '');
  }
  function setBar(pct) {
    var bar = $('bar');
    if (pct == null) { bar.className = 'bar'; $('bar_fill').style.width = '0'; return; }
    if (pct < 0) { bar.className = 'bar indeterminate'; $('bar_fill').style.width = ''; return; }
    bar.className = 'bar'; $('bar_fill').style.width = Math.max(2, pct) + '%';
    bar.setAttribute('aria-valuenow', String(pct));
  }

  var ACTION_BUTTONS = ['btn_run', 'btn_svg_pick', 'btn_plate_read'];
  function begin(action, key, params) {
    S.busy = action;
    ACTION_BUTTONS.forEach(function (id) { $(id).disabled = true; });
    if (key) setStatus(key, params, 'busy'); else renderStatus();
    setBar(-1);
    if (action === 'analyze') $('preview_spin').hidden = false;
  }
  function end() {
    S.busy = null;
    ACTION_BUTTONS.forEach(function (id) { $(id).disabled = false; });
    $('preview_spin').hidden = true;
    setBar(null);
    renderStatus();
    if (S.pendingAnalyze) { var q = S.pendingAnalyze; S.pendingAnalyze = null; analyze(q); }
    else if (S.pendingFaces) { S.pendingFaces = null; requestFaces(false); }
  }

  /* ------------------------------------------------------------ form */
  function readOpt(e) {
    if (e.type === 'checkbox') return e.checked;
    if (e.type === 'number' || e.type === 'range') return e.value === '' ? 0 : num(e.value, 0);
    if (e.id === 'base_filament') return parseInt(e.value, 10) || 1;
    if (e.id === 'rotation') return num(e.value, 0);
    return e.value;
  }
  function options() {
    var o = {};
    each('[data-opt]', function (e) { o[e.getAttribute('data-opt')] = readOpt(e); });
    return o;
  }
  function fillForm(s) {
    each('[data-opt]', function (e) {
      var k = e.getAttribute('data-opt');
      if (!(k in s)) return;
      var v = s[k];
      if (e.type === 'checkbox') e.checked = !!v;
      else if (k === 'apply_width_mm') e.value = v ? v : '';
      else e.value = v;
    });
    S.target = s.target === 'new' ? 'new' : 'plate';
    each('input[name=target]', function (r) { r.checked = r.value === S.target; });
    $('size_mm').disabled = $('size_mode').value === 'original';
    updateMergeOut();
  }
  function updateMergeOut() {
    var v = num($('merge_tolerance').value, 0);
    $('merge_out').textContent = v > 0 ? 'ΔE ' + v : t('opt.off');
  }
  // the page remembers what you change, in the plugin's own config
  var saveTimer = null;
  function rememberSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      var s = options();
      s.target = S.target;
      send({ action: 'save_settings', settings: s, quiet: true });
    }, 800);
  }

  function updateTarget() {
    $('target_plate').hidden = S.target !== 'plate';
    $('target_new').hidden = S.target !== 'new';
    $('base_opts').hidden = num($('base_thickness_mm').value, 0) <= 0;
    $('btn_run_label').textContent = t(S.target === 'plate' ? 'out.apply_plate' : 'out.add_plate');
    $('view_place').hidden = S.target !== 'plate';
  }

  /* ------------------------------------------------------------ filaments */
  function filamentList() {
    if (S.filaments.length) return S.filaments;
    var out = [];
    for (var i = 1; i <= 16; i++) out.push({ n: i, name: '', color: '' });
    return out;
  }
  function filamentOptions(select, value) {
    select.textContent = '';
    filamentList().forEach(function (f) {
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
    for (var i = 0; i < S.filaments.length; i++) if (S.filaments[i].n === n) return S.filaments[i].color || '';
    return '';
  }
  function renderBaseFilament() {
    filamentOptions($('base_filament'), S.settings.base_filament || $('base_filament').value || 1);
  }

  /* ------------------------------------------------------------ renderers */
  function renderSvgLine() {
    var line = $('svg_line'), name = $('svg_name');
    line.className = 'file-line' + (S.svg ? ' has' : '');
    name.textContent = S.svg ? basename(S.svg) : t('src.none');
    line.title = S.svg || '';
  }

  function renderAnalysisInfo() {
    var a = S.analysis, dims = $('dims'), warn = $('warnings');
    var view = currentView(), face = selectedFace();
    dims.className = 'dims';
    if (view === 'placement' && face) {
      var fit = placement(a, face, rotation());
      var where = faceLabel(face, S.faces.list);
      dims.textContent = fit
        ? t('prev.on_face', { design: t('prev.dims', { w: fmt(fit.w), h: fmt(fit.h) }), face: where })
        : where;
      dims.title = dims.textContent;
      if (fit && (fit.w > face.w + 0.05 || fit.h > face.h + 0.05)) {
        dims.className = 'dims warn';
        dims.title += '\n' + t('warn.exceeds_face', { w: fmt(face.w), h: fmt(face.h) });
      }
    }
    if (!a) {
      if (view !== 'placement' || !face) { dims.textContent = ''; dims.title = ''; }
      warn.hidden = true;
      return;
    }
    if (view !== 'placement' || !face) {
      var parts = [t('prev.dims', { w: fmt(a.size_mm[0]), h: fmt(a.size_mm[1]) })];
      parts.push(a.raw_count !== a.colors.length
        ? t('prev.colors_reduced', { n: a.colors.length, raw: a.raw_count })
        : t('prev.colors', { n: a.colors.length }));
      dims.textContent = parts.join('  ·  ');
      dims.title = dims.textContent;
    }
    warn.textContent = '';
    (a.warnings || []).forEach(function (w) { warn.appendChild(el('li', null, w)); });
    warn.hidden = !(a.warnings || []).length;
  }

  function currentView() {
    var v = S.view;
    var canPlace = S.target === 'plate' && !!selectedFace();
    if (v === 'auto') v = canPlace ? 'placement' : 'result';
    if (v === 'placement' && !canPlace) v = 'result';
    if (v === 'original' && !(S.analysis && S.analysis.original)) v = 'result';
    return v;
  }

  function renderPreview() {
    var a = S.analysis, res = $('preview_result'), img = $('preview_original');
    var view = currentView();
    each('#view_seg button', function (b) {
      b.setAttribute('aria-selected', String(b.getAttribute('data-view') === view));
    });
    $('preview_empty').hidden = !!a || view === 'placement';
    $('preview_place').hidden = view !== 'placement';
    if (view === 'placement') renderPlacement();
    renderAnalysisInfo();
    if (!a) { res.hidden = true; img.hidden = true; return; }
    if (res.getAttribute('data-src') !== a.svg + a.preview.length) {
      res.innerHTML = a.preview;   // SVG built by the plugin: numbers and hex colors only
      res.setAttribute('data-src', a.svg + a.preview.length);
    }
    if (a.original) img.src = 'data:image/svg+xml;base64,' + a.original;
    else img.removeAttribute('src');
    res.hidden = view !== 'result';
    img.hidden = view !== 'original';
  }

  function highlight(color) {
    ['preview_result', 'preview_place'].forEach(function (id) {
      var stage = $(id);
      stage.classList.toggle('focus', !!color);
      Array.prototype.forEach.call(stage.querySelectorAll('path[data-key]'), function (p) {
        p.classList.toggle('on', p.getAttribute('data-key') === color);
      });
    });
    each('.crow', function (r) { r.classList.toggle('hl', r.getAttribute('data-color') === color); });
  }

  /* ------------------------------------------------------------ surfaces */
  function rotation() { return num($('rotation').value, 0); }

  function facesMatchItem() {
    var f = S.faces, item = plateItem();
    return !!(f && S.plate && item && f.project === S.plate.project && f.object_id === item.object_id);
  }
  function facesFresh() { return facesMatchItem() && S.faces.mtime === S.plate.project_mtime; }

  function selectedFace() {
    if (!facesMatchItem()) return null;
    var list = S.faces.list;
    for (var i = 0; i < list.length; i++) if (list[i].id === S.faces.chosen) return list[i];
    return null;
  }

  function faceName(f) {
    var name = t('face.' + f.dir);
    return f.inner ? t('face.inner', { dir: name }) : name;
  }
  function faceLabel(f, list) {
    var s = t('face.label', { dir: faceName(f), w: fmt(f.w), h: fmt(f.h) });
    var twin = list.some(function (g) { return g !== f && g.dir === f.dir && !g.inner === !f.inner; });
    return twin ? s + ' · ' + t('face.at_z', { z: fmt(f.z) }) : s;
  }

  function renderFaces() {
    var sel = $('face_select'), f = S.faces;
    sel.textContent = '';
    if (!facesMatchItem() || !f.list.length) {
      var none = el('option', null, '—'); none.value = '';
      sel.appendChild(none);
      sel.disabled = true;
      sel.title = facesMatchItem() ? t('error.no_faces') : '';
      return;
    }
    var seen = {};
    f.list.forEach(function (x) {
      var label = faceLabel(x, f.list);
      seen[label] = (seen[label] || 0) + 1;
      if (seen[label] > 1) label += ' (' + seen[label] + ')';
      var o = el('option', null, label);
      o.value = String(x.id);
      sel.appendChild(o);
    });
    sel.disabled = false;
    sel.value = String(f.chosen);
    sel.title = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].textContent : '';
  }

  // the same scale the plugin will use (engine.apply_to_project)
  function placement(a, face, rot) {
    if (!a || !a.box_mm || !(a.box_mm[0] > 0 && a.box_mm[1] > 0)) return null;
    var W = a.box_mm[0], H = a.box_mm[1];
    var r = rot * Math.PI / 180, c = Math.abs(Math.cos(r)), s = Math.abs(Math.sin(r));
    var rw = W * c + H * s, rh = W * s + H * c;
    var width = num($('apply_width_mm').value, 0);
    var k = width > 0 ? width / W : num(S.settings.apply_fraction, 0.85) * Math.min(face.w / rw, face.h / rh);
    return { k: k, w: rw * k, h: rh * k };
  }

  var designCache = { src: null, html: '' };
  function designPaths(a) {
    var src = a.svg + ':' + a.preview.length;
    if (designCache.src !== src) {
      var paths = a.preview.match(/<path [^>]*\/>/g) || [];
      designCache = { src: src, html: paths.filter(function (p) {
        return p.indexOf('data-key="base"') < 0;           // the base plate is not applied
      }).join('') };
    }
    return designCache.html;
  }

  function renderPlacement() {
    var box = $('preview_place'), face = selectedFace(), a = S.analysis;
    if (!face) { box.textContent = ''; box.removeAttribute('data-key'); return; }
    var rot = rotation(), fit = placement(a, face, rot);
    var key = [S.faces.project, S.faces.mtime, face.id, rot, fit ? fit.k.toFixed(6) : '',
               a ? a.svg + a.preview.length : ''].join('|');
    if (box.getAttribute('data-key') === key) return;
    box.setAttribute('data-key', key);
    var b = face.bounds.slice();
    if (fit) {   // the design is centered on the face: show what falls outside too
      b = [Math.min(b[0], -fit.w / 2), Math.min(b[1], -fit.h / 2),
           Math.max(b[2], fit.w / 2), Math.max(b[3], fit.h / 2)];
    }
    var w = b[2] - b[0], h = b[3] - b[1], pad = Math.max(w, h) * 0.06 + 1;
    var vb = [b[0] - pad, b[1] - pad, w + 2 * pad, h + 2 * pad].map(function (n) { return n.toFixed(2); });
    var design = '';
    if (fit) {
      // the plugin rotates counterclockwise with Y up; this SVG has Y down
      var g = '<g transform="rotate(' + (-rot) + ') scale(' + fit.k.toFixed(6) + ')">' + designPaths(a) + '</g>';
      design = '<g class="ghost">' + g + '</g><g clip-path="url(#svgm_face)">' + g + '</g>';
    }
    // outlines and paths come from the plugin: numbers and hex colors only
    box.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + vb.join(' ') +
      '" preserveAspectRatio="xMidYMid meet"><defs><clipPath id="svgm_face">' +
      '<path clip-rule="evenodd" d="' + face.outline + '"/></clipPath></defs>' +
      '<path class="face" fill-rule="evenodd" d="' + face.outline + '"/>' + design +
      '<path class="face-edge" d="' + face.outline + '"/></svg>';
  }

  function requestFaces(thenApply) {
    var item = plateItem();
    if (!S.plate || !S.plate.project || !item || !item.object_id) return false;
    if (S.busy && S.busy !== 'plate') { S.pendingFaces = true; return true; }
    S.facesApply = !!thenApply;
    begin('faces', thenApply ? 'status.reading_plate' : null);
    send({ action: 'faces', project: S.plate.project, object_id: item.object_id });
    return true;
  }
  function ensureFaces() { if (!facesFresh()) requestFaces(false); }

  function onFaces(m) {
    var list = m.faces || [], want = S.faceWant, keep = null;
    if (want && want.project === m.project && want.object_id === m.object_id) {
      keep = list.filter(function (x) {
        return x.dir === want.dir && Math.abs(x.w - want.w) < 0.6 && Math.abs(x.h - want.h) < 0.6 &&
               Math.abs(x.z - want.z) < 0.6;
      })[0] || null;
    }
    S.faces = { project: m.project, object_id: m.object_id, mtime: m.mtime, list: list,
                chosen: keep ? keep.id : m.default };
    renderFaces();
    if (S.facesApply) { S.facesApply = false; sendApply(); renderPreview(); return; }
    end();
    renderPreview();
  }

  function sendApply() {
    var item = plateItem(), face = selectedFace();
    var msg = jobMessage('apply');
    msg.project = S.plate.project;
    msg.object_id = item.object_id;
    msg.face_id = face ? face.id : null;
    begin('apply', 'status.applying');
    send(msg);
  }

  function renderColors() {
    var box = $('colors'), a = S.analysis;
    box.textContent = '';
    $('colors_empty').hidden = !!(a && a.colors.length);
    if (!a || !a.colors.length) {
      $('colors_count').textContent = '';
      $('colors_note').hidden = true;
      $('btn_auto_fil').hidden = true;
      return;
    }
    a.colors.forEach(function (c) {
      var st = S.rows[c.color];
      var row = el('div', 'crow' + (st.enabled ? '' : ' off'));
      row.setAttribute('role', 'listitem');
      row.setAttribute('data-color', c.color);

      var use = el('input'); use.type = 'checkbox'; use.checked = st.enabled;
      use.setAttribute('aria-label', t('col.use', { name: st.name }));
      use.addEventListener('change', function () {
        st.enabled = use.checked; row.classList.toggle('off', !use.checked); renderColorsNote();
      });

      var sw = el('div', 'c-sw'); sw.style.background = c.color; sw.title = c.color;

      var name = el('input'); name.type = 'text'; name.value = st.name; name.spellcheck = false;
      name.setAttribute('aria-label', t('col.name'));
      name.addEventListener('input', function () { st.name = name.value; st.nameEdited = true; });

      var fil = el('div', 'c-fil');
      var fsw = el('i', 'fsw');
      var sel = el('select'); sel.setAttribute('aria-label', t('col.filament'));
      filamentOptions(sel, st.filament);
      var paint = function () {
        var col = filamentColor(parseInt(sel.value, 10));
        fsw.className = 'fsw' + (col ? '' : ' none');
        fsw.style.background = col || '';
        fsw.title = col ? t('col.filament_color', { color: col }) : '';
      };
      sel.addEventListener('change', function () {
        st.filament = parseInt(sel.value, 10); st.filEdited = true; paint(); renderColorsNote();
      });
      paint();
      fil.appendChild(fsw); fil.appendChild(sel);

      var pct = el('span', 'c-pct', fmt(c.area_pct, c.area_pct < 1 ? 2 : 1) + '%');
      pct.title = t('col.area', { mm2: fmt(c.area_mm2) });
      var meta = el('div', 'c-meta');
      meta.appendChild(el('span', null, t('col.shapes', { n: c.shapes })));
      if (c.merged && c.merged.length) {
        var m = el('span', 'tag', t('col.merged', { n: c.merged.length })); m.title = c.merged.join('  ');
        meta.appendChild(m);
      }
      if (c.background) {
        var b = el('span', 'tag bg', t('col.background')); b.title = t('col.background_hint');
        meta.appendChild(b);
      }
      var line2 = el('div', 'c-line2');
      line2.appendChild(fil); line2.appendChild(meta);

      row.appendChild(use); row.appendChild(sw); row.appendChild(name); row.appendChild(pct); row.appendChild(line2);
      row.addEventListener('mouseenter', function () { highlight(c.color); });
      row.addEventListener('mouseleave', function () { highlight(null); });
      row.addEventListener('focusin', function () { highlight(c.color); });
      row.addEventListener('focusout', function () { highlight(null); });
      box.appendChild(row);
    });
    $('btn_auto_fil').hidden = !S.filaments.some(function (f) { return !!f.color; });
    renderColorsNote();
  }

  function renderColorsNote() {
    var a = S.analysis, note = $('colors_note');
    if (!a) { note.hidden = true; return; }
    var on = a.colors.filter(function (c) { return S.rows[c.color].enabled; });
    $('colors_count').textContent = on.length + '/' + a.colors.length;
    var used = {};
    on.forEach(function (c) { used[S.rows[c.color].filament] = 1; });
    var nFil = S.filaments.length;
    var beyond = nFil && Object.keys(used).some(function (n) { return parseInt(n, 10) > nFil; });
    var shared = Object.keys(used).length < on.length;
    note.textContent = beyond ? t('col.beyond_filaments', { n: nFil }) : shared ? t('col.shared') : '';
    note.hidden = !(beyond || shared);
  }

  function mergeRows(colors) {
    var rows = {};
    colors.forEach(function (c) {
      var old = S.rows[c.color];
      rows[c.color] = {
        name: old && old.nameEdited ? old.name : c.name,
        nameEdited: !!(old && old.nameEdited),
        filament: old && old.filEdited ? old.filament : c.filament,
        filEdited: !!(old && old.filEdited),
        enabled: old ? old.enabled : true,
        suggested: c.filament
      };
    });
    S.rows = rows;
  }

  function renderPlate() {
    var m = S.plate, sel = $('plate_object'), state = $('plate_state');
    var prev = sel.value;
    sel.textContent = '';
    if (!m) { state.textContent = ''; state.className = 'note'; return; }
    var objs = m.objects || [];
    objs.forEach(function (o, i) {
      var size = o.size ? o.size.map(function (v) { return fmt(v); }).join(' × ') + ' mm' : '';
      var label = o.name + (size ? ' · ' + size : '');
      if (m.project && !o.object_id) label += '  (' + t('plate.not_saved') + ')';
      var opt = el('option', null, label);
      opt.value = String(i);
      opt.disabled = !o.object_id;
      sel.appendChild(opt);
    });
    if (!objs.length) {
      var none = el('option', null, t('status.plate_empty')); none.value = ''; none.disabled = true;
      sel.appendChild(none);
    }
    if (prev && sel.querySelector('option[value="' + prev + '"]:not([disabled])')) sel.value = prev;
    else {
      var first = sel.querySelector('option:not([disabled])');
      if (first) sel.value = first.value;
    }
    var text, cls;
    if (!objs.length) { text = t('status.plate_empty'); cls = 'err'; }
    else if (!m.project) { text = t('status.plate_unsaved'); cls = 'err'; }
    else if (m.project_error) { text = m.project_error; cls = 'err'; }
    else if (m.dirty) { text = t('apply.dirty'); cls = 'warn'; }
    else { text = t('plate.project', { name: basename(m.project) }); cls = 'ok'; }
    state.textContent = text;
    state.className = 'note ' + cls;
    state.title = m.project || '';
  }

  /* ------------------------------------------------------------ actions */
  function analyze(opt) {
    opt = opt || {};
    if (!S.svg) { if (!opt.quiet) setStatus('error.no_svg', null, 'err'); return; }
    if (S.busy) { S.pendingAnalyze = opt; return; }
    S.quiet = !!opt.quiet;
    begin('analyze', opt.quiet ? null : 'status.analyzing', { name: basename(S.svg) });
    send({ action: 'analyze', svg: S.svg, options: options(),
           filaments: S.filaments.length ? S.filaments : null });
  }
  var reTimer = null;
  function scheduleAnalyze() {
    if (!S.svg) return;
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

  function jobMessage(action) {
    return { action: action, svg: S.svg, options: options(), colors: colorsPayload(), reopen: true,
             filaments: S.filaments.length ? S.filaments : null };
  }

  function run() {
    if (S.busy) return;
    if (!S.svg) { setStatus('error.no_svg', null, 'err'); return; }
    if (reTimer || !S.analysis || S.analysis.svg_input !== S.svg) {
      clearTimeout(reTimer); reTimer = null;
      analyze();                   // the colors must be on screen before anything is built
      return;
    }
    $('btn_open_folder').hidden = true;
    if (S.target === 'plate') { readPlate(true); return; }
    begin('generate', 'status.generating');
    send(jobMessage('generate'));
  }

  function readPlate(thenApply) {
    if (S.busy) return;
    S.plateApply = !!thenApply;
    S.plateReadAt = Date.now();
    begin('plate', thenApply ? 'status.reading_plate' : null);
    send({ action: 'plate' });
  }

  function plateItem() {
    var sel = $('plate_object');
    if (!S.plate || !sel.value) return null;
    return (S.plate.objects || [])[parseInt(sel.value, 10)] || null;
  }

  function pick() {
    if (S.busy) return;
    $('pick_fallback').hidden = true;
    begin('pick', 'status.picking');
    var dir = S.svg ? S.svg.replace(/[\\/][^\\/]*$/, '') : '';
    send({ action: 'pick', kind: 'svg', initial: dir });
  }

  function upload(input) {
    var f = input.files && input.files[0];
    input.value = '';
    if (!f) return;
    if (f.size > LIMIT) { setStatus('error.too_big', null, 'err'); return; }
    var r = new FileReader();
    r.onload = function () {
      begin('upload', 'status.uploading', { name: f.name });
      send({ action: 'upload', kind: 'svg', name: f.name, data: r.result, binary: false });
    };
    r.onerror = function () { setStatus('error.read_file', null, 'err'); };
    r.readAsText(f);
  }

  function useSvg(path) {
    S.svg = path;
    $('pick_fallback').hidden = true;
    renderSvgLine();
    analyze();
  }

  /* ------------------------------------------------------------ messages */
  function receive(data) {
    var m = data;
    if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { return; } }
    if (!m || typeof m !== 'object') return;
    switch (m.type) {
      case 'init': onInit(m); break;
      case 'i18n': S.cat = m.catalog || S.cat; S.lang = m.lang || S.lang; applyI18n(); break;
      case 'filaments': onFilaments(m); break;
      case 'picked': onPicked(m); break;
      case 'analysis': onAnalysis(m); break;
      case 'plate': onPlate(m); break;
      case 'faces': onFaces(m); break;
      case 'progress':
        if (S.busy) { setBar(m.pct); if (!S.quiet && m.text) setStatus(null, null, 'busy', m.text); }
        break;
      case 'log': if (m.level !== 'info') console.warn('[svg multicolor]', m.text); break;
      case 'done': onDone(m); break;
      case 'cancelled': end(); setStatus(null, null, '', m.text); break;
      case 'saved': if (!m.ok) setStatus(null, null, 'err', m.text); break;
      case 'error':
        S.plateApply = false;
        S.facesApply = false;
        if (S.busy) end();
        if (m.action === 'pick' || m.action === 'upload') { showPickFallback(m.text); }
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
    onFilaments({ filaments: m.filaments, silent: true, init: true });
    applyI18n();
    setStatus('status.ready');
    if (S.target === 'plate') readPlate(false);
  }

  function onFilaments(m) {
    var list = (m.filaments || []).map(function (f) {
      return { n: parseInt(f.n, 10), name: f.name || '', color: f.color || '' };
    });
    var sig = JSON.stringify(list);
    var changed = sig !== S.filSig;
    S.filSig = sig;
    S.filaments = list;
    if (!changed) return;
    renderBaseFilament();
    if (!m.init && S.analysis) analyze({ quiet: true });   // new suggestions for the new filaments
    else renderColors();
  }

  function showPickFallback(text) {
    $('pick_error').textContent = text || '';
    $('pick_fallback').hidden = false;
  }

  function onPicked(m) {
    if (S.busy === 'pick' || S.busy === 'upload') end();
    if (m.failed) { showPickFallback(m.text); setStatus(null, null, 'err', m.text); return; }
    if (!m.path) { setStatus('status.pick_cancelled'); return; }
    if (m.kind === 'svg') useSvg(m.path);
  }

  function onAnalysis(m) {
    var quiet = S.quiet;
    var sameFile = S.analysis && S.analysis.svg_input === S.svg;
    m.svg_input = S.svg;
    if (!sameFile) S.rows = {};
    mergeRows(m.colors);
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

  function plateProblem(m) {
    var item = plateItem();
    if (!(m.objects || []).length) return ['status.plate_empty'];
    if (!m.project) return ['status.plate_unsaved'];
    if (m.project_error) return [null, null, m.project_error];
    if (m.dirty) return ['apply.dirty'];
    if (!item) return ['error.no_object'];
    if (!item.object_id) return ['plate.no_match', { name: item.name }];
    return null;
  }

  function onPlate(m) {
    var apply = S.plateApply;
    S.plateApply = false;
    S.plate = m;
    renderPlate();
    renderFaces();
    var problem = apply ? plateProblem(m) : null;
    if (apply && !problem) {
      // the surface list must be the one of the file that will be changed
      if (facesFresh()) sendApply(); else requestFaces(true);
      return;
    }
    end();
    renderPreview();
    if (problem) { setStatus(problem[0], problem[1], 'err', problem[2]); return; }
    ensureFaces();
  }

  function onDone(m) {
    end();
    S.lastDone = m;
    $('btn_open_folder').hidden = false;
    if (m.open_after) {
      setStatus('status.reopening', null, 'ok');
      send({ action: 'open_path', path: m.path });
    } else {
      setStatus(null, null, 'ok', m.text);
    }
  }

  // changing where the design goes shows it there
  function showPlacement() {
    if (S.target === 'plate' && selectedFace()) S.view = 'placement';
    renderPreview();
  }

  /* ------------------------------------------------------------ wiring */
  function wire() {
    $('btn_svg_pick').addEventListener('click', pick);
    $('btn_svg_upload').addEventListener('click', function (e) { e.preventDefault(); $('svg_file').click(); });
    $('svg_file').addEventListener('change', function () { upload($('svg_file')); });

    $('size_mode').addEventListener('change', function () {
      $('size_mm').disabled = $('size_mode').value === 'original';
    });
    $('merge_tolerance').addEventListener('input', updateMergeOut);
    $('base_thickness_mm').addEventListener('input', updateTarget);
    each('[data-opt]', function (e) {
      var k = e.getAttribute('data-opt');
      e.addEventListener('change', rememberSoon);
      if (REANALYZE.indexOf(k) >= 0) e.addEventListener('change', scheduleAnalyze);
      if (PLACEMENT.indexOf(k) >= 0) {
        e.addEventListener(e.tagName === 'INPUT' ? 'input' : 'change', showPlacement);
      }
    });
    each('input[name=target]', function (r) {
      r.addEventListener('change', function () {
        if (!r.checked) return;
        S.target = r.value;
        updateTarget();
        renderPreview();
        rememberSoon();
        if (S.target === 'plate' && !S.busy) readPlate(false);
      });
    });

    $('plate_object').addEventListener('change', function () {
      renderFaces();
      renderPreview();
      ensureFaces();
    });
    $('face_select').addEventListener('change', function () {
      if (!facesMatchItem()) return;
      S.faces.chosen = parseInt($('face_select').value, 10);
      var f = selectedFace();
      if (f) {
        S.faceWant = { project: S.faces.project, object_id: S.faces.object_id,
                       dir: f.dir, w: f.w, h: f.h, z: f.z };
      }
      renderFaces();
      showPlacement();
    });

    $('view_seg').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-view]'); if (!b) return;
      S.view = b.getAttribute('data-view');
      renderPreview();
    });

    $('btn_auto_fil').addEventListener('click', function () {
      if (!S.analysis) return;
      S.analysis.colors.forEach(function (c) {
        var st = S.rows[c.color]; st.filament = st.suggested; st.filEdited = false;
      });
      renderColors();
      setStatus('status.matched', null, 'ok');
    });

    $('btn_plate_read').addEventListener('click', function () { readPlate(false); });
    $('btn_run').addEventListener('click', run);
    $('btn_open_folder').addEventListener('click', function (e) {
      e.preventDefault();
      if (S.lastDone) send({ action: 'open_path', path: S.lastDone.folder });
    });

    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    });

    // coming back to this tab: the plate may have changed in the Prepare tab
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && S.target === 'plate' && !S.busy && Date.now() - S.plateReadAt > 2000) {
        readPlate(false);
      }
    });
    // OrcaSlicer does not announce filament changes; check now and then
    setInterval(function () {
      if (!S.busy && !document.hidden) send({ action: 'filaments', silent: true });
    }, 20000);
  }

  wire();
  applyI18n();
  start();
  if (S.mode === 'dev') window.__svgmUse = useSvg;   // dev server preloading
})();
