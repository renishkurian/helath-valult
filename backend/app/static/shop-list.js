(function () {
  var root = document.getElementById("shop-list-root");
  if (!root) return;

  var catalog = {};
  try { catalog = JSON.parse(root.getAttribute("data-catalog") || "{}"); } catch (e) { catalog = {}; }
  var useAi = document.getElementById("shop-use-ai");
  var search = document.getElementById("shop-quick-search");
  var nameInput = document.getElementById("item-name");
  var suggestBox = document.getElementById("shop-suggest");
  var chipHost = document.getElementById("shop-chips-host");
  var catBar = document.getElementById("shop-cat-bar");
  var emptyHint = document.getElementById("shop-chip-empty");
  var itemFilter = document.getElementById("shop-item-filter");
  var activeCat = "all";

  function fold(s) {
    return String(s || "").toLowerCase().replace(/[^a-z0-9\u0d00-\u0d7f]+/g, "");
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
      if (h && h.indexOf(n) >= 0) return true;
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
    if (emptyHint) emptyHint.hidden = shown > 0;
  }

  function renderSuggest() {
    if (!nameInput || !suggestBox) return;
    var q = nameInput.value.trim();
    if (q.length < 2 || !aiOn()) {
      suggestBox.hidden = true;
      suggestBox.innerHTML = "";
      return;
    }
    var ranked = entries().map(function (it) {
      return { it: it, s: score(it, q) };
    }).filter(function (row) { return row.s >= 70; })
      .sort(function (a, b) { return b.s - a.s; })
      .slice(0, 8);
    if (!ranked.length) {
      suggestBox.hidden = true;
      suggestBox.innerHTML = "";
      return;
    }
    suggestBox.innerHTML = ranked.map(function (row) {
      var it = row.it;
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

  var liveUrl = root.getAttribute("data-live");
  var revision = root.getAttribute("data-revision") || "";
  if (liveUrl) {
    setInterval(function () {
      var active = document.activeElement;
      if (active && active.matches && active.matches("input, textarea, select")) return;
      fetch(liveUrl, { headers: { Accept: "application/json" } })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.revision) return;
          if (revision && data.revision !== revision) location.reload();
        })
        .catch(function () {});
    }, 2500);
  }
})();
