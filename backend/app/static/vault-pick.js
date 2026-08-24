/*!
 * Vault Pick — upgrades native <select> controls to a modern dark dropdown.
 * Skips: [multiple], [size], [data-native], already-enhanced, or inside [data-v-pick].
 * Dynamically added selects are picked up via MutationObserver.
 */
(function () {
  "use strict";

  var OPEN = null;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function shouldEnhance(sel) {
    if (!sel || sel.tagName !== "SELECT") return false;
    if (sel.dataset.vPickBound === "1") return false;
    if (sel.multiple) return false;
    if (sel.getAttribute("size") && Number(sel.getAttribute("size")) > 1) return false;
    if (sel.hasAttribute("data-native")) return false;
    if (sel.closest("[data-v-pick]")) return false;
    if (sel.classList.contains("v-pick-native")) return false;
    return true;
  }

  function closeAll(except) {
    document.querySelectorAll(".v-pick.open").forEach(function (el) {
      if (except && el === except) return;
      el.classList.remove("open");
      var btn = el.querySelector(".v-pick-btn");
      var menu = el.querySelector(".v-pick-menu");
      if (btn) btn.setAttribute("aria-expanded", "false");
      if (menu) {
        menu.hidden = true;
        menu.style.position = "";
        menu.style.left = "";
        menu.style.top = "";
        menu.style.width = "";
        menu.style.right = "";
      }
    });
    OPEN = null;
  }

  function selectedOption(sel) {
    var i = sel.selectedIndex;
    if (i < 0) return null;
    return sel.options[i] || null;
  }

  function optionLabel(opt) {
    if (!opt) return "Select…";
    return (opt.textContent || opt.label || opt.value || "").trim() || "Select…";
  }

  function syncButton(root, sel) {
    var label = root.querySelector(".v-pick-label");
    var dot = root.querySelector(".v-pick-btn > .v-pick-dot");
    var opt = selectedOption(sel);
    if (label) label.textContent = optionLabel(opt);
    if (dot) {
      var color = opt && (opt.getAttribute("data-color") || opt.dataset.color);
      if (color) {
        dot.style.background = color;
        dot.hidden = false;
        dot.classList.remove("is-all");
      } else {
        dot.hidden = true;
      }
    }
    root.querySelectorAll(".v-pick-opt").forEach(function (btn) {
      btn.classList.toggle("on", btn.getAttribute("data-value") === String(sel.value));
    });
  }

  function buildMenu(root, sel) {
    var menu = root.querySelector(".v-pick-menu");
    if (!menu) return;
    var html = "";
    var kids = Array.prototype.slice.call(sel.children);
    kids.forEach(function (node) {
      if (node.tagName === "OPTGROUP") {
        html += '<div class="v-pick-group">' + esc(node.label || "") + "</div>";
        Array.prototype.slice.call(node.children).forEach(function (opt) {
          if (opt.tagName !== "OPTION") return;
          html += optionHtml(opt, sel);
        });
      } else if (node.tagName === "OPTION") {
        html += optionHtml(node, sel);
      }
    });
    menu.innerHTML = html || '<div class="v-pick-empty">No options</div>';
    menu.querySelectorAll(".v-pick-opt").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (btn.disabled) return;
        sel.value = btn.getAttribute("data-value");
        sel.dispatchEvent(new Event("input", { bubbles: true }));
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        syncButton(root, sel);
        closeAll();
      });
    });
  }

  function optionHtml(opt, sel) {
    var val = opt.value;
    var color = opt.getAttribute("data-color") || "";
    var disabled = opt.disabled ? " disabled" : "";
    var on = String(sel.value) === String(val) ? " on" : "";
    var dot = color
      ? '<span class="v-pick-dot" style="background:' + esc(color) + '" aria-hidden="true"></span>'
      : "";
    return (
      '<button type="button" class="v-pick-opt' +
      on +
      '"' +
      disabled +
      ' role="option" data-value="' +
      esc(val) +
      '" data-color="' +
      esc(color) +
      '">' +
      dot +
      '<span class="truncate">' +
      esc(optionLabel(opt)) +
      "</span></button>"
    );
  }

  function enhance(sel) {
    if (!shouldEnhance(sel)) return;
    sel.dataset.vPickBound = "1";

    var root = document.createElement("div");
    root.className = "v-pick";
    root.setAttribute("data-v-pick", "auto");
    if (sel.classList.contains("form-select-sm")) root.classList.add("v-pick-sm");
    if (sel.classList.contains("grow")) root.classList.add("grow");
    if (sel.disabled) root.classList.add("is-disabled");
    // Layout styles lived on the native select — move them to the visible wrapper.
    if (sel.style.cssText) {
      root.style.cssText = sel.style.cssText;
      sel.style.cssText = "";
    }

    var wrapParent = sel.parentNode;
    wrapParent.insertBefore(root, sel);
    root.appendChild(sel);
    sel.classList.add("v-pick-native");
    sel.setAttribute("tabindex", "-1");
    sel.setAttribute("aria-hidden", "true");

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "v-pick-btn";
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    if (sel.id) {
      var lab = document.querySelector('label[for="' + sel.id.replace(/"/g, '\\"') + '"]');
      if (lab) btn.setAttribute("aria-label", (lab.textContent || "").trim() || "Select");
    } else if (sel.getAttribute("aria-label")) {
      btn.setAttribute("aria-label", sel.getAttribute("aria-label"));
    } else {
      btn.setAttribute("aria-label", "Select");
    }
    if (sel.disabled) btn.disabled = true;
    if (sel.title) btn.title = sel.title;

    btn.innerHTML =
      '<span class="v-pick-dot" hidden aria-hidden="true"></span>' +
      '<span class="v-pick-label truncate"></span>' +
      '<i class="bi bi-chevron-down" aria-hidden="true"></i>';

    var menu = document.createElement("div");
    menu.className = "v-pick-menu";
    menu.setAttribute("role", "listbox");
    menu.hidden = true;

    root.appendChild(btn);
    root.appendChild(menu);

    buildMenu(root, sel);
    syncButton(root, sel);

    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (sel.disabled) return;
      var open = !root.classList.contains("open");
      closeAll();
      if (open) {
        buildMenu(root, sel);
        syncButton(root, sel);
        root.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
        menu.hidden = false;
        // Fixed so menus escape modal / overflow containers.
        var r = btn.getBoundingClientRect();
        var width = Math.max(r.width, 160);
        var left = Math.min(r.left, window.innerWidth - width - 8);
        var top = r.bottom + 6;
        if (top + Math.min(288, window.innerHeight * 0.55) > window.innerHeight - 8) {
          top = Math.max(8, r.top - 6 - Math.min(288, menu.scrollHeight || 180));
        }
        menu.style.position = "fixed";
        menu.style.left = Math.max(8, left) + "px";
        menu.style.top = top + "px";
        menu.style.width = width + "px";
        menu.style.right = "auto";
        OPEN = root;
      }
    });

    sel.addEventListener("change", function () {
      syncButton(root, sel);
    });

    // Rebuild if options are rewritten (common in finance / expense forms).
    var mo = new MutationObserver(function () {
      buildMenu(root, sel);
      syncButton(root, sel);
      root.classList.toggle("is-disabled", !!sel.disabled);
      btn.disabled = !!sel.disabled;
    });
    mo.observe(sel, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "value"] });
    root._vPickMo = mo;
  }

  function enhanceAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var list = scope.querySelectorAll ? scope.querySelectorAll("select") : [];
    if (scope.tagName === "SELECT") {
      enhance(scope);
      return;
    }
    Array.prototype.forEach.call(list, enhance);
  }

  function boot() {
    enhanceAll(document);
    document.addEventListener("click", function () {
      closeAll();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") closeAll();
    });
    if (window.MutationObserver) {
      var docMo = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          Array.prototype.forEach.call(m.addedNodes || [], function (node) {
            if (!node || node.nodeType !== 1) return;
            if (node.tagName === "SELECT") enhance(node);
            else if (node.querySelectorAll) enhanceAll(node);
          });
        });
      });
      docMo.observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  window.VaultPick = { enhance: enhance, enhanceAll: enhanceAll, closeAll: closeAll };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
