(function () {
  'use strict';

  var drawer = document.querySelector('.site-mobile-menu');
  var toggle = document.querySelector('.site-menu-toggle');
  var navigation = document.querySelector('.js-clone-nav');
  if (!drawer || !toggle || !navigation) return;

  var mobileNavigation = navigation.cloneNode(true);
  mobileNavigation.className = 'site-nav-wrap';
  drawer.querySelector('.site-mobile-menu-body').appendChild(mobileNavigation);

  function setMenu(open, restoreFocus) {
    document.body.classList.toggle('offcanvas-menu', open);
    drawer.setAttribute('aria-hidden', String(!open));
    drawer.inert = !open;
    document.querySelectorAll('.js-menu-toggle').forEach(function (button) {
      button.setAttribute('aria-expanded', String(open));
    });
    if (open) drawer.querySelector('button').focus();
    else if (restoreFocus) toggle.focus();
  }

  document.querySelectorAll('.js-menu-toggle').forEach(function (button) {
    button.addEventListener('click', function () {
      setMenu(!document.body.classList.contains('offcanvas-menu'), true);
    });
  });

  mobileNavigation.addEventListener('click', function (event) {
    if (event.target.closest('a')) setMenu(false, true);
  });

  document.addEventListener('click', function (event) {
    if (document.body.classList.contains('offcanvas-menu') &&
        !drawer.contains(event.target) && !toggle.contains(event.target)) {
      setMenu(false, true);
    }
  });

  document.addEventListener('keydown', function (event) {
    if (!document.body.classList.contains('offcanvas-menu')) return;
    if (event.key === 'Escape') {
      setMenu(false, true);
    } else if (event.key === 'Tab') {
      var controls = drawer.querySelectorAll('button, a[href]');
      var first = controls[0];
      var last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  window.addEventListener('resize', function () {
    if (window.innerWidth >= 1200) setMenu(false, false);
  });
}());
