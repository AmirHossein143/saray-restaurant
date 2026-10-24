/*!
 * Saray — site.js
 * Vanilla, dependency-free progressive enhancement. Every feature checks for
 * its own markup, so this single file serves all pages.
 */
(function () {
  'use strict';

  var d = document;
  var root = d.documentElement;
  var body = d.body;
  var motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  var reduceMotion = function () { return motionQuery.matches; };

  function $(sel, ctx) { return (ctx || d).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || d).querySelectorAll(sel)); }

  var FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
  function toFa(value) { return String(value).replace(/\d/g, function (n) { return FA_DIGITS[n]; }); }
  function toAscii(value) {
    return String(value)
      .replace(/[۰-۹]/g, function (c) { return String(c.charCodeAt(0) - 0x06F0); })
      .replace(/[٠-٩]/g, function (c) { return String(c.charCodeAt(0) - 0x0660); });
  }

  /* Normalise Persian text for search: Arabic ي/ك → ی/ک, drop ZWNJ, spaces,
     diacritics and tatweel, unify digits and alef forms. */
  function normalize(text) {
    return toAscii(String(text || '').toLowerCase())
      .replace(/[يى]/g, 'ی')
      .replace(/ك/g, 'ک')
      .replace(/[ةۀ]/g, 'ه')
      .replace(/[أإآٱ]/g, 'ا')
      .replace(/ؤ/g, 'و')
      .replace(/[ً-ْٰـ]/g, '')
      .replace(/[‌‍‎‏\s\-_.،,؛:()]+/g, '');
  }

  function smoothBehavior() { return reduceMotion() ? 'auto' : 'smooth'; }

  /* Tehran wall-clock time, independent of the visitor's own timezone. */
  function tehranNow() {
    try {
      var parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Tehran', hour: 'numeric', minute: 'numeric', weekday: 'short', hourCycle: 'h23',
        year: 'numeric', month: '2-digit', day: '2-digit'
      }).formatToParts(new Date());
      var o = {};
      parts.forEach(function (p) { o[p.type] = p.value; });
      var days = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
      return {
        minutes: (parseInt(o.hour, 10) % 24) * 60 + parseInt(o.minute, 10),
        weekday: days[o.weekday],
        iso: o.year + '-' + o.month + '-' + o.day
      };
    } catch (e) {
      var n = new Date();
      return { minutes: n.getHours() * 60 + n.getMinutes(), weekday: n.getDay(), iso: n.toISOString().slice(0, 10) };
    }
  }

  function parseHM(value) {
    var m = /^(\d{1,2}):(\d{2})/.exec(toAscii(value || ''));
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
  }

  /* ---------------------------------------------------------------------- */
  /* Image fallback: missing photos become the branded placeholder.          */
  /* ---------------------------------------------------------------------- */
  var placeholder = body.getAttribute('data-placeholder');
  function useFallback(img) {
    if (!placeholder || img.getAttribute('data-fell-back')) return;
    img.setAttribute('data-fell-back', '1');
    img.removeAttribute('srcset');
    img.src = placeholder;
    img.classList.add('is-placeholder');
  }
  d.addEventListener('error', function (e) {
    var t = e.target;
    if (t && t.tagName === 'IMG') useFallback(t);
  }, true);
  $$('img').forEach(function (img) {
    if (img.complete && img.naturalWidth === 0 && img.getAttribute('src')) useFallback(img);
  });

  /* ---------------------------------------------------------------------- */
  /* Header: condense on scroll; back-to-top button.                         */
  /* ---------------------------------------------------------------------- */
  var header = $('[data-header]');
  var toTop = $('[data-back-to-top]');
  var catTabs = $('[data-cat-tabs]');
  var callFab = $('.fab--call');
  var ticking = false;

  function onScroll() {
    var y = window.pageYOffset || root.scrollTop;
    if (header) header.classList.toggle('is-scrolled', y > 24);
    if (toTop) {
      var show = y > 900;
      if (show && toTop.hidden) { toTop.hidden = false; requestAnimationFrame(function () { toTop.classList.add('is-visible'); }); }
      else if (!show && !toTop.hidden && toTop.classList.contains('is-visible')) {
        toTop.classList.remove('is-visible');
        setTimeout(function () { if (!toTop.classList.contains('is-visible')) toTop.hidden = true; }, 350);
      }
    }
    if (callFab) callFab.classList.toggle('is-visible', y > 320);
    if (catTabs) catTabs.classList.toggle('is-stuck', catTabs.getBoundingClientRect().top <= headerOffset() + 1);
    if (spy) spy();
    ticking = false;
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
  }, { passive: true });

  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: smoothBehavior() });
      var main = $('#main');
      if (main) main.focus({ preventScroll: true });
    });
  }

  function headerOffset() {
    var v = getComputedStyle(root).getPropertyValue('--header-h-c');
    return parseInt(v, 10) || 64;
  }

  /* ---------------------------------------------------------------------- */
  /* Mobile drawer: focus trap, Esc, aria-expanded, inert background.        */
  /* ---------------------------------------------------------------------- */
  (function drawer() {
    var el = $('[data-drawer]');
    var openBtn = $('[data-drawer-open]');
    if (!el || !openBtn) return;
    var panel = $('.drawer__panel', el);
    var lastFocus = null;
    var outside = $$('body > *').filter(function (n) {
      return n !== el && !n.matches('script, svg.sprite, .skip-link');
    });
    var focusables = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

    function setInert(on) {
      outside.forEach(function (n) {
        if (on) { n.setAttribute('inert', ''); n.setAttribute('aria-hidden', 'true'); }
        else { n.removeAttribute('inert'); n.removeAttribute('aria-hidden'); }
      });
    }
    var isOpen = false, hideTimer = null, focusTimer = null;
    function open() {
      // Cancel a pending hide from a close() that is still animating out.
      clearTimeout(hideTimer); hideTimer = null;
      if (!isOpen) lastFocus = d.activeElement;
      isOpen = true;
      el.hidden = false;
      void el.offsetWidth;
      el.classList.add('is-open');
      openBtn.setAttribute('aria-expanded', 'true');
      setInert(true);
      root.style.overflow = 'hidden';
      d.removeEventListener('keydown', onKey);
      d.addEventListener('keydown', onKey);
      var first = $('[data-drawer-close].icon-btn', el) || panel;
      clearTimeout(focusTimer);
      focusTimer = setTimeout(function () { if (isOpen) first.focus(); }, 60);
    }
    function close(restore) {
      // Always restore the page state, even if the drawer looks closed already.
      var wasOpen = isOpen;
      isOpen = false;
      clearTimeout(focusTimer);
      el.classList.remove('is-open');
      openBtn.setAttribute('aria-expanded', 'false');
      setInert(false);
      root.style.overflow = '';
      d.removeEventListener('keydown', onKey);
      clearTimeout(hideTimer);
      hideTimer = setTimeout(function () { hideTimer = null; if (!isOpen) el.hidden = true; }, reduceMotion() ? 0 : 480);
      if (wasOpen && restore !== false && lastFocus && lastFocus.focus) lastFocus.focus();
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); return; }
      if (e.key !== 'Tab') return;
      var items = $$(focusables, panel).filter(function (n) { return n.offsetParent !== null; });
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (e.shiftKey && d.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && d.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    openBtn.addEventListener('click', open);
    $$('[data-drawer-close]', el).forEach(function (b) { b.addEventListener('click', function () { close(); }); });
    $$('a[href]', panel).forEach(function (a) {
      a.addEventListener('click', function () { close(false); });
    });
    window.addEventListener('resize', function () { if (isOpen && window.innerWidth >= 1024) close(false); });
  })();

  /* ---------------------------------------------------------------------- */
  /* Open-now indicator (Asia/Tehran), refreshed every minute.               */
  /* ---------------------------------------------------------------------- */
  (function openStatus() {
    var els = $$('[data-open-status]');
    if (!els.length) return;
    function label(mins) {
      if (mins >= 1439 || mins === 0) return 'نیمه‌شب';
      var h = Math.floor(mins / 60), m = mins % 60;
      return toFa(h + ':' + (m < 10 ? '0' : '') + m);
    }
    function update() {
      var now = tehranNow().minutes;
      els.forEach(function (el) {
        var o = parseHM(el.getAttribute('data-opens'));
        var c = parseHM(el.getAttribute('data-closes'));
        if (o === null || c === null) return;
        var close = c >= 1439 ? 1440 : c;
        var isOpen = close > o ? (now >= o && now < close) : (now >= o || now < close);
        var untilClose = (close - now + 1440) % 1440;
        var text, state;
        if (isOpen && untilClose <= 60) { state = 'is-closing'; text = 'به‌زودی می‌بندیم · تا ' + label(c); }
        else if (isOpen) { state = 'is-open'; text = 'الان باز هستیم · تا ' + label(c); }
        else { state = 'is-closed'; text = 'الان بسته‌ایم · از ساعت ' + label(o) + ' باز می‌شویم'; }
        el.classList.remove('is-open', 'is-closing', 'is-closed');
        el.classList.add(state);
        var t = $('[data-open-text]', el);
        if (t) t.textContent = text;
        el.hidden = false;
      });
    }
    update();
    setInterval(update, 60000);
  })();

  /* Today's row in the hours table */
  (function hoursToday() {
    var table = $('[data-hours]');
    if (!table) return;
    var row = $('tr[data-day="' + tehranNow().weekday + '"]', table);
    if (row) row.classList.add('is-today');
  })();

  /* OSM embed (only rendered when the owner has entered coordinates).
     Click-to-load: no request reaches openstreetmap.org until asked for. */
  (function mapEmbed() {
    $$('[data-map]').forEach(function (wrap) {
      var lat = parseFloat(wrap.getAttribute('data-lat'));
      var lng = parseFloat(wrap.getAttribute('data-lng'));
      var btn = $('[data-map-load]', wrap);
      var placeholder = $('[data-map-placeholder]', wrap);
      if (!btn || !placeholder || isNaN(lat) || isNaN(lng)) return;
      var fallback = $('[data-map-fallback]', wrap);
      var note = $('[data-map-note]', wrap);
      btn.hidden = false;
      if (note) note.hidden = false;
      if (fallback) fallback.hidden = true;
      btn.addEventListener('click', function () {
        var bbox = [lng - 0.006, lat - 0.0035, lng + 0.006, lat + 0.0035].map(function (n) { return n.toFixed(5); }).join(',');
        var frame = d.createElement('iframe');
        frame.title = 'نقشه‌ی محل رستوران';
        frame.setAttribute('referrerpolicy', 'no-referrer');
        frame.setAttribute('tabindex', '0');
        frame.src = 'https://www.openstreetmap.org/export/embed.html?bbox=' + bbox + '&layer=mapnik&marker=' + lat + ',' + lng;
        wrap.appendChild(frame);
        wrap.classList.add('is-loaded');
        placeholder.parentNode.removeChild(placeholder);
        frame.focus();
      });
    });
  })();

  /* ---------------------------------------------------------------------- */
  /* Scroll reveal                                                           */
  /* ---------------------------------------------------------------------- */
  (function reveal() {
    var items = $$('[data-reveal]');
    if (!items.length) return;
    if (!('IntersectionObserver' in window) || reduceMotion()) {
      items.forEach(function (n) { n.classList.add('is-visible'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('is-visible'); io.unobserve(en.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    items.forEach(function (n) { io.observe(n); });
  })();

  /* ---------------------------------------------------------------------- */
  /* Hero slideshow — crossfade + Ken Burns, pausable (WCAG 2.2.2).           */
  /* ---------------------------------------------------------------------- */
  (function slideshow() {
    var hero = $('[data-hero]');
    if (!hero) return;
    var slides = $$('.hero__slide', hero);
    var controls = $('[data-slide-controls]', hero);
    // Reduced motion: a single still image — the extra slides are never downloaded.
    if (slides.length < 2 || reduceMotion()) return;
    var dots = $$('[data-slide-to]', hero);
    var pauseBtn = $('[data-slide-pause]', hero);
    var DURATION = 7000;
    var index = 0, timer = null, userPaused = false, visible = true;
    hero.style.setProperty('--slide-dur', DURATION + 'ms');
    if (controls) controls.hidden = false;

    /* slides 2..n carry data-src/data-srcset; fetch them once the page has loaded */
    function loadSlide(img) {
      if (!img.hasAttribute('data-src')) return;
      if (img.getAttribute('data-srcset')) img.setAttribute('srcset', img.getAttribute('data-srcset'));
      img.src = img.getAttribute('data-src');
      img.removeAttribute('data-src');
      img.removeAttribute('data-srcset');
    }
    function ready(img) { return !img.hasAttribute('data-src') && img.complete && img.naturalWidth > 1; }
    function loadAll() { slides.forEach(loadSlide); }
    if (d.readyState === 'complete') setTimeout(loadAll, 200);
    else window.addEventListener('load', function () { setTimeout(loadAll, 200); });

    function show(i) {
      if (i === index) return;
      loadSlide(slides[(i + slides.length) % slides.length]);
      var prev = slides[index];
      prev.classList.add('is-leaving');
      prev.classList.remove('is-active');
      setTimeout(function () { prev.classList.remove('is-leaving'); }, 1900);
      index = (i + slides.length) % slides.length;
      var next = slides[index];
      // restart Ken Burns
      next.style.animation = 'none'; void next.offsetWidth; next.style.animation = '';
      next.classList.add('is-active');
      dots.forEach(function (dot, k) {
        var on = k === index;
        dot.classList.toggle('is-active', on);
        dot.setAttribute('aria-pressed', on ? 'true' : 'false');
        if (on) { dot.classList.remove('is-active'); void dot.offsetWidth; dot.classList.add('is-active'); }
      });
    }
    function running() { return !userPaused && visible && !d.hidden; }
    function schedule() {
      clearTimeout(timer);
      hero.classList.toggle('is-paused', !running());
      if (running()) timer = setTimeout(function () {
        var next = slides[(index + 1) % slides.length];
        // never crossfade into an image that has not arrived yet
        if (ready(next)) show(index + 1); else loadSlide(next);
        schedule();
      }, DURATION);
    }
    /* one state model: the label (and icon) says what the button will do */
    function syncPause() {
      if (!pauseBtn) return;
      $('use', pauseBtn).setAttribute('href', userPaused ? '#i-play' : '#i-pause');
      $('.sr-only', pauseBtn).textContent = userPaused ? 'پخش نمایش خودکار تصاویر' : 'توقف نمایش خودکار تصاویر';
    }
    dots.forEach(function (dot) {
      dot.addEventListener('click', function () { show(parseInt(dot.getAttribute('data-slide-to'), 10)); schedule(); });
    });
    if (pauseBtn) pauseBtn.addEventListener('click', function () { userPaused = !userPaused; syncPause(); schedule(); });
    d.addEventListener('visibilitychange', schedule);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (en) { visible = en[0].isIntersecting; schedule(); }).observe(hero);
    }
    syncPause();
    schedule();
  })();

  /* ---------------------------------------------------------------------- */
  /* Ember / spark canvas — cheap additive particles, pauses offscreen.      */
  /* ---------------------------------------------------------------------- */
  $$('canvas[data-embers]').forEach(function (canvas) {
    if (reduceMotion() || !canvas.getContext) return;
    var ctx = canvas.getContext('2d');
    var burst = canvas.getAttribute('data-embers-mode') === 'burst';
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    var W = 0, H = 0, parts = [], raf = null, onScreen = true;

    // pre-rendered glow sprite
    var sprite = d.createElement('canvas');
    sprite.width = sprite.height = 32;
    var sc = sprite.getContext('2d');
    var g = sc.createRadialGradient(16, 16, 0, 16, 16, 16);
    g.addColorStop(0, 'rgba(255,236,190,1)');
    g.addColorStop(0.25, 'rgba(255,184,92,.85)');
    g.addColorStop(0.6, 'rgba(226,120,40,.25)');
    g.addColorStop(1, 'rgba(200,80,20,0)');
    sc.fillStyle = g;
    sc.fillRect(0, 0, 32, 32);

    function resize() {
      var r = canvas.getBoundingClientRect();
      W = r.width; H = r.height;
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function spawn(fromBurst) {
      if (fromBurst) {
        var a = -Math.PI / 2 + (Math.random() - 0.5) * 2.4;
        var sp = 2 + Math.random() * 5;
        return { x: W / 2, y: H * 0.32, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, s: 3 + Math.random() * 6, life: 0, max: 70 + Math.random() * 60, g: 0.06, w: 0 };
      }
      return {
        x: Math.random() * W, y: H + 10,
        vx: (Math.random() - 0.5) * 0.25, vy: -(0.35 + Math.random() * 0.9),
        s: 2 + Math.random() * 5, life: 0, max: 220 + Math.random() * 260, g: 0,
        w: Math.random() * Math.PI * 2
      };
    }
    function target() { return Math.max(14, Math.min(64, Math.round(W / 22))); }
    function frame() {
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      if (parts.length < target() && Math.random() < 0.35) parts.push(spawn(false));
      for (var i = parts.length - 1; i >= 0; i--) {
        var p = parts[i];
        p.life++;
        p.w += 0.03;
        p.vx += Math.sin(p.w) * 0.012;
        p.vy += p.g;
        p.x += p.vx; p.y += p.vy;
        var t = p.life / p.max;
        if (t >= 1 || p.y < -20) { parts.splice(i, 1); continue; }
        var alpha = t < 0.15 ? t / 0.15 : 1 - (t - 0.15) / 0.85;
        ctx.globalAlpha = Math.max(0, alpha) * 0.85;
        var s = p.s * (1 - t * 0.5);
        ctx.drawImage(sprite, p.x - s, p.y - s, s * 2, s * 2);
      }
      ctx.globalAlpha = 1;
      raf = requestAnimationFrame(frame);
    }
    function start() { if (!raf && onScreen && !d.hidden) raf = requestAnimationFrame(frame); }
    function stop() { if (raf) cancelAnimationFrame(raf); raf = null; }

    resize();
    if (burst) for (var k = 0; k < 70; k++) parts.push(spawn(true));
    window.addEventListener('resize', resize);
    d.addEventListener('visibilitychange', function () { d.hidden ? stop() : start(); });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (en) { onScreen = en[0].isIntersecting; onScreen ? start() : stop(); }).observe(canvas);
    }
    start();
  });

  /* ---------------------------------------------------------------------- */
  /* Menu page: tabs + scroll-spy, live search, filters, dish dialog, print. */
  /* ---------------------------------------------------------------------- */
  var spy = null;
  (function menuPage() {
    var sections = $$('[data-cat]');
    if (!sections.length) return;
    var tabsList = $('[data-cat-tabs-list]');
    var tabs = $$('[data-tab]');
    var dishes = $$('[data-dish]');
    var tools = $('[data-menu-tools]');
    var search = $('[data-menu-search]');
    var clearBtn = $('[data-search-clear]');
    var status = $('[data-menu-status]');
    var empty = $('[data-menu-empty]');
    var filterBtns = $$('[data-filter]');
    var filter = 'all';
    var activeSlug = null;

    if (tools) tools.hidden = false;

    /* sticky-bar shortcut back to the search box and filter chips */
    var jump = $('[data-jump-search]');
    if (jump && tools && search) {
      jump.hidden = false;
      jump.addEventListener('click', function () {
        var top = tools.getBoundingClientRect().top + window.pageYOffset - headerOffset() - 12;
        window.scrollTo({ top: Math.max(0, top), behavior: smoothBehavior() });
        search.focus({ preventScroll: true });
      });
    }

    function offset() {
      var tabsH = catTabs ? catTabs.offsetHeight : 0;
      return headerOffset() + tabsH + 12;
    }

    /* scroll the active tab into view inside the horizontal list (RTL-safe) */
    function revealTab(tab) {
      if (!tabsList || !tab) return;
      var lr = tabsList.getBoundingClientRect();
      var tr = tab.getBoundingClientRect();
      var delta = (tr.left + tr.width / 2) - (lr.left + lr.width / 2);
      tabsList.scrollBy({ left: delta, behavior: smoothBehavior() });
    }
    function setActive(slug) {
      if (slug === activeSlug) return;
      activeSlug = slug;
      tabs.forEach(function (t) {
        var on = t.getAttribute('data-tab') === slug;
        t.classList.toggle('is-active', on);
        if (on) { t.setAttribute('aria-current', 'location'); revealTab(t); }
        else t.removeAttribute('aria-current');
      });
    }
    spy = function () {
      var line = offset() + 8;
      var current = null;
      for (var i = 0; i < sections.length; i++) {
        var s = sections[i];
        if (s.hidden) continue;
        if (s.getBoundingClientRect().top <= line) current = s.id;
        else break;
      }
      if (!current) {
        var firstVisible = sections.filter(function (s) { return !s.hidden; })[0];
        current = firstVisible ? firstVisible.id : null;
      }
      setActive(current);
    };

    function scrollToEl(el) {
      var top = el.getBoundingClientRect().top + window.pageYOffset - offset() + 4;
      window.scrollTo({ top: Math.max(0, top), behavior: smoothBehavior() });
    }
    tabs.forEach(function (t) {
      t.addEventListener('click', function (e) {
        var target = d.getElementById(t.getAttribute('data-tab'));
        if (!target) return;
        e.preventDefault();
        setActive(target.id);
        scrollToEl(target);
        if (history.replaceState) history.replaceState(null, '', '#' + target.id);
        var heading = $('h2', target);
        if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: true }); }
      });
    });

    /* search + filters */
    dishes.forEach(function (el) { el._q = normalize(el.getAttribute('data-search')); });
    function apply() {
      var q = normalize(search ? search.value : '');
      var filtering = !!q || filter !== 'all';
      var shown = 0;
      dishes.forEach(function (el) {
        var ok = !filtering || ((!q || el._q.indexOf(q) !== -1) &&
          (filter === 'all' || el.getAttribute('data-' + filter) === '1'));
        el.hidden = !ok;
        if (ok) shown++;
      });
      sections.forEach(function (s) {
        // With no search/filter every category is shown again, whatever it held.
        var any = !filtering || $$('[data-dish]', s).some(function (el) { return !el.hidden; });
        s.hidden = !any;
        var tab = tabs.filter(function (t) { return t.getAttribute('data-tab') === s.id; })[0];
        if (tab) {
          tab.classList.toggle('is-empty', !any);
          if (!any) tab.setAttribute('aria-disabled', 'true'); else tab.removeAttribute('aria-disabled');
        }
      });
      root.classList.toggle('is-menu-filtered', filtering);
      if (jump) $('.sr-only', jump).textContent = filtering ? 'جست‌وجو و فیلتر غذاها (فیلتر فعال است)' : 'جست‌وجو و فیلتر غذاها';
      if (status) status.textContent = filtering ? (shown ? toFa(shown) + ' غذا پیدا شد' : 'غذایی پیدا نشد') : '';
      if (empty) empty.hidden = shown !== 0;
      if (clearBtn) clearBtn.hidden = !(search && search.value);
      activeSlug = null;
      if (spy) spy();
    }
    var debounce;
    if (search) {
      search.addEventListener('input', function () { clearTimeout(debounce); debounce = setTimeout(apply, 110); });
      search.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && search.value) { e.preventDefault(); search.value = ''; apply(); }
        if (e.key === 'Enter') { e.preventDefault(); var first = sections.filter(function (s) { return !s.hidden; })[0]; if (first) scrollToEl(first); }
      });
    }
    if (clearBtn) clearBtn.addEventListener('click', function () { search.value = ''; apply(); search.focus(); });
    filterBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        filter = b.getAttribute('data-filter');
        filterBtns.forEach(function (x) {
          var on = x === b;
          x.classList.toggle('is-active', on);
          x.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        apply();
      });
    });
    var reset = $('[data-menu-reset]');
    if (reset) reset.addEventListener('click', function () {
      if (search) search.value = '';
      filter = 'all';
      filterBtns.forEach(function (x) {
        var on = x.getAttribute('data-filter') === 'all';
        x.classList.toggle('is-active', on);
        x.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      apply();
      if (search) search.focus();
    });

    /* dish dialog */
    var dialog = $('[data-dish-dialog]');
    if (dialog && typeof dialog.showModal === 'function') {
      var dImg = $('[data-dd-img]', dialog);
      var opener = null;
      $$('.dish__hit').forEach(function (btn) {
        btn.hidden = false;
        btn.addEventListener('click', function () {
          var card = btn.closest('[data-dish]');
          opener = btn;
          var name = $('.dish__name', card).textContent;
          $('[data-dd-title]', dialog).textContent = name;
          $('[data-dd-cat]', dialog).textContent = card.getAttribute('data-category') || '';
          var en = $('.dish__en', card);
          $('[data-dd-en]', dialog).textContent = en ? en.textContent : '';
          var desc = $('.dish__desc', card);
          $('[data-dd-desc]', dialog).textContent = desc ? desc.textContent : '';
          var priceBox = $('[data-dd-price]', dialog);
          priceBox.innerHTML = '';
          var price = $('.dish__head .price', card);
          var variants = $('.variants', card);
          if (variants) priceBox.appendChild(variants.cloneNode(true));
          else if (price) priceBox.appendChild(price.cloneNode(true));
          var badgeBox = $('[data-dd-badges]', dialog);
          badgeBox.innerHTML = '';
          var badges = $('.badges', card);
          if (badges) badgeBox.appendChild(badges.cloneNode(true));
          // Drop the previous dish's photo first so it never flashes; the
          // media box shows its dark background until the new one decodes.
          var media = dImg.parentNode;
          dImg.removeAttribute('src');
          dImg.removeAttribute('srcset');
          dImg.removeAttribute('data-fell-back');
          dImg.classList.remove('is-placeholder');
          media.classList.add('is-loading');
          dImg.alt = name;
          dImg.onload = dImg.onerror = function () { media.classList.remove('is-loading'); };
          dImg.src = card.getAttribute('data-photo');
          root.classList.add('has-dialog');
          dialog.showModal();
        });
      });
      var closeDialog = function () { dialog.close(); };
      $('[data-dialog-close]', dialog).addEventListener('click', closeDialog);
      dialog.addEventListener('click', function (e) { if (e.target === dialog) closeDialog(); });
      dialog.addEventListener('close', function () {
        root.classList.remove('has-dialog');
        if (opener) opener.focus({ preventScroll: true });
      });
    }

    /* print */
    var printBtn = $('[data-print]');
    if (printBtn && window.print) {
      printBtn.hidden = false;
      printBtn.addEventListener('click', function () { window.print(); });
    }

    /* deep links: #dish-slug or #category */
    function fromHash() {
      var id = decodeURIComponent((location.hash || '').slice(1));
      if (!id) return;
      var el = d.getElementById(id);
      if (!el) return;
      setTimeout(function () {
        scrollToEl(el);
        if (el.hasAttribute('data-dish')) {
          el.classList.remove('is-target'); void el.offsetWidth; el.classList.add('is-target');
        }
      }, 80);
    }
    window.addEventListener('hashchange', fromHash);
    if (location.hash) window.addEventListener('load', fromHash);
    spy();
  })();

  /* ---------------------------------------------------------------------- */
  /* Reservation form: chips scroller, today's slots, guests stepper, hints. */
  /* ---------------------------------------------------------------------- */
  (function reservation() {
    var form = $('[data-reserve-form]');
    if (!form) return;
    var dateWrap = $('[data-date-chips]', form);
    var dateInputs = $$('input[name="date"]', form);
    var timeInputs = $$('input[name="time"]', form);
    var timeHint = $('[data-time-hint]', form);
    var timeStep = $('[data-time-step]', form);
    var summary = $('[data-reserve-summary]', form);
    var guests = $('input[name="guests"]', form);
    var guestsHint = $('[data-guests-hint]', form);
    var phone = $('input[name="phone"]', form);
    var nameI = $('input[name="name"]', form);
    var submit = $('[data-submit]', form);
    var clientAlert = $('[data-client-alert]', form);
    var MIN_LEAD = 60;

    function checked(list) { return list.filter(function (i) { return i.checked; })[0] || null; }

    /* aria-describedby helpers: append/remove one id without clobbering others */
    function descIds(el) { return (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean); }
    function addDesc(el, id) {
      if (!el || !id) return;
      var ids = descIds(el);
      if (ids.indexOf(id) === -1) ids.push(id);
      el.setAttribute('aria-describedby', ids.join(' '));
    }
    function removeDesc(el, id) {
      if (!el) return;
      var ids = descIds(el).filter(function (x) { return x !== id; });
      if (ids.length) el.setAttribute('aria-describedby', ids.join(' '));
      else el.removeAttribute('aria-describedby');
    }

    /* static hints (phone, notes) describe their field */
    $$('[data-hint-for]', form).forEach(function (h) {
      addDesc(d.getElementById(h.getAttribute('data-hint-for')), h.id);
    });

    /* errors from the server: focus the summary. Django already renders
       aria-invalid + aria-describedby="<id>_error" pointing at .field__errors */
    var alertBox = $('[data-form-alert]', form);
    if (alertBox) {
      alertBox.focus({ preventScroll: true });
      setTimeout(function () { alertBox.scrollIntoView({ block: 'center', behavior: smoothBehavior() }); }, 120);
    }
    $$('.has-error', form).forEach(function (f) {
      var err = $('.field__errors', f);
      $$('input:not([type=radio]), select, textarea', f).forEach(function (i) {
        i.setAttribute('aria-invalid', 'true');
        if (err) addDesc(i, err.id);
      });
    });

    /* field-level error state (server or client), cleared once the value is fixed */
    function fieldBox(control) { return control.closest('.field') || control.closest('.step'); }
    function clearError(control) {
      var box = fieldBox(control);
      if (!box) return;
      $$('.field__errors', box).forEach(function (err) {
        [box].concat($$('input, select, textarea', box)).forEach(function (n) { removeDesc(n, err.id); });
        err.parentNode.removeChild(err);
      });
      box.classList.remove('has-error');
      $$('[aria-invalid]', box).forEach(function (n) { n.removeAttribute('aria-invalid'); });
      if (clientAlert && !$('.has-error', form)) { clientAlert.hidden = true; clientAlert.textContent = ''; }
    }
    function showError(control, msg) {
      var box = fieldBox(control);
      if (!box) return;
      clearError(control);
      var wrap = d.createElement('div');
      wrap.className = 'field__errors';
      wrap.id = 'client-err-' + (control.name || 'field');
      var p = d.createElement('p');
      p.className = 'field__error';
      p.textContent = msg;
      wrap.appendChild(p);
      box.appendChild(wrap);
      box.classList.add('has-error');
      if (box.tagName === 'FIELDSET') {
        addDesc(box, wrap.id);
      } else {
        control.setAttribute('aria-invalid', 'true');
        addDesc(control, wrap.id);
      }
    }

    function phoneDigits() {
      return toAscii(phone.value).replace(/[\s\-‐-―().‌‎‏]/g, '').replace(/^\+98|^0098/, '0');
    }
    /* mirrors the server's accepted shapes; never stricter than the server */
    function phoneLooksValid() {
      var n = phoneDigits();
      return /^0\d{10}$/.test(n) || /^9\d{9}$/.test(n) || /^98\d{10}$/.test(n);
    }
    var checks = {
      name: function () { return !!nameI && nameI.value.trim().length >= 2; },
      phone: function () { return !!phone && !!phone.value.trim() && phoneLooksValid(); },
      time: function () { return !!checked(timeInputs); },
      date: function () { return !!checked(dateInputs); },
      guests: function () { var v = parseInt(toAscii(guests.value), 10); return v >= 1 && v <= 20; }
    };
    function onFix(e) {
      var t = e.target;
      if (!t || !t.name || !checks[t.name]) return;
      var box = fieldBox(t);
      if (box && box.classList.contains('has-error') && checks[t.name]()) clearError(t);
    }
    form.addEventListener('input', onFix);
    form.addEventListener('change', onFix);

    /* date scroller arrows */
    var wrap = $('[data-scroller-wrap]', form);
    if (wrap && dateWrap && window.matchMedia && matchMedia('(hover: hover) and (pointer: fine)').matches) {
      var btns = $$('[data-scroll-dir]', wrap);
      btns.forEach(function (b) {
        b.hidden = false;
        b.addEventListener('click', function () {
          // RTL: "next" (later dates) lies to the left
          var dir = parseInt(b.getAttribute('data-scroll-dir'), 10);
          dateWrap.scrollBy({ left: -dir * dateWrap.clientWidth * 0.75, behavior: smoothBehavior() });
        });
      });
      var syncArrows = function () {
        var max = dateWrap.scrollWidth - dateWrap.clientWidth;
        var pos = Math.abs(dateWrap.scrollLeft);
        btns[0].classList.toggle('is-off', pos < 4);
        btns[1].classList.toggle('is-off', pos > max - 4);
      };
      dateWrap.addEventListener('scroll', syncArrows, { passive: true });
      syncArrows();
    }

    function centerChip(input) {
      if (!dateWrap || !input) return;
      var chip = input.closest('.date-chip');
      var lr = dateWrap.getBoundingClientRect(), cr = chip.getBoundingClientRect();
      if (cr.left < lr.left || cr.right > lr.right) {
        dateWrap.scrollBy({ left: (cr.left + cr.width / 2) - (lr.left + lr.width / 2), behavior: smoothBehavior() });
      }
    }

    function tooSoonToday(t, now) {
      var mins = parseHM(t.value);
      return t.getAttribute('data-today-ok') === '0' || (mins !== null && mins < now + MIN_LEAD);
    }

    function setTimeHint(text, warn) {
      if (!timeHint) return;
      if (text) {
        timeHint.textContent = text;
        timeHint.className = 'field__hint' + (warn ? ' field__hint--warn' : '');
        timeHint.hidden = false;
        addDesc(timeStep, timeHint.id);
      } else {
        timeHint.hidden = true;
        removeDesc(timeStep, timeHint.id);
      }
    }

    function updateTimes() {
      var dInput = checked(dateInputs);
      var isToday = dInput && dInput.getAttribute('data-today') === '1';
      var now = tehranNow().minutes;
      var available = 0, cleared = false;
      timeInputs.forEach(function (t) {
        var tooSoon = isToday && tooSoonToday(t, now);
        t.disabled = !!tooSoon;
        if (tooSoon && t.checked) { t.checked = false; cleared = true; }
        if (!tooSoon) available++;
      });
      if (isToday && available === 0) {
        setTimeHint('برای امروز دیگر ساعت خالی نداریم؛ لطفاً روز دیگری را انتخاب کنید.', true);
      } else if (isToday && available < timeInputs.length) {
        setTimeHint(cleared
          ? 'ساعت انتخابی شما برای امروز گذشته است؛ لطفاً ساعت دیگری انتخاب کنید.'
          : 'برای امروز، رزرو دست‌کم یک ساعت زودتر ممکن است؛ ساعت‌های گذشته غیرفعال شده‌اند.', cleared);
      } else {
        setTimeHint('');
      }
    }

    /* Summary built from DOM nodes; a visually hidden "، " keeps the parts
       apart for screen readers (date, time and guest count never merge). */
    function summaryPart(icon, text, first) {
      var span = d.createElement('span');
      if (!first) {
        var sep = d.createElement('span');
        sep.className = 'sr-only';
        sep.textContent = '، ';
        span.appendChild(sep);
      }
      span.insertAdjacentHTML('beforeend', '<svg class="icon icon--sm" aria-hidden="true"><use href="#i-' + icon + '"/></svg>');
      span.appendChild(d.createTextNode(text));
      return span;
    }
    function updateSummary() {
      if (!summary) return;
      var dI = checked(dateInputs), tI = checked(timeInputs);
      var g = guests ? parseInt(toAscii(guests.value), 10) : 0;
      if (!dI || !tI) { summary.hidden = true; return; }
      summary.textContent = '';
      summary.appendChild(summaryPart('calendar', (dI.getAttribute('data-today') === '1' ? 'امروز، ' : '') + dI.getAttribute('data-label'), true));
      summary.appendChild(summaryPart('clock', 'ساعت ' + tI.getAttribute('data-label')));
      if (g > 0) summary.appendChild(summaryPart('users', toFa(g) + ' نفر'));
      summary.hidden = false;
    }

    dateInputs.forEach(function (i) {
      i.addEventListener('change', function () { centerChip(i); updateTimes(); updateSummary(); });
    });
    timeInputs.forEach(function (i) { i.addEventListener('change', function () { if (timeHint && timeHint.classList.contains('field__hint--warn')) updateTimes(); updateSummary(); }); });

    /* Today with no bookable slot left (the server marks it too; this also
       covers a page left open past the last slot): show a subtle "full" pill,
       disable the chip and select the next day instead of switching silently. */
    function markTodayFull(input) {
      var chip = input.closest('.date-chip');
      input.disabled = true;
      input.checked = false;
      input.removeAttribute('required');
      if (chip && !chip.classList.contains('is-full')) {
        chip.classList.add('is-full');
        var face = $('.date-chip__face', chip);
        if (face && !$('.date-chip__full', face)) {
          var pill = d.createElement('span');
          pill.className = 'date-chip__full';
          pill.textContent = 'تکمیل';
          var sr = d.createElement('span');
          sr.className = 'sr-only';
          sr.textContent = '؛ برای امروز ساعت خالی نمانده است';
          pill.appendChild(sr);
          face.appendChild(pill);
        }
      }
    }
    (function ensureDate() {
      var todayI = dateInputs.filter(function (i) { return i.getAttribute('data-today') === '1'; })[0];
      if (todayI) {
        var now = tehranNow().minutes;
        var full = timeInputs.length > 0 && timeInputs.every(function (t) { return tooSoonToday(t, now); });
        if (full || todayI.disabled) markTodayFull(todayI);
      }
      if (!checked(dateInputs)) {
        var firstOpen = dateInputs.filter(function (i) { return !i.disabled; })[0];
        if (firstOpen) firstOpen.checked = true;
      }
      updateTimes();
      centerChip(checked(dateInputs));
    })();

    /* guests stepper */
    if (guests) {
      var min = parseInt(guests.getAttribute('min'), 10) || 1;
      var max = parseInt(guests.getAttribute('max'), 10) || 20;
      var stepBtns = $$('[data-step]', form);
      var syncGuests = function (tried) {
        var v = parseInt(toAscii(guests.value), 10);
        stepBtns.forEach(function (b) {
          var s = parseInt(b.getAttribute('data-step'), 10);
          b.disabled = isNaN(v) ? false : (s < 0 ? v <= min : v >= max);
        });
        if (guestsHint) {
          guestsHint.hidden = !(tried || v >= max);
          if (guestsHint.hidden) removeDesc(guests, guestsHint.id); else addDesc(guests, guestsHint.id);
        }
        updateSummary();
      };
      stepBtns.forEach(function (b) {
        b.hidden = false;
        b.addEventListener('click', function () {
          var v = parseInt(toAscii(guests.value), 10);
          if (isNaN(v)) v = 2;
          var next = v + parseInt(b.getAttribute('data-step'), 10);
          var tried = next > max;
          guests.value = Math.max(min, Math.min(max, next));
          syncGuests(tried);
          if (checks.guests()) clearError(guests);
        });
      });
      guests.addEventListener('input', function () { syncGuests(false); });
      if (!guests.value) guests.value = 2;
      syncGuests(false);
    }

    /* phone: gentle format hint on blur (the hint is the field's description) */
    if (phone) {
      var phoneHint = $('[data-phone-hint]', form);
      var original = phoneHint ? phoneHint.textContent : '';
      phone.addEventListener('blur', function () {
        if (!phoneHint) return;
        if (phone.value.trim() && !phoneLooksValid()) {
          phoneHint.textContent = 'شماره را کامل و با پیش‌شماره وارد کنید؛ مثلاً ۰۹۱۲۳۴۵۶۷۸۹';
          phoneHint.classList.add('field__hint--warn');
        } else {
          phoneHint.textContent = original;
          phoneHint.classList.remove('field__hint--warn');
        }
      });
    }

    /* client-side guard for the obvious misses, then prevent double submit */
    var submitLabel = submit ? $('span', submit) : null;
    var submitText = submitLabel ? submitLabel.textContent : '';
    form.addEventListener('submit', function (e) {
      var problems = [];
      function flag(control, msg, label) {
        showError(control, msg);
        problems.push({ el: control, label: label });
      }
      if (!checked(timeInputs)) {
        var firstTime = timeInputs.filter(function (t) { return !t.disabled; })[0] || timeInputs[0];
        if (firstTime) flag(firstTime, 'لطفاً ساعت رزرو را انتخاب کنید.', 'ساعت');
      }
      if (nameI && !checks.name()) flag(nameI, 'لطفاً نام خود را وارد کنید.', 'نام');
      if (phone && !phone.value.trim()) flag(phone, 'لطفاً شماره‌ی تماس خود را وارد کنید.', 'شماره‌ی تماس');
      if (problems.length) {
        e.preventDefault();
        if (clientAlert) {
          clientAlert.textContent = 'رزرو ثبت نشد؛ لطفاً این موارد را کامل کنید: ' +
            problems.map(function (p) { return p.label; }).join('، ') + '.';
          clientAlert.hidden = false;
        }
        var first = problems[0].el;
        first.focus({ preventScroll: true });
        first.scrollIntoView({ block: 'center', behavior: smoothBehavior() });
        return;
      }
      if (submit) {
        submit.disabled = true;
        if (submitLabel) submitLabel.textContent = 'در حال ثبت…';
      }
    });
    /* back/forward cache: restore the button if the page comes back */
    window.addEventListener('pageshow', function (e) {
      if (e.persisted && submit) {
        submit.disabled = false;
        if (submitLabel) submitLabel.textContent = submitText;
      }
    });

    updateSummary();
  })();

  /* ---------------------------------------------------------------------- */
  /* Done page: copy the reservation code.                                   */
  /* ---------------------------------------------------------------------- */
  (function copyCode() {
    var btn = $('[data-copy-code]');
    var source = $('[data-copy-source]');
    if (!btn || !source) return;
    var label = $('[data-copy-label]', btn);
    var status = $('[data-copy-status]');
    var original = label ? label.textContent : '';
    var resetTimer = null;
    btn.hidden = false;

    function selectSource() {
      var sel = window.getSelection && window.getSelection();
      if (!sel) return false;
      var range = d.createRange();
      range.selectNodeContents(source);
      sel.removeAllRanges();
      sel.addRange(range);
      return true;
    }
    function legacyCopy() {
      try { return selectSource() && d.execCommand && d.execCommand('copy'); } catch (e) { return false; }
    }
    function report(ok) {
      var msg = ok ? 'کپی شد' : 'کد انتخاب شد؛ آن را کپی کنید';
      if (label) label.textContent = ok ? msg : original;
      if (status) status.textContent = ok ? 'کد رزرو کپی شد.' : msg + '.';
      btn.classList.toggle('is-done', ok);
      clearTimeout(resetTimer);
      resetTimer = setTimeout(function () {
        if (label) label.textContent = original;
        btn.classList.remove('is-done');
        if (status) status.textContent = '';
      }, 2400);
    }
    btn.addEventListener('click', function () {
      var code = source.textContent.trim();
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(code).then(function () { report(true); }, function () { report(legacyCopy()); });
      } else {
        var ok = legacyCopy();
        if (!ok) selectSource();
        report(ok);
      }
    });
  })();

  /* initial paint of scroll-dependent state */
  onScroll();
})();
