/*!
 * Vault Pick — replaces every native <select> with a modern dropdown UI.
 * Loaded from base.html so all admin modules are covered automatically.
 * Skips only: [multiple], size>1, [data-native].
 * Dynamically injected selects (modals, AJAX) are picked up via MutationObserver.
 */
(function () {
  "use strict";

  var OPEN = null;
  var PORTAL = null;

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

  function portalHost() {
    if (PORTAL && document.body.contains(PORTAL)) return PORTAL;
    PORTAL = document.createElement("div");
    PORTAL.id = "v-pick-portal";
    PORTAL.setAttribute("aria-hidden", "true");
    document.body.appendChild(PORTAL);
    return PORTAL;
  }

  function clearMenuInline(menu) {
    menu.classList.remove("is-open");
    menu.hidden = true;
    menu.style.cssText = "";
    if (menu._vPickRoot && menu.parentElement !== menu._vPickRoot) {
      menu._vPickRoot.appendChild(menu);
    }
  }

  function closeAll(except) {
    document.querySelectorAll(".v-pick.open").forEach(function (el) {
      if (except && el === except) return;
      el.classList.remove("open");
      var btn = el.querySelector(".v-pick-btn");
      var menu = el._vPickMenu || el.querySelector(".v-pick-menu");
      if (btn) btn.setAttribute("aria-expanded", "false");
      if (menu) clearMenuInline(menu);
    });
    OPEN = null;
  }

  function placeMenu(btn, menu) {
    var r = btn.getBoundingClientRect();
    var width = Math.max(Math.round(r.width), 140);
    var maxH = Math.min(288, Math.floor(window.innerHeight * 0.55));
    var top = Math.round(r.bottom + 6);
    var left = Math.round(r.left);

    // Keep inside the viewport.
    if (left + width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - width - 8);
    }
    if (left < 8) left = 8;

    // Flip upward when there is not enough room below.
    if (top + Math.min(maxH, 180) > window.innerHeight - 8) {
      top = Math.max(8, Math.round(r.top - 6 - Math.min(maxH, menu.scrollHeight || 180)));
    }

    portalHost().appendChild(menu);
    menu.hidden = false;
    menu.classList.add("is-open");
    menu.style.position = "fixed";
    menu.style.left = left + "px";
    menu.style.top = top + "px";
    menu.style.width = width + "px";
    menu.style.minWidth = width + "px";
    menu.style.maxWidth = width + "px";
    menu.style.right = "auto";
    menu.style.zIndex = "2100";
    menu.style.maxHeight = maxH + "px";
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
    var menu = root._vPickMenu;
    if (menu) {
      menu.querySelectorAll(".v-pick-opt").forEach(function (btn) {
        btn.classList.toggle("on", btn.getAttribute("data-value") === String(sel.value));
      });
    }
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

  function buildMenu(root, sel) {
    var menu = root._vPickMenu;
    if (!menu) return;
    var html = "";
    Array.prototype.forEach.call(sel.children, function (node) {
      if (node.tagName === "OPTGROUP") {
        html += '<div class="v-pick-group">' + esc(node.label || "") + "</div>";
        Array.prototype.forEach.call(node.children, function (opt) {
          if (opt.tagName === "OPTION") html += optionHtml(opt, sel);
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
        var next = btn.getAttribute("data-value");
        if (String(sel.value) !== String(next)) {
          sel.value = next;
          sel.dispatchEvent(new Event("input", { bubbles: true }));
          sel.dispatchEvent(new Event("change", { bubbles: true }));
        }
        syncButton(root, sel);
        closeAll();
      });
    });
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
    if (sel.style.cssText) {
      root.style.cssText = sel.style.cssText;
      sel.style.cssText = "";
    }

    sel.parentNode.insertBefore(root, sel);
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
      var sid = sel.id;
      var lab = null;
      try {
        lab = document.querySelector('label[for="' + (window.CSS && CSS.escape ? CSS.escape(sid) : sid.replace(/"/g, '\\"')) + '"]');
      } catch (e) {
        lab = document.querySelector('label[for="' + sid + '"]');
      }
      if (lab) btn.setAttribute("aria-label", (lab.textContent || "").trim() || "Select");
    } else if (sel.getAttribute("aria-label")) {
      btn.setAttribute("aria-label", sel.getAttribute("aria-label"));
    } else {
      btn.setAttribute("aria-label", "Select");
    }
    if (sel.disabled) btn.disabled = true;
    if (sel.title) btn.title = sel.title;
    if (sel.required) btn.setAttribute("aria-required", "true");

    btn.innerHTML =
      '<span class="v-pick-dot" hidden aria-hidden="true"></span>' +
      '<span class="v-pick-label truncate"></span>' +
      '<i class="bi bi-chevron-down" aria-hidden="true"></i>';

    var menu = document.createElement("div");
    menu.className = "v-pick-menu";
    menu.setAttribute("role", "listbox");
    menu.hidden = true;
    menu._vPickRoot = root;
    root._vPickMenu = menu;
    root._vPickBtn = btn;

    root.appendChild(btn);
    root.appendChild(menu);

    buildMenu(root, sel);
    syncButton(root, sel);

    function openMenu() {
      if (sel.disabled) return;
      buildMenu(root, sel);
      syncButton(root, sel);
      root.classList.add("open");
      btn.setAttribute("aria-expanded", "true");
      placeMenu(btn, menu);
      OPEN = root;
      var on = menu.querySelector(".v-pick-opt.on");
      if (on) {
        try {
          on.focus({ preventScroll: true });
        } catch (e) {
          /* ignore */
        }
      }
    }

    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var willOpen = !root.classList.contains("open");
      closeAll();
      if (willOpen) openMenu();
    });

    btn.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" || ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        if (!root.classList.contains("open")) {
          closeAll();
          openMenu();
        }
      }
    });

    sel.addEventListener("change", function () {
      syncButton(root, sel);
    });

    var mo = new MutationObserver(function () {
      buildMenu(root, sel);
      syncButton(root, sel);
      root.classList.toggle("is-disabled", !!sel.disabled);
      btn.disabled = !!sel.disabled;
    });
    mo.observe(sel, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["disabled"],
    });
    root._vPickMo = mo;
  }

  function enhanceAll(root) {
    var scope = root && root.querySelectorAll ? root : document;
    if (scope.tagName === "SELECT") {
      enhance(scope);
      return;
    }
    Array.prototype.forEach.call(scope.querySelectorAll("select"), enhance);
  }

  function onScrollOrResize() {
    if (!OPEN) return;
    var btn = OPEN._vPickBtn;
    var menu = OPEN._vPickMenu;
    if (btn && menu && !menu.hidden) placeMenu(btn, menu);
  }

  function boot() {
    enhanceAll(document);

    document.addEventListener("click", function (ev) {
      if (ev.target && ev.target.closest && ev.target.closest(".v-pick-menu")) return;
      if (ev.target && ev.target.closest && ev.target.closest(".v-pick-btn")) return;
      closeAll();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") closeAll();
    });
    window.addEventListener("resize", onScrollOrResize, { passive: true });
    window.addEventListener("scroll", onScrollOrResize, true);

    // Bootstrap modals / sheets often inject or reveal selects after first paint.
    document.addEventListener("shown.bs.modal", function (ev) {
      if (ev.target) enhanceAll(ev.target);
    });
    document.addEventListener("hidden.bs.modal", function () {
      closeAll();
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

  window.VaultPick = {
    enhance: enhance,
    enhanceAll: enhanceAll,
    closeAll: closeAll,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
