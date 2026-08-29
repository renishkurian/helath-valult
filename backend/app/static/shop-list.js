(function () {
  var root = document.getElementById("shop-list-root");
  if (!root) return;

  var catalog = {};
  var catNode = document.getElementById("shop-catalog-data");
  if (catNode) {
    try { catalog = JSON.parse(catNode.textContent || "{}"); } catch (e) { catalog = {}; }
  }
  if (!(catalog.groups && catalog.groups.length)) {
    try { catalog = JSON.parse(root.getAttribute("data-catalog") || "{}"); } catch (e) { catalog = {}; }
  }

  var suggestUrl = (root.getAttribute("data-suggest") || "").trim();
  var useAi = document.getElementById("shop-use-ai");
  var search = document.getElementById("shop-quick-search");
  var nameInput = document.getElementById("item-name");
  var suggestBox = document.getElementById("shop-suggest");
  var chipHost = document.getElementById("shop-chips-host");
  var catBar = document.getElementById("shop-cat-bar");
  var emptyHint = document.getElementById("shop-chip-empty");
  var itemFilter = document.getElementById("shop-item-filter");
  var activeCat = "all";
  var suggestTimer = null;
  var suggestSeq = 0;

  function fold(s) {
    // Match backend: keep Malayalam letters, drop virama (U+0D4D) and punctuation.
    return String(s || "").toLowerCase().replace(/\u0d4d/g, "").replace(/[^a-z0-9\u0d00-\u0d7f]+/g, "");
  }

  function editDistance(a, b) {
    if (a === b) return 0;
    if (!a) return b.length;
    if (!b) return a.length;
    if (Math.abs(a.length - b.length) > 2) return 99;
    if (a.length > 24 || b.length > 24) return 99;
    var prev = [];
    for (var j = 0; j <= b.length; j++) prev[j] = j;
    for (var i = 1; i <= a.length; i++) {
      var cur = [i];
      for (j = 1; j <= b.length; j++) {
        var cost = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1;
        cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
      }
      prev = cur;
    }
    return prev[b.length];
  }

  function entries() {
    var out = [];
    (catalog.groups || []).forEach(function (g) {
      (g.entries || []).forEach(function (it) { out.push(it); });
    });
    return out;
  }

  function haystack(it, ai) {
    var bits = [it.english, it.malayalam];
    if (ai) bits = bits.concat(it.aliases || it.keys || []);
    return bits;
  }

  function matches(it, q, ai) {
    if (!q) return true;
    var n = fold(q);
    if (!n) return true;
    var bits = haystack(it, ai);
    for (var i = 0; i < bits.length; i++) {
      var h = fold(bits[i]);
      if (!h) continue;
      if (h.indexOf(n) >= 0) return true;
      if (ai && n.length >= 4) {
        var d = editDistance(n, h);
        if (d === 1 || (d === 2 && n.length >= 5)) return true;
      }
    }
    return false;
  }

  function score(it, q) {
    var n = fold(q);
    if (!n) return 0;
    var best = 0;
    haystack(it, true).forEach(function (k) {
      var h = fold(k);
      if (!h) return;
      if (h === n) best = Math.max(best, 100);
      else if (h.indexOf(n) === 0) best = Math.max(best, n.length >= 4 ? 92 : 80);
      else if (h.indexOf(n) >= 0) best = Math.max(best, 70);
      else if (n.length >= 4) {
        var d = editDistance(n, h);
        if (d === 1) best = Math.max(best, 86);
        else if (d === 2 && n.length >= 5) best = Math.max(best, 72);
      }
    });
    return best;
  }

  function aiOn() {
    return !useAi || useAi.checked;
  }

  function filterChips() {
    if (!chipHost) return;
    var q = search ? search.value : "";
    var ai = aiOn();
    var shown = 0;
    Array.prototype.forEach.call(chipHost.querySelectorAll("form"), function (form) {
      var cat = form.getAttribute("data-cat") || "";
      var it = {
        english: form.getAttribute("data-en") || "",
        malayalam: form.getAttribute("data-ml") || "",
        keys: (form.getAttribute("data-keys") || "").split(/\s+/),
        aliases: (form.getAttribute("data-keys") || "").split(/\s+/),
      };
      var ok = (activeCat === "all" || cat === activeCat) && matches(it, q, ai);
      form.hidden = !ok;
      if (ok) shown += 1;
    });
    Array.prototype.forEach.call(chipHost.querySelectorAll(".shop-chip-section"), function (sec) {
      var cat = sec.getAttribute("data-section-cat") || "";
      var catOk = activeCat === "all" || cat === activeCat;
      var any = false;
      if (catOk) {
        Array.prototype.forEach.call(sec.querySelectorAll("form"), function (form) {
          if (!form.hidden) any = true;
        });
      }
      sec.hidden = !any;
    });
    if (emptyHint) emptyHint.hidden = shown > 0;
  }

  function localRanked(q) {
    return entries().map(function (it) {
      return { it: it, s: score(it, q) };
    }).filter(function (row) { return row.s >= 70; })
      .sort(function (a, b) { return b.s - a.s; })
      .slice(0, 8)
      .map(function (row) { return row.it; });
  }

  function paintSuggest(rows, emptyMsg) {
    if (!suggestBox) return;
    if (!rows || !rows.length) {
      suggestBox.innerHTML = '<div class="shop-suggest-empty">' + (emptyMsg || "No match — Add will keep this name") + "</div>";
      suggestBox.hidden = false;
      return;
    }
    suggestBox.innerHTML = rows.map(function (it) {
      var ml = it.malayalam ? " (" + it.malayalam + ")" : "";
      return '<button type="button" class="shop-suggest-row" data-en="' +
        encodeURIComponent(it.english) + '" data-emoji="' +
        encodeURIComponent(it.emoji || "") + '" data-cat="' +
        encodeURIComponent(it.category || "") + '">' +
        '<span>' + (it.emoji || "🛒") + " " + it.english + ml + "</span>" +
        '<span class="text-muted">Match</span></button>';
    }).join("");
    suggestBox.hidden = false;
  }

  function renderSuggest() {
    if (!nameInput || !suggestBox) return;
    var q = nameInput.value.trim();
    if (q.length < 2 || !aiOn()) {
      suggestBox.hidden = true;
      suggestBox.innerHTML = "";
      return;
    }
    var seq = ++suggestSeq;
    var local = localRanked(q);
    if (local.length) paintSuggest(local);
    else {
      suggestBox.innerHTML = '<div class="shop-suggest-empty">Looking up…</div>';
      suggestBox.hidden = false;
    }

    if (!suggestUrl) {
      if (!local.length) paintSuggest([], "No match — Add will keep this name");
      return;
    }

    if (suggestTimer) clearTimeout(suggestTimer);
    suggestTimer = setTimeout(function () {
      fetch(suggestUrl + (suggestUrl.indexOf("?") >= 0 ? "&" : "?") + "q=" + encodeURIComponent(q) + "&limit=8", {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (seq !== suggestSeq) return;
          var rows = Array.isArray(data) ? data.filter(function (it) { return it && it.english; }) : [];
          if (rows.length) paintSuggest(rows);
          else if (local.length) paintSuggest(local);
          else paintSuggest([], "No match — Add will keep this name");
        })
        .catch(function () {
          if (seq !== suggestSeq) return;
          if (local.length) paintSuggest(local);
          else paintSuggest([], "No match — Add will keep this name");
        });
    }, 180);
  }

  if (catBar) {
    catBar.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-cat]");
      if (!btn) return;
      activeCat = btn.getAttribute("data-cat") || "all";
      Array.prototype.forEach.call(catBar.querySelectorAll("[data-cat]"), function (el) {
        el.classList.toggle("active", el === btn);
      });
      filterChips();
    });
  }
  if (search) search.addEventListener("input", filterChips);
  if (useAi) useAi.addEventListener("change", function () {
    filterChips();
    renderSuggest();
  });
  if (nameInput) {
    nameInput.addEventListener("input", renderSuggest);
    nameInput.addEventListener("focus", renderSuggest);
  }
  if (suggestBox) {
    suggestBox.addEventListener("mousedown", function (e) { e.preventDefault(); });
    suggestBox.addEventListener("click", function (e) {
      var row = e.target.closest(".shop-suggest-row");
      if (!row || !nameInput) return;
      nameInput.value = decodeURIComponent(row.getAttribute("data-en") || "");
      suggestBox.hidden = true;
      nameInput.focus();
    });
  }
  document.addEventListener("click", function (e) {
    if (!suggestBox || suggestBox.hidden) return;
    if (e.target === nameInput || suggestBox.contains(e.target)) return;
    suggestBox.hidden = true;
  });
  if (itemFilter) {
    itemFilter.addEventListener("input", function () {
      var q = fold(itemFilter.value);
      Array.prototype.forEach.call(document.querySelectorAll("#shop-item-rows .shop-item"), function (row) {
        var name = fold(row.getAttribute("data-name") || "");
        row.hidden = q && name.indexOf(q) < 0;
      });
    });
  }
  filterChips();

  // Item edit bottom drawer
  var editSheet = document.getElementById("shop-edit-sheet");
  var editScrim = document.getElementById("shop-edit-scrim");
  var editForm = document.getElementById("shop-edit-form");
  var editName = document.getElementById("edit-item-name");
  var editQty = document.getElementById("edit-item-qty");
  var editUnit = document.getElementById("edit-item-unit");
  var editPrice = document.getElementById("edit-item-price");
  var editNotes = document.getElementById("edit-item-notes");

  function closeEditDrawer() {
    if (!editSheet) return;
    editSheet.classList.remove("open");
    editSheet.setAttribute("aria-hidden", "true");
    if (editScrim) editScrim.classList.remove("open");
  }

  function openEditDrawer(btn) {
    if (!editSheet || !editForm) return;
    var action = btn.getAttribute("data-action") || "";
    var name = btn.getAttribute("data-name") || "";
    var qty = btn.getAttribute("data-quantity") || "1";
    var unit = btn.getAttribute("data-unit") || "";
    var price = btn.getAttribute("data-price") || "";
    var notes = btn.getAttribute("data-notes") || "";

    editForm.action = action;
    if (editName) editName.value = name;
    if (editQty) editQty.value = qty;
    if (editUnit) editUnit.value = unit;
    if (editPrice) editPrice.value = price;
    if (editNotes) editNotes.value = notes;

    editSheet.classList.add("open");
    editSheet.setAttribute("aria-hidden", "false");
    if (editScrim) editScrim.classList.add("open");
    if (editName) {
      setTimeout(function () {
        editName.focus();
        editName.select();
      }, 150);
    }
  }

  root.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-shop-edit");
    if (btn) {
      e.preventDefault();
      openEditDrawer(btn);
    }
  });

  if (editScrim) editScrim.addEventListener("click", closeEditDrawer);
  var editClose = document.getElementById("shop-edit-close");
  if (editClose) editClose.addEventListener("click", closeEditDrawer);
  var editCancel = document.getElementById("shop-edit-cancel");
  if (editCancel) editCancel.addEventListener("click", closeEditDrawer);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && editSheet && editSheet.classList.contains("open")) {
      closeEditDrawer();
    }
  });

  var liveUrl = root.getAttribute("data-live");
  var revision = root.getAttribute("data-revision") || "";
  var toggleBusy = 0;

  function applyChecked(block, checked) {
    block.classList.toggle("checked", !!checked);
    var btn = block.querySelector(".js-shop-toggle button");
    var icon = btn && btn.querySelector("i");
    if (icon) icon.className = "bi " + (checked ? "bi-check-circle-fill" : "bi-circle");
    if (btn) btn.setAttribute("aria-label", checked ? "Uncheck" : "Check");
  }

  function paintProgress(checkedCount, itemCount) {
    var completed = root.getAttribute("data-completed") === "1";
    var pct = itemCount ? Math.floor((checkedCount / itemCount) * 100) : 0;
    var state = document.getElementById("shop-progress-state");
    var counts = document.getElementById("shop-progress-counts");
    var bar = document.getElementById("shop-progress-fill");
    var stat = document.getElementById("shop-stat-checked");
    if (state) state.textContent = completed ? "Done" : (checkedCount ? "Shopping" : "Planning");
    if (counts) counts.textContent = pct + "% · " + checkedCount + " of " + itemCount;
    if (bar) bar.style.width = pct + "%";
    if (stat) stat.textContent = String(checkedCount);
  }

  function paintProgressFromDom() {
    var rows = document.querySelectorAll("#shop-item-rows .shop-item");
    if (!rows.length) return;
    var checked = 0;
    Array.prototype.forEach.call(rows, function (row) {
      if (row.classList.contains("checked")) checked += 1;
    });
    paintProgress(checked, rows.length);
  }

  function setRevision(value) {
    if (!value) return;
    revision = value;
    root.setAttribute("data-revision", value);
  }

  root.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || !form.classList || !form.classList.contains("js-shop-toggle")) return;
    e.preventDefault();
    if (form.getAttribute("data-busy") === "1") return;
    var block = form.closest(".shop-item");
    if (!block) return;
    var was = block.classList.contains("checked");
    var next = !was;
    var action = form.getAttribute("action") || form.action;
    form.setAttribute("data-busy", "1");
    toggleBusy += 1;
    applyChecked(block, next);
    paintProgressFromDom();
    fetch(action, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "fetch" },
    })
      .then(function (r) {
        if (r.status === 401) {
          location.reload();
          return null;
        }
        if (!r.ok) throw new Error("toggle failed");
        var ct = r.headers.get("content-type") || "";
        if (ct.indexOf("application/json") < 0) {
          location.reload();
          return null;
        }
        return r.json();
      })
      .then(function (data) {
        if (!data) return;
        if (typeof data.checked === "boolean") applyChecked(block, data.checked);
        setRevision(data.revision);
        if (typeof data.checked_count === "number" && typeof data.item_count === "number") {
          paintProgress(data.checked_count, data.item_count);
        } else {
          paintProgressFromDom();
        }
      })
      .catch(function () {
        applyChecked(block, was);
        paintProgressFromDom();
      })
      .then(function () {
        form.removeAttribute("data-busy");
        toggleBusy = Math.max(0, toggleBusy - 1);
      });
  });

  if (liveUrl) {
    setInterval(function () {
      if (toggleBusy) return;
      var active = document.activeElement;
      if (active && active.matches && active.matches("input, textarea, select")) return;
      if (editSheet && editSheet.classList.contains("open")) return;
      if (root.querySelector(".shop-edit-form:not([hidden])")) return;
      fetch(liveUrl, { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.revision) return;
          if (revision && data.revision !== revision) location.reload();
        })
        .catch(function () {});
    }, 2500);
  }

  // Prevent double-submit on add (main form, quick-add chips, public composer).
  Array.prototype.forEach.call(document.querySelectorAll(
    "#shop-add-form, .shop-composer form, #shop-chips-host form"
  ), function (form) {
    form.addEventListener("submit", function (e) {
      if (form.getAttribute("data-busy") === "1") {
        e.preventDefault();
        return;
      }
      form.setAttribute("data-busy", "1");
      var btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        if (!btn.getAttribute("data-label")) btn.setAttribute("data-label", btn.textContent || "Add");
        btn.textContent = "Adding…";
      }
    });
  });

  // Swipe right → delete, swipe left → mark purchased (toggle).
  (function setupShopSwipe() {
    var THRESH = 72;
    var MAX = 96;
    var open = null;

    function frontOf(el) {
      return el && el.querySelector(".shop-swipe-front");
    }

    function reset(el) {
      if (!el) return;
      el.classList.remove("dragging", "swiped-left", "swiped-right");
      var front = frontOf(el);
      if (front) front.style.transform = "";
    }

    function closeOpen(except) {
      if (open && open !== except) {
        reset(open);
        open = null;
      }
    }

    function triggerToggle(el) {
      var form = el.querySelector(".js-shop-toggle");
      if (!form) return;
      if (typeof form.requestSubmit === "function") form.requestSubmit();
      else form.submit();
    }

    function triggerDelete(el) {
      var form = el.querySelector(".js-shop-delete");
      if (!form) return;
      var msg = form.getAttribute("data-confirm") || "Remove this item?";
      function go() {
        form.removeAttribute("data-confirm");
        if (typeof form.requestSubmit === "function") form.requestSubmit();
        else form.submit();
      }
      if (typeof window.vaultConfirm === "function") {
        window.vaultConfirm(msg).then(function (ok) {
          if (!ok) { reset(el); open = null; return; }
          go();
        });
        return;
      }
      if (window.confirm(msg)) go();
      else { reset(el); open = null; }
    }

    function onStart(el, x, y) {
      if (editSheet && editSheet.classList.contains("open")) return;
      if (el.classList.contains("editing") || el.querySelector(".shop-edit-form:not([hidden])")) return;
      closeOpen(el);
      el._sx = x;
      el._sy = y;
      el._dx = 0;
      el._axis = null;
      el.classList.add("dragging");
    }

    function onMove(el, x, y, ev) {
      if (el._sx == null) return;
      var dx = x - el._sx;
      var dy = y - el._sy;
      if (!el._axis) {
        if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
        el._axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
        if (el._axis === "y") {
          el.classList.remove("dragging");
          el._sx = null;
          return;
        }
      }
      if (el._axis !== "x") return;
      if (ev && ev.cancelable) ev.preventDefault();
      var hasDelete = !!el.querySelector(".js-shop-delete");
      var hasToggle = !!el.querySelector(".js-shop-toggle");
      if (dx > 0 && !hasDelete) dx = 0;
      if (dx < 0 && !hasToggle) dx = 0;
      dx = Math.max(-MAX, Math.min(MAX, dx));
      el._dx = dx;
      var front = frontOf(el);
      if (front) front.style.transform = "translateX(" + dx + "px)";
    }

    function onEnd(el) {
      if (el._sx == null) return;
      var dx = el._dx || 0;
      el._sx = null;
      el.classList.remove("dragging");
      var front = frontOf(el);
      if (front) front.style.transform = "";
      if (dx >= THRESH && el.querySelector(".js-shop-delete")) {
        el.classList.add("swiped-right");
        open = el;
        setTimeout(function () { triggerDelete(el); }, 160);
        return;
      }
      if (dx <= -THRESH && el.querySelector(".js-shop-toggle")) {
        el.classList.add("swiped-left");
        open = el;
        setTimeout(function () {
          triggerToggle(el);
          reset(el);
          open = null;
        }, 160);
        return;
      }
      reset(el);
      if (open === el) open = null;
    }

    Array.prototype.forEach.call(document.querySelectorAll(".shop-swipe"), function (el) {
      var front = frontOf(el);
      if (!front) return;
      front.addEventListener("touchstart", function (e) {
        if (!e.touches || !e.touches.length) return;
        onStart(el, e.touches[0].clientX, e.touches[0].clientY);
      }, { passive: true });
      front.addEventListener("touchmove", function (e) {
        if (!e.touches || !e.touches.length) return;
        onMove(el, e.touches[0].clientX, e.touches[0].clientY, e);
      }, { passive: false });
      front.addEventListener("touchend", function () { onEnd(el); });
      front.addEventListener("touchcancel", function () {
        el._sx = null;
        el.classList.remove("dragging");
        var f = frontOf(el);
        if (f) f.style.transform = "";
        reset(el);
      });
    });

    document.addEventListener("click", function (e) {
      if (open && !e.target.closest(".shop-swipe")) {
        reset(open);
        open = null;
      }
    });
  })();
})();
