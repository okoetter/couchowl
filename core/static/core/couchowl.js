// Couch Owl's own JavaScript. Keep this small: htmx and Alpine.js do most of the work.

// A link to the anchor that is already in the URL (e.g. clicking "Next: S1 E3" twice)
// only scrolls: the browser doesn't restart the :target highlight (see couchowl.css).
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

// Forms marked with data-busy may take a few seconds ("Refresh all" asks TMDB for every
// followed show): show Pico's spinner on the button and prevent a second click.
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.matches("form[data-busy]") || event.defaultPrevented) {
    return;
  }
  const button = event.submitter || form.querySelector("button[type='submit']");
  if (form.dataset.busyActive) {
    event.preventDefault();
    return;
  }
  form.dataset.busyActive = "true";
  if (button) {
    button.setAttribute("aria-busy", "true");
  }
});

// Coming back with the back button can restore the page from the browser's cache
// ("bfcache") with the spinner still running: reset it.
window.addEventListener("pageshow", (event) => {
  if (!event.persisted) {
    return;
  }
  for (const form of document.querySelectorAll("form[data-busy]")) {
    delete form.dataset.busyActive;
    form.querySelector("[aria-busy]")?.removeAttribute("aria-busy");
  }
});
