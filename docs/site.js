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

  // Deal filter chips (index page only)
  var chips = document.querySelectorAll('.chip[data-filter]');
  var cards = document.querySelectorAll('.deal-grid .deal');
  var empty = document.querySelector('.filter-empty');
  var tests = {
    all: function () { return true; },
    deep: function (c) { return parseFloat(c.dataset.off) >= 30; },
    under25: function (c) { return parseFloat(c.dataset.price) < 25; },
    bestseller: function (c) { return c.dataset.bs === '1'; },
    toprated: function (c) { return parseFloat(c.dataset.rating) >= 4.7; }
  };
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('is-active'); });
      chip.classList.add('is-active');
      var test = tests[chip.dataset.filter] || tests.all;
      var shown = 0;
      cards.forEach(function (card) {
        var ok = test(card);
        card.classList.toggle('filtered-out', !ok);
        if (ok) { shown++; card.classList.add('in'); }
      });
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
