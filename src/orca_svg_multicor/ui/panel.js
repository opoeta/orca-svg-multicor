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
    frame: { ox: 0, oy: 0 },   // the design's center on the face, mm (not saved)
    presetLayers: null,        // {lh, h1} of the printer profile in use
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
    $('preview_result').title = $('preview_place').title = t('pop.hint');
    renderSvgLine();
    renderStatus();
    renderBaseFilament();
    renderColors();
    renderPlate();
    renderFaces();
    updateTarget();
    renderAnalysisInfo();
    updateMergeOut();
    updateLayers();
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
      else if (k === 'apply_width_mm' || k === 'layer_height_mm') e.value = v ? v : '';
      else e.value = v;
    });
    S.target = s.target === 'new' ? 'new' : 'plate';
    each('input[name=target]', function (r) { r.checked = r.value === S.target; });
    updateSizeMode();
    updateLayers();
    updateMergeOut();
  }
  /* ------------------------------------------------------------ thickness in layers */
  function currentHeights() {
    var h = S.target === 'plate' ? (S.plate && S.plate.layers) : S.presetLayers;
    var lh = num($('layer_height_mm').value, 0) || (h && h.lh) || 0.2;
    return { lh: lh, h1: (h && h.h1) || lh };
  }

  // the face (or the new object) starts on the bed: its first layer is the first layer
  function onBedNow() {
    if (S.target === 'plate') {
      var f = selectedFace();
      return !!(f && f.dir === 'bottom' && !f.inner && f.z <= 0.05);
    }
    return num($('base_thickness_mm').value, 0) <= 0;
  }

  // the same plan as engine.layer_plan()
  function layerPlan() {
    var h = currentHeights(), onBed = onBedNow();
    var above = onBed && S.target === 'plate' && $('first_layer').value === 'above';
    var plan = { above: above, h1: h.h1, lh: h.lh, layers: $('thickness_mode').value === 'layers' };
    if (plan.layers) {
      plan.n = Math.max(1, Math.round(num($('thickness_layers').value, 3)));
      plan.first = onBed && !above;
      plan.mm = plan.first ? h.h1 + (plan.n - 1) * h.lh : plan.n * h.lh;
    }
    return plan;
  }

  function updateLayers() {
    var layers = $('thickness_mode').value === 'layers';
    $('thickness_mm_box').hidden = layers;
    $('thickness_layers').hidden = !layers;
    $('first_layer_row').hidden = !(S.target === 'plate' && onBedNow());
    var p = layerPlan(), parts = [], note = $('layers_note');
    if (p.layers) {
      if (p.first && p.n === 1) parts.push(t('layer.note_one', { mm: fmt(p.mm, 2) }));
      else if (p.first) parts.push(t('layer.note_first', { mm: fmt(p.mm, 2), h1: fmt(p.h1, 2), n: p.n - 1, lh: fmt(p.lh, 2) }));
      else parts.push(t('layer.note', { mm: fmt(p.mm, 2), n: p.n, lh: fmt(p.lh, 2) }));
    }
    if (p.above) parts.push(t('layer.starts', { mm: fmt(p.h1, 2) }));
    note.textContent = parts.join(' · ');
    note.hidden = !parts.length;
  }

  // the file's own size needs no number
  function updateSizeMode() {
    var original = $('size_mode').value === 'original';
    $('size_mm').disabled = original;
    $('size_mm').parentNode.hidden = original;
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
    var a = S.analysis, dims = $('dims'), warn = $('warnings'), note = $('size_note');
    // the file's own size, which "Original size" keeps
    note.hidden = !(a && a.original_mm);
    if (a && a.original_mm) {
      note.textContent = t(a.physical ? 'opt.size_file' : 'opt.size_file_px',
                           { w: fmt(a.original_mm[0]), h: fmt(a.original_mm[1]) });
    }
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
    applyRecolors();
    markPicked();
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
    setTimeout(updateLayers, 0);     // the chosen face decides the first layer row
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
  // the same scale and position the plugin will use (engine.apply_to_project):
  // never larger than the face, and moved only as far as it still fits
  function placement(a, face, rot) {
    if (!a || !a.box_mm || !(a.box_mm[0] > 0 && a.box_mm[1] > 0)) return null;
    var W = a.box_mm[0], H = a.box_mm[1];
    var r = rot * Math.PI / 180, c = Math.abs(Math.cos(r)), s = Math.abs(Math.sin(r));
    var rw = W * c + H * s, rh = W * s + H * c;
    var width = num($('apply_width_mm').value, 0);
    var kmax = Math.min(face.w / rw, face.h / rh);
    var k = width > 0 ? width / W : num(S.settings.apply_fraction, 0.85) * kmax;
    k = Math.min(k, kmax);
    var fit = { k: k, kmax: kmax, W: W, w: rw * k, h: rh * k };
    var roomX = Math.max(0, (face.w - fit.w) / 2), roomY = Math.max(0, (face.h - fit.h) / 2);
    S.frame.ox = Math.max(-roomX, Math.min(roomX, S.frame.ox));
    S.frame.oy = Math.max(-roomY, Math.min(roomY, S.frame.oy));
    return fit;
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
    var key = [S.faces.project, S.faces.mtime, face.id, a ? a.svg + a.preview.length : ''].join('|');
    if (box.getAttribute('data-key') !== key) {
      box.setAttribute('data-key', key);
      var b = face.bounds, w = b[2] - b[0], h = b[3] - b[1], pad = Math.max(w, h) * 0.06 + 1;
      var vb = [b[0] - pad, b[1] - pad, w + 2 * pad, h + 2 * pad].map(function (n) { return n.toFixed(2); });
      var design = '';
      if (a) {
        var g = '<g class="dz">' + designPaths(a) + '</g>';
        design = '<g class="ghost">' + g + '</g><g clip-path="url(#svgm_face)">' + g + '</g>' +
                 '<rect class="frame"/><rect class="handle"/>';
      }
      // outlines and paths come from the plugin: numbers and hex colors only
      box.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + vb.join(' ') +
        '" preserveAspectRatio="xMidYMid meet"><defs><clipPath id="svgm_face">' +
        '<path clip-rule="evenodd" d="' + face.outline + '"/></clipPath></defs>' +
        '<path class="face" fill-rule="evenodd" d="' + face.outline + '"/>' + design +
        '<path class="face-edge" d="' + face.outline + '"/></svg>';
      S.handleSize = Math.max(w, h) * 0.035;
    }
    positionDesign();
  }

  // where the design is on the face: its transform, its frame and handle
  function positionDesign() {
    var box = $('preview_place'), face = selectedFace(), a = S.analysis;
    var fit = face && placement(a, face, rotation());
    renderFramePos();
    if (!fit) return;
    var ox = S.frame.ox, oy = -S.frame.oy;          // this SVG has Y down
    var tf = 'translate(' + ox.toFixed(3) + ' ' + oy.toFixed(3) + ') rotate(' + (-rotation()) + ') scale(' +
             fit.k.toFixed(6) + ')';
    Array.prototype.forEach.call(box.querySelectorAll('.dz'), function (g) { g.setAttribute('transform', tf); });
    var frame = box.querySelector('.frame'), handle = box.querySelector('.handle'), hs = S.handleSize || 2;
    if (frame) {
      frame.setAttribute('x', (ox - fit.w / 2).toFixed(3)); frame.setAttribute('y', (oy - fit.h / 2).toFixed(3));
      frame.setAttribute('width', fit.w.toFixed(3)); frame.setAttribute('height', fit.h.toFixed(3));
    }
    if (handle) {
      handle.setAttribute('x', (ox + fit.w / 2 - hs / 2).toFixed(3));
      handle.setAttribute('y', (oy + fit.h / 2 - hs / 2).toFixed(3));
      handle.setAttribute('width', hs.toFixed(3)); handle.setAttribute('height', hs.toFixed(3));
    }
  }

  function renderFramePos() {
    var f = S.frame, centered = Math.abs(f.ox) < 0.05 && Math.abs(f.oy) < 0.05;
    $('frame_pos').textContent = centered ? t('frame.centered') : t('frame.pos', { x: fmt(f.ox), y: fmt(f.oy) });
    $('btn_center').disabled = centered;
  }

  function resetFrame() { S.frame.ox = 0; S.frame.oy = 0; }

  // drag the design to move it, its corner to resize it
  var drag = null;
  function svgPoint(svg, e) {
    var pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }
  function startDrag(e) {
    var face = selectedFace(), svg = $('preview_place').querySelector('svg');
    if (!face || !S.analysis || !svg || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var t0 = e.target, onHandle = t0.classList && t0.classList.contains('handle');
    if (!onHandle && !t0.closest('.dz') && !(t0.classList && t0.classList.contains('frame'))) return;
    var p = svgPoint(svg, e), fit = placement(S.analysis, face, rotation());
    drag = { svg: svg, handle: onHandle, x: p.x, y: p.y, ox: S.frame.ox, oy: S.frame.oy, fit: fit, moved: false };
    $('preview_place').setPointerCapture(e.pointerId);
  }
  function moveDrag(e) {
    if (!drag) return;
    var p = svgPoint(drag.svg, e), dx = p.x - drag.x, dy = p.y - drag.y;
    if (!drag.moved && Math.sqrt(dx * dx + dy * dy) < (S.handleSize || 2) / 4) return;
    drag.moved = true;
    if (drag.handle) {            // uniform scale about the center
      var cx = drag.ox, cy = -drag.oy, f = drag.fit;
      var s = Math.max((p.x - cx) / (f.w / 2), (p.y - cy) / (f.h / 2));
      var k = Math.max(1 / f.W, Math.min(f.kmax, f.k * s));
      $('apply_width_mm').value = (k * f.W).toFixed(1);
    } else {
      S.frame.ox = drag.ox + dx;
      S.frame.oy = drag.oy - dy;
    }
    positionDesign();
    renderAnalysisInfo();
  }
  function endDrag() {
    if (!drag) return;
    if (drag.moved) {
      S.dragEnd = Date.now();
      if (drag.handle) rememberSoon();
    }
    drag = null;
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

      // the swatch is a color picker: the part may print as another color
      var sw = el('label', 'c-sw' + (st.recolor ? ' changed' : ''));
      sw.style.background = st.recolor || c.color;
      sw.title = st.recolor ? t('col.recolored', { from: c.color, to: st.recolor }) : t('col.recolor');
      var pick = el('input'); pick.type = 'color'; pick.value = st.recolor || c.color;
      pick.setAttribute('aria-label', t('col.recolor'));
      pick.addEventListener('input', function () {      // live, while the picker is open
        sw.style.background = pick.value;
        st.recolor = sameColor(pick.value, c.color) ? null : pick.value.toLowerCase();
        applyRecolors();
      });
      pick.addEventListener('change', function () { recolor(c, pick.value); });
      sw.appendChild(pick);

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
        var opt = sel.options[sel.selectedIndex];
        sel.title = opt ? opt.textContent : '';     // the whole name, when the select cuts it
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
      if (st.recolor) {
        var back = el('button', 'tag reset', '↺'); back.type = 'button';
        back.title = t('col.reset_color', { color: c.color });
        back.setAttribute('aria-label', back.title);
        back.addEventListener('click', function () { recolor(c, null); });
        meta.insertBefore(back, meta.firstChild);
      }
      // the filament gets its own line, for its name; the details go below
      var line2 = el('div', 'c-line2');
      line2.appendChild(fil);

      row.appendChild(use); row.appendChild(sw); row.appendChild(name); row.appendChild(pct);
      row.appendChild(line2); row.appendChild(meta);
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
      var recolor = old ? old.recolor : null;
      var suggested = recolor ? old.suggested : c.filament;
      rows[c.color] = {
        name: old && (old.nameEdited || recolor) ? old.name : c.name,
        nameEdited: !!(old && old.nameEdited),
        filament: old && old.filEdited ? old.filament : suggested,
        filEdited: !!(old && old.filEdited),
        enabled: old ? old.enabled : true,
        suggested: suggested,
        recolor: recolor
      };
    });
    S.rows = rows;
  }

  /* ------------------------------------------------------------ recolor */
  function sameColor(a, b) { return String(a || '').toLowerCase() === String(b || '').toLowerCase(); }

  function colorIndex(color) {
    var list = S.analysis ? S.analysis.colors : [];
    for (var i = 0; i < list.length; i++) if (list[i].color === color) return i + 1;
    return 0;
  }

  function analysisColor(key) {
    var list = S.analysis ? S.analysis.colors : [];
    for (var i = 0; i < list.length; i++) if (list[i].color === key) return list[i];
    return null;
  }

  // a part printed as another color: name and filament follow the new color
  // unless the user chose them. Returns the color to describe, if any.
  function setRecolor(key, value) {
    var st = S.rows[key], c = analysisColor(key);
    if (!st || !c) return null;
    st.recolor = value && !sameColor(value, key) ? value.toLowerCase() : null;
    st.describing = !!st.recolor;
    if (!st.recolor) {
      if (!st.nameEdited) st.name = c.name;
      st.suggested = c.filament;
      if (!st.filEdited) st.filament = c.filament;
    }
    return st.recolor;
  }

  function describeColors(list) {
    var wanted = list.filter(function (c, i) { return c && list.indexOf(c) === i; });
    if (wanted.length) {
      send({ action: 'describe_colors', colors: wanted, filaments: S.filaments.length ? S.filaments : null });
    }
  }

  function recolor(c, value) {
    describeColors([setRecolor(c.color, value)]);
    renderColors();
    applyRecolors();
  }

  /* ------------------------------------------------------------ pick colors in the drawing */
  // a click on a color of the drawing opens its filaments; Ctrl (or Shift)
  // + click adds colors, and the choice goes to every selected one
  var picked = [];

  function markPicked() {
    ['preview_result', 'preview_place'].forEach(function (id) {
      var stage = $(id);
      stage.classList.toggle('picking', picked.length > 0);
      Array.prototype.forEach.call(stage.querySelectorAll('path[data-key]'), function (p) {
        p.classList.toggle('sel', picked.indexOf(p.getAttribute('data-key')) >= 0);
      });
    });
    each('.crow', function (r) { r.classList.toggle('sel', picked.indexOf(r.getAttribute('data-color')) >= 0); });
  }

  function openPicker(key, add, x, y) {
    if (!S.rows[key]) return;
    if (add) {
      var at = picked.indexOf(key);
      if (at >= 0) picked.splice(at, 1); else picked.push(key);
      if (!picked.length) { closePicker(); return; }
    } else {
      picked = [key];
    }
    markPicked();
    renderPicker();
    placePicker(x, y);
  }

  function renderPicker() {
    var rows = picked.map(function (k) { return S.rows[k]; });
    var shown = picked.map(function (k) { return S.rows[k].recolor || k; });
    var one = rows.length === 1;
    $('fp_sw').style.background = one ? shown[0] : 'linear-gradient(90deg, ' + shown.map(function (c, i) {
      return c + ' ' + (100 * i / shown.length) + '% ' + (100 * (i + 1) / shown.length) + '%';
    }).join(', ') + ')';
    $('fp_name').textContent = one ? rows[0].name : t('pop.many', { n: rows.length });
    var common = rows.every(function (r) { return r.filament === rows[0].filament; }) ? rows[0].filament : null;
    var list = $('fp_list');
    list.textContent = '';
    filamentList().forEach(function (f) {
      var b = el('button', 'fp-item' + (f.n === common ? ' on' : ''));
      b.type = 'button';
      b.setAttribute('role', 'listitem');
      var chip = el('i');
      if (f.color) chip.style.background = f.color; else chip.className = 'fsw none';
      b.appendChild(chip);
      b.appendChild(el('span', null, f.name ? f.n + ' · ' + f.name : String(f.n)));
      b.title = b.textContent;
      b.addEventListener('click', function () { applyFilament(f); });
      list.appendChild(b);
    });
    $('fp_color').value = shown[0];
    $('fp_off').textContent = t(rows.every(function (r) { return !r.enabled; }) ? 'pop.on' : 'pop.off');
    $('fil_pop').hidden = false;
  }

  function placePicker(x, y) {
    var pop = $('fil_pop'), box = $('preview').getBoundingClientRect();
    var left = Math.min(x - box.left + 12, box.width - pop.offsetWidth - 8);
    var top = Math.min(y - box.top + 12, box.height - pop.offsetHeight - 8);
    pop.style.left = Math.max(8, left) + 'px';
    pop.style.top = Math.max(8, top) + 'px';
  }

  function closePicker() {
    $('fil_pop').hidden = true;
    picked = [];
    markPicked();
  }

  function finishPick(toDescribe) {
    describeColors(toDescribe || []);
    closePicker();
    renderColors();
    applyRecolors();
  }

  // the chosen filament, and its color in the drawing, as it will print
  function applyFilament(f) {
    var names = picked.map(function (key) {
      var st = S.rows[key];
      st.enabled = true;
      var c = f.color ? setRecolor(key, f.color) : null;
      st.filament = f.n;
      st.filEdited = true;
      return c;
    });
    finishPick(names);
  }

  function onColorsInfo(m) {
    var items = m.items || {};
    Object.keys(S.rows).forEach(function (key) {
      var st = S.rows[key], info = st.recolor && items[st.recolor];
      if (!st.describing || !info) return;
      st.describing = false;
      if (!st.nameEdited && info.name) st.name = colorIndex(key) + '-' + info.name;
      if (info.filament) {
        st.suggested = info.filament;
        if (!st.filEdited) st.filament = info.filament;
      }
    });
    renderColors();
  }

  // the previews keep the SVG's colors in data-key; the fill shows the part's
  function applyRecolors() {
    ['preview_result', 'preview_place'].forEach(function (id) {
      Array.prototype.forEach.call($(id).querySelectorAll('path[data-key]'), function (p) {
        var st = S.rows[p.getAttribute('data-key')];
        if (st) p.setAttribute('fill', st.recolor || p.getAttribute('data-key'));
      });
    });
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
    send({ action: 'analyze', svg: S.svg, options: options(), levels: !!S.askColors,
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
      return { color: c.color, name: st.name, filament: st.filament, enabled: st.enabled,
               recolor: st.recolor || null };
    });
  }

  function jobMessage(action) {
    var opts = options();
    if (S.target === 'plate') { opts.offset_x_mm = S.frame.ox; opts.offset_y_mm = S.frame.oy; }
    return { action: action, svg: S.svg, options: opts, colors: colorsPayload(), reopen: true,
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
    resetFrame();
    S.askColors = S.settings.ask_colors !== false;   // a new drawing: how many colors?
    $('pick_fallback').hidden = true;
    renderSvgLine();
    analyze();
  }

  /* ------------------------------------------------------------ how many colors? */
  // levels.preview has one path per color; every count recolors that one
  // drawing through CSS variables (--k0, --k1 ...), drawn with <use>.
  function openWizard(levels) {
    var counts = Object.keys(levels.counts).map(Number).sort(function (a, b) { return a - b; });
    if (!counts.length) return;
    var src = new DOMParser().parseFromString(levels.preview, 'image/svg+xml').documentElement;
    var vb = src.getAttribute('viewBox') || '0 0 1 1';
    var NS = 'http://www.w3.org/2000/svg';
    // a plain group (not a <symbol>): the thumbnails share its coordinates
    var defs = $('wiz_defs'), box = document.createElementNS(NS, 'defs'), sym = document.createElementNS(NS, 'g');
    var keys = [], idx = {};
    defs.textContent = '';
    sym.setAttribute('id', 'svgm_levels');
    Array.prototype.forEach.call(src.querySelectorAll('path[data-key]'), function (p) {
      var key = p.getAttribute('data-key');
      if (!(key in idx)) { idx[key] = keys.length; keys.push(key); }
      var q = document.createElementNS(NS, 'path');
      q.setAttribute('d', p.getAttribute('d'));
      q.setAttribute('fill-rule', 'evenodd');
      q.setAttribute('style', 'fill:var(--k' + idx[key] + ')');
      sym.appendChild(q);
    });
    box.appendChild(sym);
    defs.appendChild(box);

    var grid = $('wiz_grid'), current = num($('max_colors').value, 0);
    var suggested = counts.indexOf(S.filaments.length) >= 0 ? S.filaments.length : null;
    grid.textContent = '';
    counts.forEach(function (k) {
      var lv = levels.counts[String(k)];
      var card = el('button', 'wiz-card' + (k === suggested ? ' suggested' : '') + (k === current ? ' current' : ''));
      card.type = 'button';
      card.setAttribute('role', 'listitem');
      var svg = document.createElementNS(NS, 'svg'), use = document.createElementNS(NS, 'use');
      svg.setAttribute('class', 'wiz-thumb');
      svg.setAttribute('viewBox', vb);
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      use.setAttribute('href', '#svgm_levels');
      use.setAttribute('style', keys.map(function (key, i) {
        return '--k' + i + ':' + (lv.map[key] || key);
      }).join(';'));
      svg.appendChild(use);
      card.appendChild(svg);
      var sw = el('div', 'wiz-sw');
      lv.colors.forEach(function (c) {
        var chip = el('i'); chip.style.background = c[0]; chip.title = c[0] + ' · ' + fmt(c[1]) + '%';
        sw.appendChild(chip);
      });
      card.appendChild(sw);
      card.appendChild(el('span', 'wiz-n', t('wiz.count', { n: k })));
      if (k === suggested) card.appendChild(el('span', 'wiz-badge', t('wiz.filaments')));
      card.addEventListener('click', function () { chooseColorCount(k); });
      grid.appendChild(card);
    });
    $('wizard').hidden = false;
    grid.scrollTop = 0;
    var first = grid.querySelector('.suggested') || grid.querySelector('.current') || grid.firstChild;
    if (first) first.focus({ preventScroll: true });
  }

  function closeWizard() {
    $('wizard').hidden = true;
    $('wiz_defs').textContent = '';
    $('wiz_grid').textContent = '';
  }

  function chooseColorCount(k) {
    closeWizard();
    $('max_colors').value = k;
    rememberSoon();
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
      case 'colors_info': onColorsInfo(m); break;
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
    S.presetLayers = m.layers || null;
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
    var ask = S.askColors && m.levels;
    S.askColors = false;
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
    if (ask) openWizard(m.levels);
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
    // read now and then: redraw only what changed (an open list must stay open)
    var sig = JSON.stringify([m.project, m.project_mtime, m.dirty, m.project_error,
      (m.objects || []).map(function (o) { return [o.name, o.size, o.object_id]; })]);
    var changed = sig !== S.plateSig;
    S.plateSig = sig;
    S.plate = m;
    if (changed || apply) { renderPlate(); renderFaces(); }
    var problem = apply ? plateProblem(m) : null;
    if (apply && !problem) {
      // the surface list must be the one of the file that will be changed
      if (facesFresh()) sendApply(); else requestFaces(true);
      return;
    }
    if (S.busy === 'plate') end();
    if (changed || apply) renderPreview();
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

    $('size_mode').addEventListener('change', updateSizeMode);
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
        updateLayers();
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
      resetFrame();
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
    $('btn_wizard').addEventListener('click', function (e) {
      e.preventDefault();                       // inside a <label>: do not focus the input
      if (!S.svg) { setStatus('error.no_svg', null, 'err'); return; }
      if (S.analysis && S.analysis.levels && S.analysis.svg_input === S.svg) openWizard(S.analysis.levels);
      else { S.askColors = true; analyze(); }
    });
    $('wiz_keep').addEventListener('click', closeWizard);

    // the design on the face: drag to move, its corner to resize
    $('preview_place').addEventListener('pointerdown', startDrag);
    $('preview_place').addEventListener('pointermove', moveDrag);
    $('preview_place').addEventListener('pointerup', endDrag);
    $('preview_place').addEventListener('pointercancel', endDrag);
    $('btn_center').addEventListener('click', function () {
      resetFrame(); positionDesign(); renderAnalysisInfo();
    });
    ['thickness_mode', 'thickness_layers', 'layer_height_mm', 'first_layer', 'base_thickness_mm'].forEach(function (id) {
      $(id).addEventListener('input', updateLayers);
      $(id).addEventListener('change', updateLayers);
    });

    // a color of the drawing: its filament (Ctrl/Shift + click: several)
    $('preview').addEventListener('click', function (e) {
      if (e.target.closest('#fil_pop') || e.target.closest('#wizard')) return;
      if (S.dragEnd && Date.now() - S.dragEnd < 300) return;      // the end of a drag, not a click
      var p = e.target.closest('path[data-key]');
      var key = p && p.getAttribute('data-key');
      if (!key || !S.rows[key]) { closePicker(); return; }
      openPicker(key, e.ctrlKey || e.metaKey || e.shiftKey, e.clientX, e.clientY);
    });
    document.addEventListener('mousedown', function (e) {
      if (!$('fil_pop').hidden && !e.target.closest('#preview')) closePicker();
    });
    $('fp_color').addEventListener('change', function () {
      var value = $('fp_color').value;
      finishPick(picked.map(function (key) { return setRecolor(key, value); }));
    });
    $('fp_off').addEventListener('click', function () {
      var on = picked.every(function (key) { return !S.rows[key].enabled; });
      picked.forEach(function (key) { S.rows[key].enabled = on; });
      finishPick([]);
    });
    $('btn_run').addEventListener('click', run);
    $('btn_open_folder').addEventListener('click', function (e) {
      e.preventDefault();
      if (S.lastDone) send({ action: 'open_path', path: S.lastDone.folder });
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !$('wizard').hidden) { e.preventDefault(); closeWizard(); return; }
      if (e.key === 'Escape' && !$('fil_pop').hidden) { e.preventDefault(); closePicker(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); run(); }
    });

    // coming back to this tab: the plate may have changed in the Prepare tab
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && S.target === 'plate' && !S.busy && Date.now() - S.plateReadAt > 2000) {
        readPlate(false);
      }
    });
    // nor changes to the plate in Prepare (a project opened, an object added)
    setInterval(function () {
      if (S.target !== 'plate' || S.busy || document.hidden || Date.now() - S.plateReadAt < 3000) return;
      S.plateReadAt = Date.now();
      send({ action: 'plate' });
    }, 3000);
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
