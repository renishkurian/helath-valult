(function () {
  "use strict";

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }

  if (window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone) {
    document.documentElement.classList.add("pwa-standalone");
  }

  // Do not call preventDefault on beforeinstallprompt and do not show an
  // Install button. Google OAuth review treats that as forcing an install.
  // The manifest stays, so the browser's own menu can still install the site.
})();
