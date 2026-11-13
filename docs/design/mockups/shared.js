/* Mockup-only helper: language/RTL toggle + screen switch. Not product code. */
(function () {
  var qs = new URLSearchParams(location.search);
  var state = { lang: qs.get('lang') || 'en', screen: qs.get('screen') || 'home' };

  function apply() {
    var ar = state.lang === 'ar';
    document.documentElement.lang = state.lang;
    document.documentElement.dir = ar ? 'rtl' : 'ltr';
    document.querySelectorAll('[data-en]').forEach(function (el) {
      el.textContent = ar ? el.getAttribute('data-ar') : el.getAttribute('data-en');
    });
    document.querySelectorAll('[data-ph-en]').forEach(function (el) {
      el.setAttribute('placeholder', ar ? el.getAttribute('data-ph-ar') : el.getAttribute('data-ph-en'));
    });
    document.querySelectorAll('[data-screen]').forEach(function (el) {
      el.hidden = el.getAttribute('data-screen') !== state.screen;
    });
    document.querySelectorAll('.mk-bar button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.lang === state.lang || b.dataset.screen === state.screen));
    });
  }

  var bar = document.createElement('div');
  bar.className = 'mk-bar';
  bar.innerHTML =
    '<button data-screen="home">Home</button><button data-screen="chat">Chat</button><span></span>' +
    '<button data-lang="en">EN</button><button data-lang="ar">عربي</button>';
  var css = document.createElement('style');
  css.textContent =
    '[hidden]{display:none!important}' +
    '.mk-bar{position:fixed;z-index:99;bottom:14px;left:50%;transform:translateX(-50%);display:flex;gap:2px;align-items:center;' +
    'background:#111;color:#eee;padding:4px;border-radius:9px;font:500 12px/1 system-ui;box-shadow:0 4px 24px rgba(0,0,0,.25)}' +
    '.mk-bar span{width:1px;height:16px;background:#444;margin:0 4px}' +
    '.mk-bar button{all:unset;cursor:pointer;padding:7px 11px;border-radius:6px}' +
    '.mk-bar button[aria-pressed=true]{background:#fff;color:#111}';
  document.head.appendChild(css);
  document.addEventListener('DOMContentLoaded', function () {
    document.body.appendChild(bar);
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.lang) state.lang = b.dataset.lang;
      if (b.dataset.screen) state.screen = b.dataset.screen;
      apply();
    });
    apply();
  });
})();
