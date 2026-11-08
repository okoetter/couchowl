// watchit's own JavaScript. Keep this small: htmx and Alpine.js do most of the work.

// A link to the anchor that is already in the URL (e.g. clicking "Next: S1 E3" twice)
// only scrolls: the browser doesn't restart the :target highlight (see watchit.css).
// Restart it by removing the animation for one frame.
document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href*='#']");
  if (
    !link ||
    !link.hash ||
    link.hash !== location.hash ||
    link.pathname !== location.pathname ||
    link.search !== location.search
  ) {
    return;
  }
  const target = document.getElementById(decodeURIComponent(link.hash.slice(1)));
  if (target) {
    target.style.animation = "none";
    void target.offsetWidth; // force the browser to apply "none" before removing it again
    target.style.animation = "";
  }
});
