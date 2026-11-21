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

// An episode with a description opens and closes it with a click anywhere in its row,
// not only on the name (the <summary>, which the browser handles itself). The check
// button and the watched date keep their own clicks; a click into the open description
// or one that ends a text selection changes nothing (the text stays selectable).
document.addEventListener("click", (event) => {
  const row = event.target.closest(".episodes li");
  const details = row?.querySelector(":scope > .episode-body > details.episode-info");
  if (
    !details ||
    event.target.closest("summary, a, button, form, details.episode-watched, .episode-info > p") ||
    getSelection().toString()
  ) {
    return;
  }
  details.open = !details.open;
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

// The back button shows the previous page from the browser's caches (bfcache or HTTP cache)
// without asking the server. If something changed since the page was made (e.g. a show was
// followed on the next page), load the page again and morph its content into place, so
// unchanged posters don't flicker. The server stores the time of the last change in a
// cookie; pages carry the time they were made with (core/middleware.py).
function dataVersion() {
  return document.cookie.match(/(?:^|;\s*)couchowl_version=([^;]*)/)?.[1] ?? "";
}

async function refreshIfOutdated() {
  const main = document.querySelector("main[data-version]");
  if (!main || main.dataset.version === dataVersion()) {
    return;
  }
  let response;
  try {
    // "no-cache": ask the server, and replace the outdated copy in the HTTP cache
    response = await fetch(location.href, { cache: "no-cache" });
  } catch {
    return; // offline: keep what we have
  }
  if (response.redirected) {
    location.reload(); // e.g. logged out in the meantime
    return;
  }
  if (!response.ok) {
    return;
  }
  const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
  const freshMain = fresh.querySelector("main[data-version]");
  const root = document.documentElement;
  // A new interface language or theme changes more than the content: load everything
  if (
    !freshMain ||
    root.lang !== fresh.documentElement.lang ||
    root.dataset.theme !== fresh.documentElement.dataset.theme
  ) {
    location.reload();
    return;
  }
  document.title = fresh.title;
  Idiomorph.morph(main, freshMain); // also takes over the new data-version
  htmx.process(main);
}

window.addEventListener("pageshow", (event) => {
  const navigation = performance.getEntriesByType("navigation")[0];
  syncZoom(); // reloaded or came back (forward) to an open zoom dialog
  if (event.persisted) {
    // Restored from the bfcache with the spinner still running: reset it
    for (const form of document.querySelectorAll("form[data-busy]")) {
      delete form.dataset.busyActive;
      form.querySelector("[aria-busy]")?.removeAttribute("aria-busy");
    }
  }
  if (event.persisted || navigation?.type === "back_forward") {
    refreshIfOutdated();
  }
});

// htmx restores pages it changed the address of (hx-push-url) from its own snapshots
document.addEventListener("htmx:historyRestore", refreshIfOutdated);

// Links marked with data-zoom="<dialog id>" show their image (the link's target) in that
// dialog instead of opening it: first the small image (already loaded), then the large
// one as soon as it has loaded. Ctrl/Cmd/middle click still opens the image in a new tab.
// Opening adds a history entry, so the back button (Android) closes the dialog instead of
// leaving the page: the dialog is open exactly while that entry is the current one.
function showZoom(link) {
  const dialog = document.getElementById(link.dataset.zoom);
  const image = dialog?.querySelector("img");
  if (!image) {
    return;
  }
  if (image.src !== link.href) {
    image.src = link.querySelector("img")?.currentSrc || image.src;
    const large = new Image();
    large.src = link.href;
    large.decode().then(
      () => {
        image.src = large.src;
      },
      () => {}, // not available (e.g. TMDB down): keep the small image
    );
  }
  if (!dialog.open) {
    dialog.showModal();
  }
}

// Open or close the dialogs to match the current history entry
function syncZoom() {
  const zoom = history.state?.zoom;
  for (const dialog of document.querySelectorAll("dialog.zoom-dialog[open]")) {
    if (dialog.id !== zoom) {
      dialog.close();
    }
  }
  const link = zoom && document.querySelector(`a[data-zoom="${CSS.escape(zoom)}"]`);
  if (link) {
    showZoom(link);
  }
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-zoom]");
  if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) {
    return;
  }
  event.preventDefault();
  history.pushState({ zoom: link.dataset.zoom }, "");
  showZoom(link);
});

// A click anywhere in the zoom dialog (image, backdrop, close button) closes it
document.addEventListener("click", (event) => {
  event.target.closest("dialog.zoom-dialog")?.close();
});

// Closed by click or Esc: leave the dialog's history entry (back closes it on its own)
document.addEventListener(
  "close",
  (event) => {
    if (event.target.matches?.("dialog.zoom-dialog") && history.state?.zoom === event.target.id) {
      history.back();
    }
  },
  true, // "close" doesn't bubble
);

window.addEventListener("popstate", syncZoom);
