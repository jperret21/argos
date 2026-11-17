// The Graphviz diagrams follow the documentation's theme, Furo's toggle included.
// Each diagram is an SVG in an <object>, a separate document that reads only the
// system's colour scheme; this marks its root "diagram-dark" or "diagram-light"
// from the page's own theme (_static/diagrams.css holds the colours).
(function () {
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  function isDark() {
    var t = document.body.dataset.theme;
    return t === "dark" || (t !== "light" && mq.matches);
  }
  function paint(o) {
    try {
      var root = o.contentDocument && o.contentDocument.documentElement;
      if (!root || !root.classList) return;
      var dark = isDark();
      root.classList.toggle("diagram-dark", dark);
      root.classList.toggle("diagram-light", !dark);
    } catch (e) {
      // not readable (another origin, file://): the system's scheme decides
    }
  }
  function paintAll() {
    document.querySelectorAll("object.graphviz").forEach(paint);
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("object.graphviz").forEach(function (o) {
      o.addEventListener("load", function () { paint(o); });
      paint(o);
    });
    new MutationObserver(paintAll).observe(document.body, { attributes: true, attributeFilter: ["data-theme"] });
    if (mq.addEventListener) mq.addEventListener("change", paintAll);
  });
})();
