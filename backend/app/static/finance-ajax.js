/* Money Manager — session AJAX + light IndexedDB cache (online-first). */
(function () {
  "use strict";

  var TYPE_ICO = {
    income: "bi-arrow-down-left",
    expense: "bi-arrow-up-right",
    transfer: "bi-arrow-left-right",
  };
  var DB_NAME = "mm-cache-v1";
  var DB_STORE = "months";

  function inr(n) {
    n = Number(n) || 0;
    var neg = n < 0;
    n = Math.abs(n);
    var parts = n.toFixed(2).split(".");
    var whole = parts[0];
    var out;
    if (whole.length <= 3) out = whole;
    else {
      var last3 = whole.slice(-3);
      var rest = whole.slice(0, -3);
      var chunks = [];
      while (rest.length > 2) {
        chunks.unshift(rest.slice(-2));
        rest = rest.slice(0, -2);
      }
      if (rest) chunks.unshift(rest);
      out = chunks.join(",") + "," + last3;
    }
    return (neg ? "-₹" : "₹") + out + "." + parts[1];
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toast(msg, isErr) {
    var el = document.getElementById("mm-ajax-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "mm-ajax-toast";
      el.setAttribute("role", "status");
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.className = "mm-ajax-toast" + (isErr ? " err" : " ok");
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.hidden = true;
    }, 2800);
  }

  function openDb() {
    return new Promise(function (resolve) {
      if (!window.indexedDB) return resolve(null);
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(DB_STORE)) db.createObjectStore(DB_STORE);
      };
      req.onsuccess = function () {
        resolve(req.result);
      };
      req.onerror = function () {
        resolve(null);
      };
    });
  }

  function idbGet(key) {
    return openDb().then(function (db) {
      if (!db) return null;
      return new Promise(function (resolve) {
        try {
          var tx = db.transaction(DB_STORE, "readonly");
          var req = tx.objectStore(DB_STORE).get(key);
          req.onsuccess = function () {
            resolve(req.result || null);
          };
          req.onerror = function () {
            resolve(null);
          };
        } catch (e) {
          resolve(null);
        }
      });
    });
  }

  function idbSet(key, value) {
    return openDb().then(function (db) {
      if (!db) return;
      return new Promise(function (resolve) {
        try {
          var tx = db.transaction(DB_STORE, "readwrite");
          tx.objectStore(DB_STORE).put(value, key);
          tx.oncomplete = function () {
            resolve();
          };
          tx.onerror = function () {
            resolve();
          };
        } catch (e) {
          resolve();
        }
      });
    });
  }

  function fetchJson(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      opts.headers || {}
    );
    opts.credentials = "same-origin";
    return fetch(url, opts).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var detail = data && data.detail;
          if (Array.isArray(detail)) {
            detail = detail
              .map(function (d) {
                return d.msg || JSON.stringify(d);
              })
              .join("; ");
          }
          var err = new Error(detail || res.statusText || "Request failed");
          err.status = res.status;
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  function wireForm() {
    var form = document.getElementById("entry-form");
    if (!form || form.dataset.ajaxBound) return;
    form.dataset.ajaxBound = "1";
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var btn = form.querySelector('[type="submit"]');
      if (btn) btn.disabled = true;
      var fd = new FormData(form);
      var editing = !!form.dataset.editId;
      var url = editing
        ? "/admin/finance/api/transactions/" + encodeURIComponent(form.dataset.editId)
        : "/admin/finance/api/transactions";
      fetchJson(url, { method: "POST", body: fd })
        .then(function (data) {
          toast(editing ? "Saved" : "Added");
          idbSet("dash-invalidate", Date.now());
          window.location.href = (data && data.redirect) || "/admin/finance";
        })
        .catch(function (err) {
          toast(err.message || "Could not save", true);
          if (btn) btn.disabled = false;
        });
    });
  }

  function recentHtml(items) {
    if (!items || !items.length) {
      return (
        '<div class="card"><div class="empty-state">' +
        '<div class="empty-ico"><i class="bi bi-wallet2"></i></div>' +
        '<div class="empty-title">Nothing this month yet</div>' +
        "<p>Log income or an expense and the dashboard fills in.</p>" +
        '<a class="btn btn-primary" href="/admin/finance/add"><i class="bi bi-plus-lg"></i> Add the first entry</a>' +
        "</div></div>"
      );
    }
    return (
      '<div class="mm-card-list">' +
      items
        .map(function (item) {
          var ico = TYPE_ICO[item.txn_type] || "bi-receipt";
          var title = item.payee || item.category_name || item.txn_type;
          var sub = item.category_name || item.txn_type;
          if (item.description && item.payee) sub += " · " + item.description;
          var sign = item.txn_type === "income" ? "+" : item.txn_type === "expense" ? "−" : "";
          var when = item.txn_date || "";
          if (item.txn_time) when += " · " + String(item.txn_time).slice(0, 5);
          return (
            '<a class="mm-card" href="/admin/finance/transactions/' +
            esc(item.id) +
            '/edit">' +
            '<span class="mm-card-ico ' +
            esc(item.txn_type) +
            '"><i class="bi ' +
            ico +
            '"></i></span>' +
            '<span class="mm-card-body">' +
            '<span class="mm-card-title truncate">' +
            esc(title) +
            "</span>" +
            '<span class="mm-card-sub truncate">' +
            esc(sub) +
            "</span>" +
            '<span class="mm-card-when">' +
            esc(when) +
            "</span></span>" +
            '<span class="mm-card-amt mm-' +
            esc(item.txn_type) +
            '">' +
            sign +
            inr(item.amount) +
            "</span></a>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function paintDashboard(dash) {
    var root = document.getElementById("mm-home");
    if (!root || !dash) return;
    var s = dash.summary || {};
    root.dataset.month = dash.year_month;
    var monthEl = root.querySelector("[data-mm-month]");
    if (monthEl) monthEl.textContent = dash.label;
    var prev = root.querySelector("[data-mm-prev]");
    var next = root.querySelector("[data-mm-next]");
    if (prev) {
      prev.dataset.month = dash.prev;
      prev.href = "/admin/finance?month=" + encodeURIComponent(dash.prev);
    }
    if (next) {
      next.dataset.month = dash.next;
      next.href = "/admin/finance?month=" + encodeURIComponent(dash.next);
    }
    ["net", "total", "opening", "income", "expense"].forEach(function (k) {
      var el = root.querySelector("[data-mm-" + k + "]");
      if (el) el.textContent = inr(s[k]);
    });
    var netLine = root.querySelector("[data-mm-netline]");
    if (netLine) {
      netLine.classList.toggle("mm-income", (s.total || 0) >= 0);
      netLine.classList.toggle("mm-expense", (s.total || 0) < 0);
    }
    var top = dash.top_category;
    var topName = root.querySelector("[data-mm-top-name]");
    var topMeta = root.querySelector("[data-mm-top-meta]");
    if (topName && topMeta) {
      if (top) {
        topName.textContent = top.name || "—";
        topName.title = top.name || "";
        topName.classList.remove("text-muted");
        topMeta.textContent = inr(top.amount) + " · " + Math.round(top.pct || 0) + "% of spend";
      } else {
        topName.textContent = "No spend yet";
        topName.removeAttribute("title");
        topName.classList.add("text-muted");
        topMeta.textContent = "";
      }
    }
    var hi = dash.highest;
    var hiName = root.querySelector("[data-mm-hi-name]");
    var hiMeta = root.querySelector("[data-mm-hi-meta]");
    if (hiName && hiMeta) {
      if (hi) {
        var label = hi.payee || hi.category_name || "Expense";
        hiName.textContent = label;
        hiName.title = label;
        hiName.classList.remove("text-muted");
        hiMeta.textContent = inr(hi.amount) + (hi.category_name ? " · " + hi.category_name : "");
      } else {
        hiName.textContent = "Nothing posted";
        hiName.removeAttribute("title");
        hiName.classList.add("text-muted");
        hiMeta.textContent = "";
      }
    }
    var insight = root.querySelector("[data-mm-insight]");
    if (insight) {
      if (dash.insight) {
        insight.hidden = false;
        var p = insight.querySelector("[data-mm-insight-text]");
        if (p) p.textContent = dash.insight;
      } else {
        insight.hidden = true;
      }
    }
    var seeAll = root.querySelector("[data-mm-see-all]");
    if (seeAll) {
      seeAll.href = "/admin/finance/transactions?month=" + encodeURIComponent(dash.year_month);
    }
    var recent = root.querySelector("[data-mm-recent]");
    if (recent) recent.innerHTML = recentHtml(dash.recent);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(
        { mmMonth: dash.year_month },
        "",
        "/admin/finance?month=" + encodeURIComponent(dash.year_month)
      );
    }
  }

  function loadDashboard(month, preferCache) {
    var key = "dash:" + month;
    var network = fetchJson("/admin/finance/api/dashboard?month=" + encodeURIComponent(month)).then(
      function (dash) {
        paintDashboard(dash);
        return idbSet(key, { savedAt: Date.now(), dash: dash }).then(function () {
          return dash;
        });
      }
    );
    if (!preferCache) {
      return network.catch(function (err) {
        toast(err.message || "Could not load", true);
      });
    }
    return idbGet(key).then(function (cached) {
      if (cached && cached.dash) paintDashboard(cached.dash);
      return network.catch(function (err) {
        if (!(cached && cached.dash)) toast(err.message || "Could not load", true);
      });
    });
  }

  function wireHome() {
    var root = document.getElementById("mm-home");
    if (!root) return;
    root.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-mm-prev], [data-mm-next]");
      if (!btn) return;
      ev.preventDefault();
      var month = btn.dataset.month;
      if (!month) return;
      loadDashboard(month, true);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireForm();
    wireHome();
  });
})();
