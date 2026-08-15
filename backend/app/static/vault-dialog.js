/*!
 * Vault custom dialogs — replaces native alert/confirm with a themed modal.
 * Usage:
 *   data-confirm="Message?" on a <form> or submit <button>
 *   await vaultConfirm("Message?")
 *   await vaultAlert("Message")
 */
(function () {
  "use strict";

  var root = null;
  var titleEl = null;
  var bodyEl = null;
  var iconEl = null;
  var cancelBtn = null;
  var okBtn = null;
  var panel = null;
  var busy = false;
  var resolveFn = null;

  var DANGER_RE = /\b(delete|trash|remove|revoke|block|disconnect|forever|permanent|empty|destroy)\b/i;

  function ensureDom() {
    if (root) return;
    root = document.createElement("div");
    root.className = "vdlg";
    root.id = "vault-dialog";
    root.hidden = true;
    root.setAttribute("role", "presentation");
    root.innerHTML =
      '<div class="vdlg-backdrop" data-vdlg-cancel></div>' +
      '<div class="vdlg-panel" role="alertdialog" aria-modal="true" aria-labelledby="vdlg-title" aria-describedby="vdlg-body" tabindex="-1">' +
      '  <div class="vdlg-icon" aria-hidden="true"><i class="bi bi-exclamation-triangle"></i></div>' +
      '  <div class="vdlg-copy">' +
      '    <h2 class="vdlg-title" id="vdlg-title">Confirm</h2>' +
      '    <p class="vdlg-body" id="vdlg-body"></p>' +
      "  </div>" +
      '  <div class="vdlg-actions">' +
      '    <button type="button" class="btn btn-ghost vdlg-cancel" data-vdlg-cancel>Cancel</button>' +
      '    <button type="button" class="btn vdlg-ok">OK</button>' +
      "  </div>" +
      "</div>";
    document.body.appendChild(root);
    titleEl = root.querySelector(".vdlg-title");
    bodyEl = root.querySelector(".vdlg-body");
    iconEl = root.querySelector(".vdlg-icon i");
    cancelBtn = root.querySelector(".vdlg-cancel");
    okBtn = root.querySelector(".vdlg-ok");
    panel = root.querySelector(".vdlg-panel");

    root.addEventListener("click", function (e) {
      if (e.target.closest("[data-vdlg-cancel]")) finish(false);
    });
    okBtn.addEventListener("click", function () {
      finish(true);
    });
    document.addEventListener("keydown", onKey);
  }

  function onKey(e) {
    if (!root || root.hidden) return;
    if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    } else if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "TEXTAREA" || tag === "A" || tag === "BUTTON") return;
      e.preventDefault();
      finish(true);
    }
  }

  function finish(ok) {
    if (!busy) return;
    busy = false;
    root.classList.remove("is-open");
    window.setTimeout(function () {
      if (!busy) root.hidden = true;
    }, 180);
    document.body.classList.remove("vdlg-open");
    var fn = resolveFn;
    resolveFn = null;
    if (fn) fn(ok);
  }

  function isDanger(message, opts) {
    if (opts && opts.danger != null) return !!opts.danger;
    return DANGER_RE.test(message || "");
  }

  function openDialog(message, opts) {
    ensureDom();
    opts = opts || {};
    var mode = opts.mode || "confirm";
    var danger = isDanger(message, opts);

    titleEl.textContent = opts.title || (mode === "alert" ? "Notice" : danger ? "Please confirm" : "Confirm");
    bodyEl.textContent = message || "";
    iconEl.className = "bi " + (opts.icon || (mode === "alert" ? "bi-info-circle" : danger ? "bi-trash3" : "bi-question-circle"));
    root.classList.toggle("is-danger", danger && mode === "confirm");
    root.classList.toggle("is-alert", mode === "alert");

    cancelBtn.hidden = mode === "alert";
    cancelBtn.textContent = opts.cancelText || "Cancel";
    okBtn.textContent = opts.okText || (mode === "alert" ? "Got it" : danger ? "Confirm" : "OK");
    okBtn.className = "btn vdlg-ok " + (danger && mode === "confirm" ? "btn-danger" : "btn-gold");

    return new Promise(function (resolve) {
      if (busy && resolveFn) resolveFn(false);
      resolveFn = resolve;
      busy = true;
      root.hidden = false;
      document.body.classList.add("vdlg-open");
      requestAnimationFrame(function () {
        root.classList.add("is-open");
        (mode === "alert" ? okBtn : cancelBtn).focus();
      });
    });
  }

  function vaultConfirm(message, opts) {
    opts = opts || {};
    opts.mode = "confirm";
    return openDialog(String(message == null ? "" : message), opts);
  }

  function vaultAlert(message, opts) {
    opts = opts || {};
    opts.mode = "alert";
    return openDialog(String(message == null ? "" : message), opts).then(function () {
      return true;
    });
  }

  function confirmMessage(el) {
    if (!el) return "";
    return el.getAttribute("data-confirm") || "";
  }

  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (form.getAttribute("data-vault-ok") === "1") {
        form.removeAttribute("data-vault-ok");
        return;
      }

      var submitter = e.submitter || null;
      var msg = confirmMessage(form) || confirmMessage(submitter);
      if (!msg) return;

      e.preventDefault();
      e.stopImmediatePropagation();

      vaultConfirm(msg).then(function (ok) {
        if (!ok) return;
        form.setAttribute("data-vault-ok", "1");
        if (typeof form.requestSubmit === "function") {
          try {
            form.requestSubmit(submitter || undefined);
            return;
          } catch (err) {}
        }
        HTMLFormElement.prototype.submit.call(form);
      });
    },
    true
  );

  document.addEventListener(
    "click",
    function (e) {
      var btn = e.target.closest("[data-confirm]");
      if (!btn) return;
      if (btn.tagName === "FORM") return;
      if (btn.type === "submit" || btn.getAttribute("type") === "submit") return;
      if (btn.tagName !== "BUTTON" && btn.tagName !== "A") return;

      var msg = confirmMessage(btn);
      if (!msg) return;

      e.preventDefault();
      e.stopImmediatePropagation();

      vaultConfirm(msg).then(function (ok) {
        if (!ok) return;
        if (btn.tagName === "A" && btn.href) {
          window.location.href = btn.href;
          return;
        }
        btn.setAttribute("data-vault-ok", "1");
        btn.click();
        btn.removeAttribute("data-vault-ok");
      });
    },
    true
  );

  function unescapeJs(str) {
    return String(str || "").replace(/\\([\\'"])/g, "$1");
  }

  function extractConfirm(code) {
    if (!code) return null;
    var m = String(code).match(/^\s*return\s+confirm\s*\(\s*'((?:\\'|[^'])*)'\s*\)\s*;?\s*$/);
    if (m) return unescapeJs(m[1]);
    m = String(code).match(/^\s*return\s+confirm\s*\(\s*"((?:\\"|[^"])*)"\s*\)\s*;?\s*$/);
    if (m) return unescapeJs(m[1]);
    return null;
  }

  function migrateInlineConfirms() {
    document.querySelectorAll("[onsubmit]").forEach(function (el) {
      var msg = extractConfirm(el.getAttribute("onsubmit"));
      if (msg == null) return;
      el.setAttribute("data-confirm", msg);
      el.removeAttribute("onsubmit");
    });
    document.querySelectorAll("[onclick]").forEach(function (el) {
      var msg = extractConfirm(el.getAttribute("onclick"));
      if (msg == null) return;
      el.setAttribute("data-confirm", msg);
      el.removeAttribute("onclick");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", migrateInlineConfirms);
  } else {
    migrateInlineConfirms();
  }

  window.vaultConfirm = vaultConfirm;
  window.vaultAlert = vaultAlert;
  window.alert = function (message) {
    vaultAlert(message);
  };
})();
