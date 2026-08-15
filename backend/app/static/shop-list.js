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

  root.addEventListener("click", function (e) {
    var btn = e.target.closest(".js-shop-edit");
    if (!btn) return;
    var form = document.getElementById(btn.getAttribute("aria-controls") || "");
    if (!form) return;
    var open = form.hidden;
    form.hidden = !open;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      var first = form.querySelector("input");
      if (first) first.focus();
    }
  });

  var liveUrl = root.getAttribute("data-live");
  var revision = root.getAttribute("data-revision") || "";
  if (liveUrl) {
    setInterval(function () {
      var active = document.activeElement;
      if (active && active.matches && active.matches("input, textarea, select")) return;
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
})();
