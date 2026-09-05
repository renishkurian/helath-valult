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
      return res.text().then(function (text) {
        var data = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch (e) {
            if (!res.ok) {
              var plain = new Error(res.statusText || "Request failed");
              plain.status = res.status;
              throw plain;
            }
            throw e;
          }
        }
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
          window.location.href = (data && data.redirect) || "/admin/finance/transactions";
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

  /* —— Transactions list —— */
  function methodLabel(m) {
    if (!m) return "";
    return String(m).replace(/_/g, " ");
  }

  function txnCardHtml(item, opts) {
    opts = opts || {};
    var canBulk = !!opts.canBulk;
    var month = opts.month || "";
    var view = opts.view || "daily";
    var ico = TYPE_ICO[item.txn_type] || "bi-receipt";
    var title = item.payee || item.category_name || "—";
    var sub = item.category_name || item.txn_type;
    var desc = item.description || "";
    var when = "";
    if (item.account_name) when += '<span class="mm-card-acct">' + esc(item.account_name) + "</span>";
    if (item.to_account_name) when += " → " + esc(item.to_account_name);
    if (item.payment_method) when += (when ? " · " : "") + esc(methodLabel(item.payment_method));
    if (opts.showDate && item.txn_date) when += (when ? " · " : "") + esc(item.txn_date);
    if (opts.showTime && item.txn_time) when += (when ? " · " : "") + esc(String(item.txn_time).slice(0, 5));
    if (item.family_member_name) when += (when ? " · " : "") + esc(item.family_member_name);
    var sign = item.txn_type === "income" ? "+" : item.txn_type === "expense" ? "−" : "";
    var check = canBulk
      ? '<input type="checkbox" class="form-check-input mm-txn-check m-0" name="txn_id" value="' +
        esc(item.id) +
        '" form="mm-bulk-delete" aria-label="Select transaction">'
      : "";
    var photo =
      item.has_image
        ? '<li><a class="dropdown-item js-photo" href="/admin/finance/transactions/' +
          esc(item.id) +
          '/image"><i class="bi bi-image"></i> Receipt</a></li>'
        : "";
    return (
      '<div class="mm-card" data-txn-id="' +
      esc(item.id) +
      '">' +
      check +
      '<span class="mm-card-ico ' +
      esc(item.txn_type) +
      '"><i class="bi ' +
      ico +
      '"></i></span>' +
      '<div class="mm-card-body">' +
      '<div class="mm-card-title truncate">' +
      esc(title) +
      "</div>" +
      '<div class="mm-card-sub truncate">' +
      esc(sub) +
      "</div>" +
      (desc ? '<div class="mm-card-desc truncate">' + esc(desc) + "</div>" : "") +
      '<div class="mm-card-when">' +
      when +
      "</div></div>" +
      '<div class="mm-card-amt mm-' +
      esc(item.txn_type) +
      '">' +
      sign +
      inr(item.amount) +
      "</div>" +
      '<div class="dropdown">' +
      '<button class="btn btn-ghost btn-icon btn-sm" type="button" data-bs-toggle="dropdown" aria-label="More actions">' +
      '<i class="bi bi-three-dots-vertical"></i></button>' +
      '<ul class="dropdown-menu dropdown-menu-end">' +
      photo +
      '<li><a class="dropdown-item" href="/admin/finance/transactions/' +
      esc(item.id) +
      '/edit"><i class="bi bi-pencil"></i> Edit</a></li>' +
      '<li><button class="dropdown-item text-danger" type="button" data-mm-delete="' +
      esc(item.id) +
      '"><i class="bi bi-trash3"></i> Move to trash</button></li>' +
      "</ul></div></div>"
    );
  }

  function emptyLedgerHtml(filtered) {
    if (filtered) {
      return (
        '<div class="card"><div class="empty-state">' +
        '<div class="empty-ico"><i class="bi bi-receipt"></i></div>' +
        '<div class="empty-title">No transactions match these filters</div>' +
        "<p>Try a different month, account, family member, or clear the search.</p>" +
        "</div></div>"
      );
    }
    return (
      '<div class="card"><div class="empty-state">' +
      '<div class="empty-ico"><i class="bi bi-receipt"></i></div>' +
      '<div class="empty-title">No transactions yet</div>' +
      "<p>Log income, an expense, or a transfer and it will appear here.</p>" +
      '<a class="btn btn-primary" href="/admin/finance/add"><i class="bi bi-plus-lg"></i> Add the first entry</a>' +
      "</div></div>"
    );
  }

  function listHtml(ledger, view) {
    var canBulk = view === "daily" || view === "monthly" || view === "total" || view === "note";
    var opts = { canBulk: canBulk, month: ledger.year_month, view: view };
    var filtered = !!ledger.filtered;

    if (view === "calendar") {
      var days = ["S", "M", "T", "W", "T", "F", "S"];
      var html =
        '<div class="card mb-4"><div class="card-body"><div class="mm-cal">' +
        days.map(function (d) {
          return '<div class="hd">' + d + "</div>";
        }).join("");
      (ledger.weeks || []).forEach(function (week) {
        week.forEach(function (cell) {
          if (!cell) {
            html += '<div class="cell empty-cell"></div>';
            return;
          }
          html +=
            '<div class="cell"><div class="d">' +
            esc(String(cell.date || "").slice(-2)) +
            "</div>";
          if (cell.income) html += '<div class="mm-income truncate">' + inr(cell.income) + "</div>";
          if (cell.expense) html += '<div class="mm-expense truncate">' + inr(cell.expense) + "</div>";
          html += "</div>";
        });
      });
      html += "</div></div></div>";
      return html;
    }

    if (view === "monthly" || view === "total") {
      var txns = ledger.txns || [];
      if (!txns.length) return emptyLedgerHtml(filtered);
      return (
        '<div class="mm-card-list mb-4">' +
        txns
          .map(function (item) {
            return txnCardHtml(item, Object.assign({}, opts, { showDate: true }));
          })
          .join("") +
        "</div>"
      );
    }

    // daily + note
    var daysList = ledger.days || [];
    if (!daysList.length) return emptyLedgerHtml(filtered);
    return daysList
      .map(function (day) {
        return (
          '<div class="mm-day">' +
          '<div class="mm-day-head">' +
          '<span class="date"><span class="dnum">' +
          esc(String(day.date || "").slice(-2)) +
          "</span> <span>" +
          esc(day.label || "") +
          "</span></span>" +
          '<span class="row-gap"><span class="mm-income">' +
          inr(day.income) +
          '</span><span class="mm-expense">' +
          inr(day.expense) +
          "</span></span></div>" +
          (day.txns || [])
            .map(function (item) {
              return txnCardHtml(item, Object.assign({}, opts, { showTime: true }));
            })
            .join("") +
          "</div>"
        );
      })
      .join("");
  }

  function paintLedger(ledger) {
    var root = document.getElementById("mm-trans");
    if (!root || !ledger) return;
    var view = ledger.view || root.dataset.view || "daily";
    root.dataset.month = ledger.year_month;
    root.dataset.view = view;
    root.dataset.q = ledger.q || "";
    root.dataset.accountId = ledger.account_id || "";
    root.dataset.familyMemberId = ledger.family_member_id || "";

    var title = root.querySelector("[data-mm-title]");
    if (title) title.textContent = ledger.label;
    var lead = root.querySelector("[data-mm-lead]");
    if (lead) {
      lead.innerHTML =
        "Last month carried " +
        inr(ledger.prev_income) +
        " in · " +
        inr(ledger.prev_expense) +
        " out. This month " +
        inr(ledger.total) +
        " plus opening becomes total.";
    }
    var prev = root.querySelector("[data-mm-prev]");
    var next = root.querySelector("[data-mm-next]");
    var filterQs =
      (root.dataset.accountId ? "&account_id=" + encodeURIComponent(root.dataset.accountId) : "") +
      (root.dataset.familyMemberId ? "&family_member_id=" + encodeURIComponent(root.dataset.familyMemberId) : "");
    if (prev) {
      prev.dataset.month = ledger.prev;
      prev.href =
        "/admin/finance/transactions?month=" +
        encodeURIComponent(ledger.prev) +
        "&view=" +
        encodeURIComponent(view) +
        filterQs;
    }
    if (next) {
      next.dataset.month = ledger.next;
      next.href =
        "/admin/finance/transactions?month=" +
        encodeURIComponent(ledger.next) +
        "&view=" +
        encodeURIComponent(view) +
        filterQs;
    }
    var monthInput = root.querySelector('input[name="month"]');
    if (monthInput) monthInput.value = ledger.year_month;
    var viewInput = root.querySelector('input[name="view"]');
    if (viewInput) viewInput.value = view;

    var opening = root.querySelector("[data-mm-opening]");
    var income = root.querySelector("[data-mm-income]");
    var expense = root.querySelector("[data-mm-expense]");
    var closing = root.querySelector("[data-mm-closing]");
    var totalSub = root.querySelector("[data-mm-total-sub]");
    var openSub = root.querySelector("[data-mm-opening-sub]");
    if (opening) opening.textContent = inr(ledger.opening);
    if (income) income.textContent = inr(ledger.income);
    if (expense) expense.textContent = inr(ledger.expense);
    if (closing) closing.textContent = inr(ledger.closing);
    if (totalSub) totalSub.textContent = "opening plus " + inr(ledger.total);
    if (openSub) openSub.textContent = "carried into " + ledger.label;

    root.querySelectorAll("[data-mm-view]").forEach(function (a) {
      var v = a.getAttribute("data-mm-view");
      a.classList.toggle("active", v === view);
      a.href =
        "/admin/finance/transactions?month=" +
        encodeURIComponent(ledger.year_month) +
        "&view=" +
        encodeURIComponent(v) +
        filterQs;
    });

    var bulk = root.querySelector("#mm-bulk-delete");
    var canBulk = view === "daily" || view === "monthly" || view === "total" || view === "note";
    if (bulk) {
      bulk.hidden = !(canBulk && root.classList.contains("mm-managing"));
      var bm = bulk.querySelector('input[name="month"]');
      var bv = bulk.querySelector('input[name="view"]');
      if (bm) bm.value = ledger.year_month;
      if (bv) bv.value = view;
    }

    var body = root.querySelector("[data-mm-list]");
    if (body) body.innerHTML = listHtml(ledger, view);

    syncBulkChecks();

    if (window.history && window.history.replaceState) {
      var q = ledger.q ? "&q=" + encodeURIComponent(ledger.q) : "";
      window.history.replaceState(
        { mmMonth: ledger.year_month, mmView: view, mmQ: ledger.q || "" },
        "",
        "/admin/finance/transactions?month=" +
          encodeURIComponent(ledger.year_month) +
          "&view=" +
          encodeURIComponent(view) +
          q +
          filterQs
      );
    }
  }

  function loadLedger(month, view, q, preferCache, accountId, familyMemberId) {
    view = view || "daily";
    q = q || "";
    accountId = accountId || "";
    familyMemberId = familyMemberId || "";
    var key = "ledger:" + month + ":" + view + ":" + q + ":" + accountId + ":" + familyMemberId;
    var url =
      "/admin/finance/api/ledger?month=" +
      encodeURIComponent(month) +
      "&view=" +
      encodeURIComponent(view) +
      (q ? "&q=" + encodeURIComponent(q) : "") +
      (accountId ? "&account_id=" + encodeURIComponent(accountId) : "") +
      (familyMemberId ? "&family_member_id=" + encodeURIComponent(familyMemberId) : "");
    var network = fetchJson(url).then(function (ledger) {
      paintLedger(ledger);
      return idbSet(key, { savedAt: Date.now(), ledger: ledger }).then(function () {
        return ledger;
      });
    });
    if (!preferCache) {
      return network.catch(function (err) {
        toast(err.message || "Could not load", true);
      });
    }
    return idbGet(key).then(function (cached) {
      if (cached && cached.ledger) paintLedger(cached.ledger);
      return network.catch(function (err) {
        if (!(cached && cached.ledger)) toast(err.message || "Could not load", true);
      });
    });
  }

  function syncBulkChecks() {
    var form = document.getElementById("mm-bulk-delete");
    if (!form || form.hidden) return;
    var all = document.getElementById("mm-select-all");
    var countEl = document.getElementById("mm-selected-count");
    var delBtn = document.getElementById("mm-delete-selected");
    var list = Array.prototype.slice.call(document.querySelectorAll(".mm-txn-check"));
    var n = list.filter(function (c) {
      return c.checked;
    }).length;
    if (countEl) countEl.textContent = n + " selected";
    if (delBtn) delBtn.disabled = n === 0;
    if (all) {
      all.checked = list.length > 0 && n === list.length;
      all.indeterminate = n > 0 && n < list.length;
    }
    if (!form.getAttribute("data-confirm-base")) {
      form.setAttribute(
        "data-confirm-base",
        form.getAttribute("data-confirm") || "Move the selected entries to trash?"
      );
    }
    var base = form.getAttribute("data-confirm-base") || "Move the selected entries to trash?";
    form.setAttribute(
      "data-confirm",
      n
        ? "Move " + n + " selected entr" + (n === 1 ? "y" : "ies") + " to trash?"
        : base
    );
  }

  function bustCaches(month) {
    idbSet("dash-invalidate", Date.now());
    if (month) idbSet("dash:" + month, null);
  }

  function deleteTxn(id) {
    var root = document.getElementById("mm-trans");
    var month = (root && root.dataset.month) || "";
    var view = (root && root.dataset.view) || "daily";
    return fetchJson(
      "/admin/finance/api/transactions/" + encodeURIComponent(id) + "/delete",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }
    ).then(function () {
      toast("Moved to trash");
      bustCaches(month);
      return loadLedger(month, view, (root && root.dataset.q) || "", false);
    });
  }

  function bulkDelete(ids) {
    var root = document.getElementById("mm-trans");
    var month = (root && root.dataset.month) || "";
    var view = (root && root.dataset.view) || "daily";
    return fetchJson("/admin/finance/api/transactions/bulk-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids }),
    }).then(function (data) {
      toast((data.deleted || ids.length) + " moved to trash");
      bustCaches(month);
      return loadLedger(month, view, (root && root.dataset.q) || "", false);
    });
  }

  function wireTrans() {
    var root = document.getElementById("mm-trans");
    if (!root) return;

    root.addEventListener("click", function (ev) {
      var manageBtn = ev.target.closest("[data-mm-manage-toggle]");
      if (manageBtn) {
        ev.preventDefault();
        var managing = root.classList.toggle("mm-managing");
        manageBtn.classList.toggle("active", managing);
        manageBtn.setAttribute("aria-pressed", managing ? "true" : "false");
        var curView = root.dataset.view || "daily";
        var canBulkNow =
          curView === "daily" || curView === "monthly" || curView === "total" || curView === "note";
        var bulkForm = document.getElementById("mm-bulk-delete");
        if (bulkForm) bulkForm.hidden = !(managing && canBulkNow);
        if (!managing) {
          document.querySelectorAll(".mm-txn-check").forEach(function (c) {
            c.checked = false;
          });
          syncBulkChecks();
        }
        return;
      }
      var nav = ev.target.closest("[data-mm-prev], [data-mm-next]");
      if (nav) {
        ev.preventDefault();
        loadLedger(
          nav.dataset.month, root.dataset.view || "daily", root.dataset.q || "", true,
          root.dataset.accountId || "", root.dataset.familyMemberId || ""
        );
        return;
      }
      var viewA = ev.target.closest("[data-mm-view]");
      if (viewA) {
        ev.preventDefault();
        loadLedger(
          root.dataset.month, viewA.getAttribute("data-mm-view"), root.dataset.q || "", true,
          root.dataset.accountId || "", root.dataset.familyMemberId || ""
        );
        return;
      }
      var del = ev.target.closest("[data-mm-delete]");
      if (del) {
        ev.preventDefault();
        var id = del.getAttribute("data-mm-delete");
        if (!id) return;
        if (!window.confirm("Move this entry to trash?")) return;
        deleteTxn(id).catch(function (err) {
          toast(err.message || "Could not delete", true);
        });
        return;
      }
    });

    var filter = root.querySelector(".filter-bar");
    if (filter) {
      filter.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var qEl = document.getElementById("fn-q");
        var acctEl = document.getElementById("fn-account");
        var memberEl = document.getElementById("fn-member");
        var q = (qEl && qEl.value) || "";
        var accountId = (acctEl && acctEl.value) || "";
        var familyMemberId = (memberEl && memberEl.value) || "";
        root.dataset.q = q;
        root.dataset.accountId = accountId;
        root.dataset.familyMemberId = familyMemberId;
        loadLedger(root.dataset.month, root.dataset.view || "daily", q, false, accountId, familyMemberId);
      });
    }

    var bulk = document.getElementById("mm-bulk-delete");
    if (bulk) {
      bulk.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var ids = Array.prototype.slice
          .call(document.querySelectorAll(".mm-txn-check:checked"))
          .map(function (c) {
            return c.value;
          });
        if (!ids.length) return;
        var msg = bulk.getAttribute("data-confirm") || "Move the selected entries to trash?";
        if (!window.confirm(msg)) return;
        bulkDelete(ids).catch(function (err) {
          toast(err.message || "Could not delete", true);
        });
      });
      var all = document.getElementById("mm-select-all");
      if (all) {
        all.addEventListener("change", function () {
          document.querySelectorAll(".mm-txn-check").forEach(function (c) {
            c.checked = all.checked;
          });
          syncBulkChecks();
        });
      }
      root.addEventListener("change", function (ev) {
        if (ev.target && ev.target.classList && ev.target.classList.contains("mm-txn-check")) {
          syncBulkChecks();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireForm();
    wireHome();
    wireTrans();
  });
})();
