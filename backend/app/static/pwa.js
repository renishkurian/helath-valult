(function () {
  "use strict";

  var INSTALL_KEY = "vault_pwa_install_dismissed";
  var IOS_HINT_KEY = "vault_pwa_ios_hint_dismissed";

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
    });
  }

  if (window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone) {
    document.documentElement.classList.add("pwa-standalone");
  }

  var installEl = document.getElementById("pwa-install");
  var iosEl = document.getElementById("pwa-ios-hint");
  var deferredPrompt = null;

  function hide(el) {
    if (!el) return;
    el.hidden = true;
    el.setAttribute("hidden", "");
  }

  function show(el) {
    if (!el) return;
    el.hidden = false;
    el.removeAttribute("hidden");
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;
    if (localStorage.getItem(INSTALL_KEY) === "1") return;
    show(installEl);
  });

  if (installEl) {
    var btn = installEl.querySelector("[data-pwa-install]");
    var close = installEl.querySelector("[data-pwa-dismiss]");
    if (btn) {
      btn.addEventListener("click", function () {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.finally(function () {
          deferredPrompt = null;
          hide(installEl);
        });
      });
    }
    if (close) {
      close.addEventListener("click", function () {
        localStorage.setItem(INSTALL_KEY, "1");
        hide(installEl);
      });
    }
  }

  // iOS Safari has no beforeinstallprompt — show a one-time Add to Home Screen hint.
  if (iosEl) {
    var isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
    var isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    if (isIos && !isStandalone && localStorage.getItem(IOS_HINT_KEY) !== "1") {
      show(iosEl);
    }
    var iosClose = iosEl.querySelector("[data-pwa-dismiss]");
    if (iosClose) {
      iosClose.addEventListener("click", function () {
        localStorage.setItem(IOS_HINT_KEY, "1");
        hide(iosEl);
      });
    }
  }
})();
