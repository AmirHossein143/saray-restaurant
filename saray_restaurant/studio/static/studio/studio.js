/* Saray Data Studio — vanilla JS, no dependencies. All data is inserted with textContent / DOM nodes (never innerHTML). */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';
  var API = location.pathname.replace(/\/?$/, '/') + 'api/';

  /* ---------------------------------------------------------------- helpers */
  function $(sel, root) { return (root || document).querySelector(sel); }

  function h(tag, props) {
    var el = document.createElement(tag);
    var kids = Array.prototype.slice.call(arguments, 2);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, v);
    });
    (function append(list) {
      list.forEach(function (kid) {
        if (Array.isArray(kid)) return append(kid);
        if (kid === null || kid === undefined || kid === false) return;
        el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
      });
    })(kids);
    return el;
  }

  function icon(name, cls) {
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'ico' + (cls ? ' ' + cls : ''));
    svg.setAttribute('aria-hidden', 'true');
    var use = document.createElementNS(NS, 'use');
    use.setAttribute('href', '#i-' + name);
    svg.append(use);
    return svg;
  }

  function csrf() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function api(path, opts) {
    opts = opts || {};
    var init = {
      method: opts.method || 'GET',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrf(), Accept: 'application/json' }
    };
    if (opts.json !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.json);
    }
    if (opts.form) init.body = opts.form;
    return fetch(API + path, init).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (body) {
        if (!res.ok) {
          var err = new Error((body && body.error) || res.statusText || 'Request failed');
          err.status = res.status;
          err.body = body || {};
          throw err;
        }
        return body;
      });
    });
  }

  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function debounce(fn, ms) {
    var t;
    return function () { var a = arguments; clearTimeout(t); t = setTimeout(function () { fn.apply(null, a); }, ms); };
  }
  function typing(el) {
    return el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
  }

  /* ------------------------------------------------------------------ state */
  var S = {
    tables: [], by: {}, cur: null, q: '', sort: '', page: 1, size: 25, filters: {},
    sel: new Set(), data: null, showFilters: false, hidden: [], req: 0, options: {}
  };
  var el = {
    app: $('#app'), nav: $('#tableNav'), view: $('#view'), crumbs: $('#crumbs'), tableFilter: $('#tableFilter'),
    drawer: $('#drawer'), drawerForm: $('#drawerForm'), drawerFoot: $('#drawerFoot'), drawerTitle: $('#drawerTitle'),
    drawerSub: $('#drawerSub'), confirm: $('#confirm'), toasts: $('#toasts'), scrim: $('#scrim')
  };

  /* ------------------------------------------------------------------ toast */
  function toast(message, type) {
    var node = h('div', { class: 'toast toast--' + (type || 'ok') }, icon(type === 'error' ? 'alert' : 'check'), h('span', { text: message }));
    el.toasts.append(node);
    setTimeout(function () { node.remove(); }, type === 'error' ? 7000 : 3200);
  }

  /* ---------------------------------------------------------------- confirm */
  function confirmDialog(o) {
    return new Promise(function (resolve) {
      $('#confirmTitle').textContent = o.title;
      $('#confirmIcon').style.display = o.icon === false ? 'none' : '';
      var body = $('#confirmBody');
      body.replaceChildren(o.body || '');
      var actions = $('#confirmActions');
      actions.replaceChildren();
      var done = false;
      function finish(value) { if (!done) { done = true; el.confirm.close(); resolve(value); } }
      actions.append(h('button', { class: 'btn', type: 'button', text: o.cancelText || 'Cancel', onclick: function () { finish(false); } }));
      if (o.confirmText) {
        var ok = h('button', { class: 'btn ' + (o.danger === false ? 'btn--primary' : 'btn--danger'), type: 'button', text: o.confirmText, onclick: function () { finish(true); } });
        actions.append(ok);
      }
      el.confirm.addEventListener('close', function once() { el.confirm.removeEventListener('close', once); finish(false); });
      el.confirm.showModal();
      var first = actions.lastChild;
      if (first) first.focus();
    });
  }

  /* --------------------------------------------------------------- sidebar */
  function renderNav() {
    var term = el.tableFilter.value.trim().toLowerCase();
    el.nav.replaceChildren();
    var lastGroup = null;
    S.tables.forEach(function (t) {
      var hay = (t.name + ' ' + t.table + ' ' + t.verbose).toLowerCase();
      if (term && hay.indexOf(term) === -1) return;
      if (t.group !== lastGroup) {
        lastGroup = t.group;
        el.nav.append(h('div', { class: 'side-group', text: t.group }));
      }
      el.nav.append(h('button', {
        class: 'side-link', type: 'button', 'aria-current': S.cur && S.cur.key === t.key ? 'page' : null,
        title: t.verbose, onclick: function () { go(t.key); closeNav(); }
      },
        icon(t.readonly ? 'lock' : 'table'),
        h('span', { class: 'side-link__name', text: t.name }),
        h('span', { class: 'side-link__count', text: fmt(t.count) })));
    });
    if (!el.nav.childNodes.length) el.nav.append(h('div', { class: 'side-group', text: 'No matching tables' }));
  }
  function openNav() { el.app.classList.add('nav-open'); el.scrim.hidden = false; }
  function closeNav() { el.app.classList.remove('nav-open'); el.scrim.hidden = true; }

  function refreshCounts() {
    return api('tables/').then(function (res) {
      res.tables.forEach(function (t) { S.by[t.key] = t; });
      S.tables = res.tables;
      if (S.cur) S.cur = S.by[S.cur.key];
      renderNav();
    });
  }

  /* ----------------------------------------------------------------- router */
  function go(key) { location.hash = key ? '#' + encodeURIComponent(key) : '#'; }
  function route() {
    var key = decodeURIComponent(location.hash.slice(1));
    if (key && S.by[key]) openTable(key); else showOverview();
  }

  function setCrumbs(parts) {
    el.crumbs.replaceChildren();
    parts.forEach(function (p, i) {
      if (i) el.crumbs.append(h('span', { class: 'sep', text: '/' }));
      el.crumbs.append(h('span', { class: p.dim ? 'dim' : '', text: p.text }));
    });
  }

  /* --------------------------------------------------------------- overview */
  function showOverview() {
    S.cur = null;
    renderNav();
    setCrumbs([{ text: 'Overview' }]);
    document.title = 'Saray Data Studio';
    var total = S.tables.reduce(function (n, t) { return n + t.count; }, 0);
    var view = h('div', {},
      h('div', { class: 'page-head' }, h('div', { class: 'page-head__grow' },
        h('h1', { text: 'Database overview' }),
        h('p', { text: S.tables.length + ' tables · ' + fmt(total) + ' rows. Pick a table to browse, search, edit, add or delete rows.' }))));
    var group = null, grid = null;
    S.tables.forEach(function (t) {
      if (t.group !== group) {
        group = t.group;
        view.append(h('div', { class: 'group-title', text: group }));
        grid = h('div', { class: 'cards' });
        view.append(grid);
      }
      grid.append(h('button', { class: 'card', type: 'button', onclick: function () { go(t.key); } },
        h('div', { class: 'card__top' }, icon(t.readonly ? 'lock' : 'table'), h('span', { class: 'mono', text: t.fields.length + ' columns' })),
        h('div', { class: 'card__name', text: t.name }),
        h('div', { class: 'card__count', text: fmt(t.count) }),
        h('div', { class: 'card__meta', text: t.table + (t.readonly ? ' · read-only' : '') })));
    });
    el.view.replaceChildren(view);
  }

  /* ------------------------------------------------------------ table view */
  function hiddenKey(t) { return 'studio-cols:' + t.key; }
  function loadHidden(t) {
    try { return JSON.parse(localStorage.getItem(hiddenKey(t)) || '[]'); } catch (e) { return []; }
  }
  function saveHidden(t) {
    try { localStorage.setItem(hiddenKey(t), JSON.stringify(S.hidden)); } catch (e) { /* private mode */ }
  }
  function visibleFields(t) { return t.fields.filter(function (f) { return S.hidden.indexOf(f.name) === -1; }); }
  function filterableFields(t) {
    return t.fields.filter(function (f) { return ['bool', 'choice', 'fk', 'image', 'file'].indexOf(f.kind) !== -1; });
  }
  function activeFilterCount() {
    return Object.keys(S.filters).filter(function (k) { return S.filters[k] !== ''; }).length;
  }

  var shell = {};

  function openTable(key) {
    var t = S.by[key];
    S.cur = t;
    S.q = ''; S.sort = ''; S.page = 1; S.filters = {}; S.sel = new Set(); S.data = null; S.showFilters = false;
    S.hidden = loadHidden(t);
    renderNav();
    setCrumbs([{ text: t.group, dim: true }, { text: t.name }]);
    document.title = t.name + ' · Saray Data Studio';
    buildShell(t);
    loadRows();
  }

  function buildShell(t) {
    var search = h('input', { class: 'input', type: 'search', placeholder: 'Search ' + t.name + '…', 'aria-label': 'Search rows', autocomplete: 'off' });
    search.addEventListener('input', debounce(function () { S.q = search.value; S.page = 1; loadRows(); }, 250));
    var addBtn = t.can_add
      ? h('button', { class: 'btn btn--primary', type: 'button', onclick: function () { openDrawer('create'); } }, icon('plus'), 'Add row')
      : null;
    var colBtn = h('button', { class: 'btn', type: 'button', 'aria-haspopup': 'true', onclick: function (e) { e.stopPropagation(); toggleColumns(colBtn); } }, icon('columns'), 'Columns');
    var filterBadge = h('span', { class: 'badge', hidden: true });
    var filterBtn = filterableFields(t).length
      ? h('button', { class: 'btn', type: 'button', onclick: function () { S.showFilters = !S.showFilters; renderFilters(); } }, icon('filter'), 'Filters', filterBadge)
      : null;

    shell = {
      search: search, filterBadge: filterBadge,
      filters: h('div', {}), body: h('div', {}),
      title: h('h1', { text: t.name }),
      sub: h('p', {})
    };
    var head = h('div', { class: 'page-head' },
      h('div', { class: 'page-head__grow' }, shell.title, shell.sub),
      addBtn);
    var toolbar = h('div', { class: 'toolbar' },
      h('div', { class: 'search' }, icon('search'), search),
      filterBtn, colBtn,
      h('span', { class: 'toolbar__spacer' }),
      h('button', { class: 'btn', type: 'button', onclick: function () { loadRows(); } }, icon('refresh'), 'Refresh'),
      h('button', { class: 'btn', type: 'button', onclick: exportCsv }, icon('download'), 'Export CSV'));
    var notice = t.readonly ? h('div', { class: 'notice' }, icon('lock'), h('span', { text: 'Read-only table. ' + (t.note || '') })) : null;
    el.view.replaceChildren(h('div', {}, head, notice, toolbar, shell.filters, shell.body));
    updateSub();
    renderFilters();
  }

  function updateSub() {
    var t = S.cur;
    var total = S.data ? S.data.total : t.count;
    shell.sub.textContent = t.table + ' · ' + fmt(total) + (total === 1 ? ' row' : ' rows') + (t.verbose ? ' · ' + t.verbose : '');
  }

  function queryParams(withPaging) {
    var p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.sort) p.set('sort', S.sort);
    Object.keys(S.filters).forEach(function (k) { if (S.filters[k] !== '') p.set('f_' + k, S.filters[k]); });
    if (withPaging) { p.set('page', S.page); p.set('page_size', S.size); }
    return p;
  }

  function loadRows() {
    var t = S.cur;
    if (!t) return;
    var token = ++S.req;
    if (!S.data) renderSkeleton();
    return api(t.key + '/rows/?' + queryParams(true)).then(function (res) {
      if (token !== S.req) return;
      if (res.page < S.page) S.page = res.page;
      S.data = res;
      var present = new Set(res.rows.map(function (r) { return r.pk; }));
      S.sel.forEach(function (pk) { if (!present.has(pk)) S.sel.delete(pk); });
      updateSub();
      renderBody();
    }).catch(function (err) {
      if (token !== S.req) return;
      shell.body.replaceChildren(h('div', { class: 'notice notice--danger' }, icon('alert'), h('span', { text: err.message }),
        h('button', { class: 'btn btn--sm', type: 'button', onclick: loadRows, text: 'Retry' })));
    });
  }

  function renderSkeleton() {
    var rows = [];
    for (var i = 0; i < 8; i++) rows.push(h('tr', {}, h('td', {}, h('div', { class: 'skel', style: 'width:' + (40 + (i * 37) % 50) + '%' }))));
    shell.body.replaceChildren(h('div', { class: 'table-wrap' }, h('table', { class: 'grid' }, h('tbody', {}, rows))));
  }

  /* ---- filters ---- */
  function renderFilters() {
    var t = S.cur;
    var n = activeFilterCount();
    shell.filterBadge.hidden = n === 0;
    shell.filterBadge.textContent = n;
    shell.filters.replaceChildren();
    if (!S.showFilters) return;
    var box = h('div', { class: 'filters' });
    filterableFields(t).forEach(function (f) {
      var sel = h('select', { class: 'select', 'aria-label': 'Filter by ' + f.name });
      sel.append(h('option', { value: '', text: 'Any' }));
      function fill(items) {
        items.forEach(function (o) { sel.append(h('option', { value: o[0], text: o[1] })); });
        sel.value = S.filters[f.name] || '';
      }
      if (f.kind === 'bool') fill([['1', 'Yes'], ['0', 'No']]);
      else if (f.kind === 'choice') fill(f.choices);
      else if (f.kind === 'image' || f.kind === 'file') fill([['yes', 'Has file'], ['no', 'No file']]);
      else getOptions(f.related).then(function (opts) { fill(opts.map(function (o) { return [String(o.id), o.label]; })); });
      sel.addEventListener('change', function () { S.filters[f.name] = sel.value; S.page = 1; renderFilters(); loadRows(); });
      box.append(h('label', {}, h('span', { text: f.name }), sel));
    });
    if (n) box.append(h('button', { class: 'btn btn--sm', type: 'button', style: 'align-self:end', text: 'Clear filters', onclick: function () { S.filters = {}; S.page = 1; renderFilters(); loadRows(); } }));
    shell.filters.append(box);
  }

  function getOptions(key) {
    if (!S.options[key]) {
      S.options[key] = api(key + '/options/').then(function (r) { return r.options; }).catch(function (e) { delete S.options[key]; throw e; });
    }
    return S.options[key];
  }

  /* ---- columns popover ---- */
  var openPopover = null;
  function closePopover() { if (openPopover) { openPopover.remove(); openPopover = null; } }
  function toggleColumns(btn) {
    if (openPopover) return closePopover();
    var t = S.cur;
    var pop = h('div', { class: 'popover', role: 'dialog', 'aria-label': 'Choose columns', onclick: function (e) { e.stopPropagation(); } }, h('h3', { text: 'Visible columns' }));
    t.fields.forEach(function (f) {
      var cb = h('input', { type: 'checkbox' });
      cb.checked = S.hidden.indexOf(f.name) === -1;
      cb.addEventListener('change', function () {
        S.hidden = cb.checked ? S.hidden.filter(function (n) { return n !== f.name; }) : S.hidden.concat(f.name);
        saveHidden(t);
        renderBody();
      });
      pop.append(h('label', {}, cb, h('span', { class: 'mono', text: f.name })));
    });
    pop.append(h('button', { class: 'btn btn--sm', type: 'button', style: 'margin-top:8px', text: 'Show all', onclick: function () { S.hidden = []; saveHidden(t); closePopover(); renderBody(); } }));
    btn.parentNode.style.position = 'relative';
    pop.style.top = (btn.offsetTop + btn.offsetHeight + 6) + 'px';
    pop.style.left = btn.offsetLeft + 'px';
    btn.parentNode.append(pop);
    openPopover = pop;
  }
  document.addEventListener('click', closePopover);

  /* ---- table body ---- */
  function renderBody() {
    var t = S.cur, d = S.data;
    closePopover();
    if (!d) return;
    var parts = [];
    if (S.sel.size) {
      parts.push(h('div', { class: 'selbar' },
        h('strong', { text: fmt(S.sel.size) + ' selected' }),
        t.can_delete ? h('button', { class: 'btn btn--danger btn--sm', type: 'button', onclick: function () { deleteRows(Array.from(S.sel)); } }, icon('trash', 'ico--sm'), 'Delete selected') : null,
        h('button', { class: 'btn btn--sm', type: 'button', text: 'Clear', onclick: function () { S.sel.clear(); renderBody(); } })));
    }
    if (!d.rows.length) {
      var filtering = S.q || activeFilterCount();
      parts.push(h('div', { class: 'table-wrap' }, h('div', { class: 'empty' }, icon('table'),
        h('h3', { text: filtering ? 'No rows match' : 'This table is empty' }),
        h('p', { text: filtering ? 'Try a different search or clear the filters.' : 'There is nothing here yet.' }),
        filtering
          ? h('button', { class: 'btn', type: 'button', text: 'Clear search & filters', onclick: function () { S.q = ''; shell.search.value = ''; S.filters = {}; S.page = 1; renderFilters(); loadRows(); } })
          : (t.can_add ? h('button', { class: 'btn btn--primary', type: 'button', onclick: function () { openDrawer('create'); } }, icon('plus'), 'Add the first row') : null))));
    } else {
      parts.push(buildTable(t, d));
      parts.push(buildPager(d));
    }
    shell.body.replaceChildren.apply(shell.body, parts);
  }

  function buildTable(t, d) {
    var fields = visibleFields(t);
    var allChecked = d.rows.length && d.rows.every(function (r) { return S.sel.has(r.pk); });
    var master = h('input', { type: 'checkbox', 'aria-label': 'Select all rows on this page' });
    master.checked = !!allChecked;
    master.addEventListener('change', function () {
      d.rows.forEach(function (r) { if (master.checked) S.sel.add(r.pk); else S.sel.delete(r.pk); });
      renderBody();
    });
    var headRow = h('tr', {}, t.can_delete ? h('th', { class: 'col-check' }, master) : null);
    fields.forEach(function (f) {
      var dir = S.sort === f.name ? 'asc' : S.sort === '-' + f.name ? 'desc' : null;
      headRow.append(h('th', { 'aria-sort': dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none' },
        h('button', {
          class: 'th-btn', type: 'button', 'data-dir': dir, title: f.verbose || f.name,
          onclick: function () { S.sort = S.sort === f.name ? '-' + f.name : S.sort === '-' + f.name ? '' : f.name; S.page = 1; loadRows(); }
        }, f.name, icon(dir === 'asc' ? 'up' : dir === 'desc' ? 'down' : 'sort'))));
    });
    headRow.append(h('th', { class: 'col-actions' }));
    var tbody = h('tbody', {});
    d.rows.forEach(function (row) { tbody.append(buildRow(t, fields, row)); });
    return h('div', { class: 'table-wrap' }, h('table', { class: 'grid' }, h('thead', {}, headRow), tbody));
  }

  function buildRow(t, fields, row) {
    var tr = h('tr', { class: S.sel.has(row.pk) ? 'is-selected' : '' });
    if (t.can_delete) {
      var cb = h('input', { type: 'checkbox', 'aria-label': 'Select row ' + row.pk });
      cb.checked = S.sel.has(row.pk);
      cb.addEventListener('change', function () {
        if (cb.checked) S.sel.add(row.pk); else S.sel.delete(row.pk);
        renderBody();
      });
      tr.append(h('td', { class: 'col-check' }, cb));
    }
    fields.forEach(function (f) {
      var td = h('td', {});
      fillCell(td, t, f, row);
      tr.append(td);
    });
    tr.append(h('td', { class: 'col-actions' },
      h('button', { class: 'icon-btn', type: 'button', title: t.readonly ? 'View' : 'Edit', 'aria-label': (t.readonly ? 'View row ' : 'Edit row ') + row.pk, onclick: function () { openDrawer(t.readonly ? 'view' : 'edit', row.pk); } }, icon(t.readonly ? 'search' : 'edit')),
      t.can_delete ? h('button', { class: 'icon-btn icon-btn--danger', type: 'button', title: 'Delete', 'aria-label': 'Delete row ' + row.pk, onclick: function () { deleteRows([row.pk]); } }, icon('trash')) : null));
    return tr;
  }

  function nullCell() { return h('span', { class: 'cell cell--null', text: 'NULL' }); }

  function fillCell(td, t, f, row) {
    var v = row.v[f.name];
    var editable = !t.readonly && f.editable && f.kind !== 'image' && f.kind !== 'file';
    var node;
    if (f.pk) {
      node = h('span', { class: 'cell cell--pk', text: String(v) });
    } else if (f.kind === 'bool') {
      node = h('button', { class: 'switch', type: 'button', role: 'switch', 'aria-checked': v ? 'true' : 'false', 'aria-label': f.name, disabled: t.readonly || !f.editable });
      node.addEventListener('click', function () { patchCell(t, f, row, !v, td); });
    } else if (v === null || v === undefined) {
      node = nullCell();
    } else if (f.kind === 'fk') {
      node = h('span', { class: 'chip', dir: 'auto', title: '#' + v.id, text: v.label });
    } else if (f.kind === 'choice') {
      node = h('span', { class: 'chip chip--choice', title: v.value, text: v.label });
    } else if (f.kind === 'image') {
      node = h('a', { href: v, target: '_blank', rel: 'noopener', title: v }, h('img', { class: 'thumb', src: v, loading: 'lazy', alt: '' }));
    } else if (f.kind === 'file') {
      node = h('a', { href: v, target: '_blank', rel: 'noopener', class: 'cell mono', text: v });
    } else if (f.kind === 'number' || f.kind === 'decimal') {
      node = h('span', { class: 'cell cell--num', text: String(v) });
    } else if (f.kind === 'date' || f.kind === 'datetime' || f.kind === 'time') {
      node = h('span', { class: 'cell cell--num', text: String(v).replace('T', ' ') });
    } else if (v === '') {
      node = h('span', { class: 'cell cell--null', text: '(empty)' });
    } else {
      node = h('span', { class: 'cell', dir: 'auto', title: v, text: v });
    }
    td.replaceChildren(node);
    if (editable && f.kind !== 'bool') {
      node.classList.add('is-editable');
      node.title = 'Double-click to edit';
      node.addEventListener('dblclick', function () { startEdit(td, t, f, row); });
    }
  }

  /* ---- inline editing ---- */
  function inputType(kind) {
    return { number: 'number', decimal: 'number', date: 'date', time: 'time', datetime: 'datetime-local', email: 'email', url: 'url' }[kind] || 'text';
  }

  function startEdit(td, t, f, row) {
    api(t.key + '/rows/' + row.pk + '/').then(function (detail) {
      var current = detail.form[f.name];
      return buildEditor(f, current).then(function (input) { return { input: input, current: current }; });
    }).then(function (ctx) {
      var input = ctx.input, finished = false;
      function cancel() { if (finished) return; finished = true; fillCell(td, t, f, row); }
      function commit() {
        if (finished) return;
        var value = input.value;
        if (String(ctx.current === null ? '' : ctx.current) === value) return cancel();
        finished = true;
        patchCell(t, f, row, value === '' && f.null ? null : value, td, function () { finished = false; td.replaceChildren(input); input.classList.add('is-invalid'); input.focus(); });
      }
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && f.kind !== 'textarea') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') { e.stopPropagation(); cancel(); }
      });
      input.addEventListener('blur', function () { setTimeout(commit, 80); });
      if (input.tagName === 'SELECT') input.addEventListener('change', commit);
      td.replaceChildren(input);
      input.focus();
      if (input.select && input.tagName === 'INPUT') input.select();
    }).catch(function (err) { toast(err.message, 'error'); });
  }

  function buildEditor(f, current) {
    if (f.kind === 'choice') {
      var sel = h('select', { class: 'cell-input' }, f.required ? null : h('option', { value: '', text: '—' }),
        f.choices.map(function (c) { return h('option', { value: c[0], text: c[1] }); }));
      sel.value = current === null ? '' : String(current);
      return Promise.resolve(sel);
    }
    if (f.kind === 'fk') {
      return getOptions(f.related).then(function (opts) {
        var s = h('select', { class: 'cell-input' }, f.required ? null : h('option', { value: '', text: '—' }),
          opts.map(function (o) { return h('option', { value: String(o.id), text: o.label }); }));
        s.value = current === null ? '' : String(current);
        return s;
      });
    }
    var input = h('input', { class: 'cell-input', type: inputType(f.kind), dir: 'auto', step: f.kind === 'decimal' ? 'any' : null });
    input.value = current === null ? '' : String(current);
    return Promise.resolve(input);
  }

  function patchCell(t, f, row, value, td, onInvalid) {
    return api(t.key + '/rows/' + row.pk + '/', { method: 'PATCH', json: { field: f.name, value: value } }).then(function (res) {
      row.v = res.row.v; row.label = res.row.label;
      fillCell(td, t, f, row);
      toast('Saved ' + f.name);
    }).catch(function (err) {
      var msg = err.body && err.body.fields && err.body.fields[f.name] ? err.body.fields[f.name][0] : err.message;
      toast(msg, 'error');
      if (onInvalid) onInvalid(); else fillCell(td, t, f, row);
    });
  }

  /* ---- pager ---- */
  function buildPager(d) {
    var pages = h('div', { class: 'pages' });
    var from = Math.max(1, d.page - 2), to = Math.min(d.pages, d.page + 2);
    function pageBtn(n, label, disabled, current) {
      return h('button', { class: 'page-btn', type: 'button', disabled: disabled, 'aria-current': current ? 'page' : null, 'aria-label': 'Page ' + n, text: label || String(n), onclick: function () { S.page = n; loadRows(); } });
    }
    pages.append(pageBtn(1, '«', d.page === 1));
    pages.append(pageBtn(Math.max(1, d.page - 1), '‹', d.page === 1));
    for (var n = from; n <= to; n++) pages.append(pageBtn(n, null, false, n === d.page));
    pages.append(pageBtn(Math.min(d.pages, d.page + 1), '›', d.page === d.pages));
    pages.append(pageBtn(d.pages, '»', d.page === d.pages));
    var size = h('select', { class: 'select', style: 'width:auto', 'aria-label': 'Rows per page' }, [10, 25, 50, 100, 250].map(function (n) { return h('option', { value: n, text: n + ' / page' }); }));
    size.value = String(S.size);
    size.addEventListener('change', function () { S.size = Number(size.value); S.page = 1; loadRows(); });
    return h('div', { class: 'pager' },
      h('span', { text: 'Showing ' + fmt(d.start) + '–' + fmt(d.end) + ' of ' + fmt(d.total) }),
      h('span', { class: 'pager__grow' }), size, pages);
  }

  function exportCsv() {
    location.href = API + S.cur.key + '/export.csv?' + queryParams(false);
  }

  /* ----------------------------------------------------------------- delete */
  function deleteRows(ids) {
    var t = S.cur;
    var preview = ids.length === 1
      ? api(t.key + '/rows/' + ids[0] + '/delete-preview/')
      : api(t.key + '/bulk-delete/', { method: 'POST', json: { ids: ids, preview: true } });
    preview.then(function (p) {
      if (p.blocked) {
        return confirmDialog({ title: 'Cannot delete', body: h('p', { text: p.blocked }), cancelText: 'Close' });
      }
      var body = h('div', {});
      if (ids.length === 1 && p.label) body.append(h('p', {}, 'You are about to delete ', h('span', { class: 'lbl', text: p.label }), ' (#' + ids[0] + ') from ', h('strong', { text: t.name }), '.'));
      else body.append(h('p', {}, 'You are about to delete ', h('strong', { text: fmt(ids.length) + ' rows' }), ' from ', h('strong', { text: t.name }), '.'));
      var related = p.summary && p.summary.related || [];
      if (related.length) {
        body.append(h('p', {}, 'This also permanently deletes:'));
        body.append(h('ul', {}, related.map(function (r) { return h('li', {}, h('strong', { text: fmt(r.count) }), ' ', r.table); })));
      }
      body.append(h('p', {}, 'This cannot be undone.'));
      return confirmDialog({ title: ids.length === 1 ? 'Delete this row?' : 'Delete ' + fmt(ids.length) + ' rows?', body: body, confirmText: 'Delete' }).then(function (ok) {
        if (!ok) return;
        var call = ids.length === 1
          ? api(t.key + '/rows/' + ids[0] + '/', { method: 'DELETE' })
          : api(t.key + '/bulk-delete/', { method: 'POST', json: { ids: ids } });
        return call.then(function (r) {
          toast('Deleted ' + fmt(r.deleted) + (r.deleted === 1 ? ' row' : ' rows'));
          ids.forEach(function (id) { S.sel.delete(id); });
          return Promise.all([loadRows(), refreshCounts()]);
        });
      });
    }).catch(function (err) { toast(err.message, 'error'); });
  }

  /* ----------------------------------------------------------------- drawer */
  var D = null;
  var lastFocus = null;

  function drawerVisible() { return !el.drawer.hidden; }

  function openDrawer(mode, pk) {
    var t = S.cur;
    lastFocus = document.activeElement;
    D = { mode: mode, pk: pk, dirty: false, busy: false };
    el.drawerTitle.textContent = mode === 'create' ? 'New ' + t.name : (mode === 'view' ? 'View ' : 'Edit ') + t.name + ' #' + pk;
    el.drawerSub.textContent = t.table;
    el.drawerForm.replaceChildren(h('div', { class: 'skel', style: 'height:40px' }), h('div', { class: 'skel', style: 'height:40px' }), h('div', { class: 'skel', style: 'height:40px' }));
    el.drawerFoot.replaceChildren();
    el.drawer.hidden = false;
    el.drawer.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';

    if (mode === 'view') {
      var row = S.data.rows.filter(function (r) { return r.pk === pk; })[0];
      var dl = h('dl', { class: 'kv' });
      t.fields.forEach(function (f) {
        var v = row.v[f.name];
        var text = v === null || v === undefined ? 'NULL' : (typeof v === 'object' ? v.label : String(v));
        dl.append(h('dt', { text: f.name }), h('dd', { text: text }));
      });
      el.drawerForm.replaceChildren(dl);
      el.drawerFoot.replaceChildren(h('span', { class: 'grow' }), h('button', { class: 'btn', type: 'button', text: 'Close', onclick: function () { closeDrawer(true); } }));
      return;
    }

    var fetchDetail = mode === 'edit' ? api(t.key + '/rows/' + pk + '/') : Promise.resolve(null);
    var needOptions = t.form_fields.map(function (n) { return fieldInfo(t, n); }).filter(function (f) { return f.kind === 'fk'; });
    Promise.all([fetchDetail].concat(needOptions.map(function (f) { return getOptions(f.related); }))).then(function (res) {
      if (!D) return;
      buildForm(t, res[0]);
    }).catch(function (err) {
      el.drawerForm.replaceChildren(h('div', { class: 'banner', text: err.message }));
    });
  }

  function fieldInfo(t, name) { return t.fields.filter(function (f) { return f.name === name; })[0]; }

  function buildForm(t, detail) {
    var form = el.drawerForm;
    form.replaceChildren(h('div', { class: 'banner', id: 'formBanner', hidden: true }));
    t.form_fields.forEach(function (name) {
      var f = fieldInfo(t, name);
      var value = detail ? detail.form[name] : (f.default !== undefined ? f.default : null);
      form.append(buildField(f, value, !!detail));
    });
    var foot = el.drawerFoot;
    foot.replaceChildren();
    if (D.mode === 'edit' && t.can_delete) {
      foot.append(h('button', { class: 'btn btn--ghost', type: 'button', style: 'color:var(--danger)', onclick: function () { var pk = D.pk; closeDrawer(true); deleteRows([pk]); } }, icon('trash', 'ico--sm'), 'Delete'));
    }
    foot.append(h('span', { class: 'grow' }));
    foot.append(h('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: function () { closeDrawer(false); } }));
    if (D.mode === 'create' && !t.singleton) {
      foot.append(h('button', { class: 'btn', type: 'button', id: 'saveAnother', text: 'Save & add another', onclick: function () { submitForm(true); } }));
    }
    foot.append(h('button', { class: 'btn btn--primary', type: 'button', id: 'saveBtn', onclick: function () { submitForm(false); } }, icon('check', 'ico--sm'), D.mode === 'create' ? 'Create' : 'Save changes'));
    var first = form.querySelector('input:not([type=hidden]):not([type=checkbox]), select, textarea');
    if (first) first.focus();
  }

  function buildField(f, value, editing) {
    var id = 'f_' + f.name;
    var control;
    var labelText = h('span', {}, f.name, f.required ? h('span', { class: 'req', 'aria-hidden': 'true', text: ' *' }) : null);
    var verbose = f.verbose && f.verbose !== f.name ? h('span', { class: 'verbose', text: f.verbose }) : null;

    if (f.kind === 'bool') {
      control = h('input', { type: 'checkbox', id: id, name: f.name, style: 'width:20px;height:20px;accent-color:var(--accent)' });
      control.checked = !!value;
      return h('div', { class: 'field field--inline', 'data-field': f.name },
        h('label', { class: 'field__label', for: id }, labelText, verbose), control, errorSlot(f));
    }
    if (f.kind === 'image' || f.kind === 'file') {
      var preview = f.kind === 'image' && value ? h('img', { src: value, alt: '' }) : null;
      var input = h('input', { type: 'file', id: id, name: f.name, accept: f.kind === 'image' ? 'image/*' : null });
      var clear = null;
      var meta = h('div', { class: 'filepick__meta' }, input);
      if (value && !f.required) {
        clear = h('input', { type: 'checkbox', name: f.name + '-clear', id: id + '-clear' });
        meta.append(h('label', { style: 'display:flex;gap:6px;align-items:center;font-size:13px' }, clear, 'Remove current file'));
      }
      if (value) meta.prepend(h('a', { href: value, target: '_blank', rel: 'noopener', class: 'mono', text: value }));
      input.addEventListener('change', function () {
        if (input.files[0] && f.kind === 'image') {
          var url = URL.createObjectURL(input.files[0]);
          var img = $('img', box) || h('img', { alt: '' });
          img.src = url;
          if (!img.parentNode) box.prepend(img);
        }
      });
      var box = h('div', { class: 'filepick' }, preview, meta);
      return h('div', { class: 'field', 'data-field': f.name }, h('label', { class: 'field__label', for: id }, labelText, verbose), box, helpLine(f), errorSlot(f));
    }
    if (f.kind === 'choice') {
      control = h('select', { class: 'select', id: id, name: f.name }, f.required ? null : h('option', { value: '', text: '—' }),
        f.choices.map(function (c) { return h('option', { value: c[0], text: c[1] }); }));
      control.value = value === null ? '' : String(value);
    } else if (f.kind === 'fk') {
      control = h('select', { class: 'select', id: id, name: f.name }, f.required ? h('option', { value: '', text: 'Select…' }) : h('option', { value: '', text: '—' }));
      S.options[f.related].then(function (opts) {
        opts.forEach(function (o) { control.append(h('option', { value: String(o.id), text: o.label })); });
        control.value = value === null ? '' : String(value);
      });
    } else if (f.kind === 'textarea' || f.kind === 'json') {
      control = h('textarea', { class: 'textarea', id: id, name: f.name, dir: 'auto', rows: f.kind === 'json' ? 8 : 4, maxlength: f.max_length });
      control.value = value === null ? '' : String(value);
    } else {
      control = h('input', {
        class: 'input', id: id, name: f.name, type: inputType(f.kind), dir: 'auto', maxlength: f.max_length,
        step: f.kind === 'decimal' ? 'any' : null, min: f.min, max: f.max, autocomplete: 'off', spellcheck: 'false'
      });
      control.value = value === null ? '' : String(value);
    }
    return h('div', { class: 'field', 'data-field': f.name },
      h('label', { class: 'field__label', for: id }, labelText, verbose), control, helpLine(f), errorSlot(f));
  }

  function helpLine(f) { return f.help ? h('div', { class: 'field__help', text: f.help }) : null; }
  function errorSlot(f) { return h('div', { class: 'field__error', 'data-error-for': f.name, hidden: true }); }

  function showErrors(fields, message) {
    var banner = $('#formBanner');
    var firstBad = null;
    Object.keys(fields || {}).forEach(function (name) {
      var slot = el.drawerForm.querySelector('[data-error-for="' + name + '"]');
      if (!slot) { message = (message ? message + ' ' : '') + name + ': ' + fields[name][0]; return; }
      slot.hidden = false;
      slot.replaceChildren(icon('alert', 'ico--sm'), h('span', { text: fields[name].join(' ') }));
      var input = el.drawerForm.querySelector('[name="' + name + '"]');
      if (input) { input.classList.add('is-invalid'); firstBad = firstBad || input; }
    });
    if (message) { banner.hidden = false; banner.textContent = message; }
    if (firstBad) firstBad.focus();
  }

  function clearErrors() {
    $('#formBanner').hidden = true;
    el.drawerForm.querySelectorAll('[data-error-for]').forEach(function (n) { n.hidden = true; n.replaceChildren(); });
    el.drawerForm.querySelectorAll('.is-invalid').forEach(function (n) { n.classList.remove('is-invalid'); });
  }

  function submitForm(addAnother) {
    if (!D || D.busy) return;
    var t = S.cur;
    clearErrors();
    D.busy = true;
    var buttons = el.drawerFoot.querySelectorAll('button');
    buttons.forEach(function (b) { b.disabled = true; });
    var url = D.mode === 'create' ? t.key + '/rows/' : t.key + '/rows/' + D.pk + '/';
    api(url, { method: 'POST', form: new FormData(el.drawerForm) }).then(function () {
      toast(D.mode === 'create' ? 'Row created' : 'Changes saved');
      var again = addAnother && D.mode === 'create';
      D.dirty = false;
      D.busy = false;
      var reload = Promise.all([loadRows(), refreshCounts()]);
      if (again) { openDrawer('create'); } else { closeDrawer(true); }
      return reload;
    }).catch(function (err) {
      D.busy = false;
      buttons.forEach(function (b) { b.disabled = false; });
      if (err.status === 422) showErrors(err.body.fields, err.body.error);
      else showErrors({}, err.message);
    });
  }

  function closeDrawer(force) {
    if (!drawerVisible()) return;
    if (!force && D && D.dirty) {
      confirmDialog({ title: 'Discard changes?', icon: false, body: h('p', { text: 'You have unsaved changes in this form.' }), confirmText: 'Discard', cancelText: 'Keep editing' })
        .then(function (ok) { if (ok) closeDrawer(true); });
      return;
    }
    el.drawer.hidden = true;
    el.drawer.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    D = null;
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }

  /* ------------------------------------------------------------------ theme */
  function effectiveDark() {
    var t = document.documentElement.dataset.theme;
    if (t) return t === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function syncThemeIcon() {
    $('#themeBtn use').setAttribute('href', effectiveDark() ? '#i-sun' : '#i-moon');
  }

  /* ------------------------------------------------------------------ wiring */
  $('#themeBtn').addEventListener('click', function () {
    var next = effectiveDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('studio-theme', next); } catch (e) { /* ignore */ }
    syncThemeIcon();
  });
  $('#menuBtn').addEventListener('click', openNav);
  $('#sidebarClose').addEventListener('click', closeNav);
  el.scrim.addEventListener('click', closeNav);
  $('#drawerClose').addEventListener('click', function () { closeDrawer(false); });
  el.drawer.addEventListener('mousedown', function (e) { if (e.target === el.drawer) closeDrawer(false); });
  // Form listeners are attached once here (the form element is reused every time the panel opens).
  el.drawerForm.addEventListener('input', function () { if (D) D.dirty = true; });
  el.drawerForm.addEventListener('change', function () { if (D) D.dirty = true; });
  el.drawerForm.addEventListener('submit', function (e) { e.preventDefault(); if (D && D.mode !== 'view') submitForm(false); });
  el.drawerForm.addEventListener('keydown', function (e) {
    var tag = e.target.tagName, type = e.target.type;
    if (e.key === 'Enter' && tag === 'INPUT' && type !== 'checkbox' && type !== 'file' && D && D.mode !== 'view') {
      e.preventDefault();
      submitForm(false);
    }
  });
  el.tableFilter.addEventListener('input', renderNav);
  window.addEventListener('hashchange', route);
  window.addEventListener('beforeunload', function (e) { if (D && D.dirty) { e.preventDefault(); e.returnValue = ''; } });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      if (openPopover) { closePopover(); return; }
      if (el.confirm.open) return;
      if (drawerVisible()) { closeDrawer(false); return; }
      closeNav();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && drawerVisible() && D && D.mode !== 'view') {
      e.preventDefault();
      submitForm(false);
      return;
    }
    if (typing(e.target) || e.ctrlKey || e.metaKey || e.altKey || el.confirm.open || drawerVisible()) return;
    if (e.key === '/' && S.cur) { e.preventDefault(); shell.search.focus(); }
    else if (e.key.toLowerCase() === 'n' && S.cur && S.cur.can_add) { e.preventDefault(); openDrawer('create'); }
    else if (e.key.toLowerCase() === 'r' && S.cur) { loadRows(); }
  });

  syncThemeIcon();
  api('tables/').then(function (res) {
    S.tables = res.tables;
    res.tables.forEach(function (t) { S.by[t.key] = t; });
    renderNav();
    route();
  }).catch(function (err) {
    el.view.replaceChildren(h('div', { class: 'notice notice--danger' }, icon('alert'), h('span', { text: 'Could not load tables: ' + err.message })));
  });
})();
