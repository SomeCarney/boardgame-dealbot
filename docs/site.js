(function () {
  var header = document.querySelector('.site-header');
  var toTop = document.querySelector('.to-top');

  // Hysteresis: shrink at 48px, expand only back at 8px. A single threshold
  // makes the header's own height change re-cross the threshold and the page
  // visibly vibrates when resting near the top.
  var shrunk = false;
  function onScroll() {
    var y = window.scrollY;
    if (header) {
      if (!shrunk && y > 48) { shrunk = true; header.classList.add('scrolled'); }
      else if (shrunk && y < 8) { shrunk = false; header.classList.remove('scrolled'); }
    }
    if (toTop) toTop.classList.toggle('show', y > 600);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if (toTop) {
    toTop.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  var toggle = document.querySelector('.nav-toggle');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        nav.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  // Deal filter/sort chips (index page only)
  var chips = document.querySelectorAll('.chip');
  var grid = document.querySelector('.deal-grid');
  var cards = document.querySelectorAll('.deal-grid .deal');
  var order = Array.prototype.slice.call(cards);  // original DOM order (newest first)
  var empty = document.querySelector('.filter-empty');
  var tests = {
    all: function () { return true; },
    under25: function (c) { return parseFloat(c.dataset.price) < 25; },
    bestseller: function (c) { return c.dataset.bs === '1'; }
  };
  var sorts = {
    'off-desc': function (a, b) { return parseFloat(b.dataset.off) - parseFloat(a.dataset.off); },
    'rating-desc': function (a, b) { return parseFloat(b.dataset.rating) - parseFloat(a.dataset.rating); }
  };
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('is-active'); });
      chip.classList.add('is-active');
      var shown = 0;
      var sortFn = sorts[chip.dataset.sort];
      if (sortFn) {
        // Sort mode: show every card, reordered (deepest cut / highest rating first).
        order.slice().sort(sortFn).forEach(function (card) {
          card.classList.remove('filtered-out');
          card.classList.add('in');
          if (grid) grid.appendChild(card);
          shown++;
        });
      } else {
        // Restore the original newest-first order, then apply the filter.
        var test = tests[chip.dataset.filter] || tests.all;
        order.forEach(function (card) {
          if (grid) grid.appendChild(card);
          var ok = test(card);
          card.classList.toggle('filtered-out', !ok);
          if (ok) { shown++; card.classList.add('in'); }
        });
      }
      if (empty) empty.hidden = shown !== 0;
    });
  });

  // Scroll-reveal
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var revealEls = document.querySelectorAll('.reveal');
  if (reduced || !('IntersectionObserver' in window)) {
    revealEls.forEach(function (el) { el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -40px 0px', threshold: 0.05 });
    revealEls.forEach(function (el) { io.observe(el); });
  }
})();
