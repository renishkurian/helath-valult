(function () {
  var bootEl = document.getElementById("ask-ai-boot");
  if (!bootEl) return;
  var boot = {};
  try { boot = JSON.parse(bootEl.textContent || "{}"); } catch (e) { boot = {}; }

  var shell = document.getElementById("ask-shell");
  var rail = document.getElementById("ask-rail");
  var mask = document.getElementById("ask-rail-mask");
  var threadBox = document.getElementById("ask-threads");
  var emptyEl = document.getElementById("ask-empty");
  var msgsEl = document.getElementById("ask-msgs");
  var scrollEl = document.getElementById("ask-scroll");
  var form = document.getElementById("ask-form");
  var input = document.getElementById("ask-input");
  var sendBtn = document.getElementById("ask-send");
  var titleEl = document.getElementById("ask-title");
  var delBtn = document.getElementById("ask-delete");
  var hintsEl = document.getElementById("ask-hints");

  var state = { threadId: null, busy: false, threads: [] };

  function esc(s) {
    return (window.VaultMd && VaultMd.esc) ? VaultMd.esc(s) : String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderMd(raw) {
    if (window.VaultMd && typeof VaultMd.render === "function") {
      return VaultMd.render(raw);
    }
    return "<p>" + esc(raw).replace(/\n/g, "<br>") + "</p>";
  }

  function toBottom() {
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
  }

  function isBrainCommand(text) {
    return /^(remember|forget|don't forget|do not forget|always|never|i prefer)\b/i.test(String(text || "").trim());
  }

  function setBusy(on) {
    state.busy = on;
    if (sendBtn) sendBtn.disabled = on;
    if (input) input.disabled = on;
  }

  function showConversation(hasMsgs) {
    if (emptyEl) emptyEl.hidden = !!hasMsgs;
    if (msgsEl) msgsEl.hidden = !hasMsgs;
    if (delBtn) delBtn.hidden = !state.threadId;
  }

  function splitAction(content) {
    var text = String(content || "");
    var m = text.match(/```vault-action\s*(\{[\s\S]*?\})\s*```/i);
    if (!m) return { text: text, action: null };
    var action = null;
    try { action = JSON.parse(m[1]); } catch (e) { action = null; }
    if (!action || !action.type) return { text: text, action: null };
    if (action.type === "create_shop_list" && Array.isArray(action.items)) {
      return { text: text.replace(m[0], "").trim(), action: action };
    }
    if (action.type === "create_diary_entry" && action.title) {
      return { text: text.replace(m[0], "").trim(), action: action };
    }
    if (action.type === "create_diary_folder" && action.name) {
      return { text: text.replace(m[0], "").trim(), action: action };
    }
    if (action.type === "create_finance_txn" && action.amount != null && Number(action.amount) > 0) {
      return { text: text.replace(m[0], "").trim(), action: action };
    }
    return { text: text, action: null };
  }

  function actionCard(action) {
    if (action && action.type === "create_diary_entry") {
      return diaryActionCard(action);
    }
    if (action && action.type === "create_diary_folder") {
      return diaryFolderActionCard(action);
    }
    if (action && action.type === "create_finance_txn") {
      return financeActionCard(action);
    }
    return shopActionCard(action);
  }

  function shopActionCard(action) {
    var wrap = document.createElement("div");
    wrap.className = "ask-action";
    var items = (action.items || []).slice(0, 60);
    var lis = items.map(function (it) {
      var name = typeof it === "string" ? it : (it && it.name) || "";
      var qty = (it && it.quantity != null) ? it.quantity : "";
      var unit = (it && it.unit) || "";
      var meta = [qty, unit].filter(Boolean).join(" ");
      return "<li><strong>" + esc(name) + "</strong>" + (meta ? " <span>" + esc(meta) + "</span>" : "") + "</li>";
    }).join("");
    wrap.innerHTML =
      '<div class="ask-action-head"><i class="bi bi-cart3"></i> Proposed shopping list</div>' +
      '<div class="ask-action-title">' + esc(action.name || "Shopping list") + "</div>" +
      "<ul>" + lis + "</ul>" +
      '<div class="ask-action-bar">' +
        '<button type="button" class="btn btn-sm btn-primary ask-action-go">Create list</button>' +
        '<button type="button" class="btn btn-sm btn-outline-light ask-action-skip">Dismiss</button>' +
        '<span class="ask-action-status" hidden></span>' +
      "</div>";
    var go = wrap.querySelector(".ask-action-go");
    var skip = wrap.querySelector(".ask-action-skip");
    var status = wrap.querySelector(".ask-action-status");
    skip.addEventListener("click", function () { wrap.remove(); });
    go.addEventListener("click", function () {
      go.disabled = true;
      skip.disabled = true;
      status.hidden = false;
      status.textContent = "Creating…";
      api("/admin/ai/ask/apply-shop-list", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(action),
      }).then(function (res) {
        status.innerHTML = 'Created <a href="' + esc(res.url || ("/admin/tracker/lists/" + res.list_id)) + '">' +
          esc(res.name || "list") + "</a> · " + esc(String(res.item_count || items.length)) + " items";
        go.hidden = true;
        skip.hidden = true;
      }).catch(function (err) {
        status.textContent = err.message || "Could not create list";
        go.disabled = false;
        skip.disabled = false;
      });
    });
    return wrap;
  }

  function diaryActionCard(action) {
    var wrap = document.createElement("div");
    wrap.className = "ask-action ask-action-diary";
    var charges = (action.charges || []).slice(0, 40);
    var lis = charges.map(function (c) {
      var label = (c && (c.label || c.name)) || "";
      var amt = (c && c.amount != null) ? c.amount : "";
      return "<li><strong>" + esc(label) + "</strong>" +
        (amt !== "" ? " <span>₹ " + esc(String(amt)) + "</span>" : "") + "</li>";
    }).join("");
    var preview = "";
    if (lis) {
      preview = "<ul>" + lis + "</ul>";
    } else if (action.body) {
      preview = '<div class="ask-action-preview md-body">' + renderMd(String(action.body).slice(0, 800)) + "</div>";
    }
    wrap.innerHTML =
      '<div class="ask-action-head"><i class="bi bi-journal-richtext"></i> Proposed diary entry</div>' +
      '<div class="ask-action-title">' + esc(action.title || "Diary entry") + "</div>" +
      (action.entry_date ? '<div class="ask-action-meta">' + esc(action.entry_date) +
        (action.category ? " · " + esc(action.category) : "") + "</div>" : "") +
      preview +
      '<div class="ask-action-bar">' +
        '<button type="button" class="btn btn-sm btn-primary ask-action-go">Save to diary</button>' +
        '<button type="button" class="btn btn-sm btn-outline-light ask-action-skip">Dismiss</button>' +
        '<span class="ask-action-status" hidden></span>' +
      "</div>";
    var go = wrap.querySelector(".ask-action-go");
    var skip = wrap.querySelector(".ask-action-skip");
    var status = wrap.querySelector(".ask-action-status");
    skip.addEventListener("click", function () { wrap.remove(); });
    go.addEventListener("click", function () {
      go.disabled = true;
      skip.disabled = true;
      status.hidden = false;
      status.textContent = "Saving…";
      api("/admin/ai/ask/apply-diary-entry", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(action),
      }).then(function (res) {
        status.innerHTML = 'Saved <a href="' + esc(res.url || ("/admin/diary/" + res.entry_id)) + '">' +
          esc(res.title || "entry") + "</a>";
        go.hidden = true;
        skip.hidden = true;
      }).catch(function (err) {
        status.textContent = err.message || "Could not save diary entry";
        go.disabled = false;
        skip.disabled = false;
      });
    });
    return wrap;
  }

  function diaryFolderActionCard(action) {
    var wrap = document.createElement("div");
    wrap.className = "ask-action ask-action-diary-folder";
    var swatch = action.color
      ? '<span class="ask-folder-swatch" style="background:' + esc(action.color) + '"></span>'
      : '<i class="bi bi-folder-plus"></i>';
    wrap.innerHTML =
      '<div class="ask-action-head">' + swatch + ' Proposed diary folder</div>' +
      '<div class="ask-action-title">' + esc(action.name || "Folder") + "</div>" +
      '<div class="ask-action-bar">' +
        '<button type="button" class="btn btn-sm btn-primary ask-action-go">Create folder</button>' +
        '<button type="button" class="btn btn-sm btn-outline-light ask-action-skip">Dismiss</button>' +
        '<span class="ask-action-status" hidden></span>' +
      "</div>";
    var go = wrap.querySelector(".ask-action-go");
    var skip = wrap.querySelector(".ask-action-skip");
    var status = wrap.querySelector(".ask-action-status");
    skip.addEventListener("click", function () { wrap.remove(); });
    go.addEventListener("click", function () {
      go.disabled = true;
      skip.disabled = true;
      status.hidden = false;
      status.textContent = "Creating…";
      api("/admin/ai/ask/apply-diary-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(action),
      }).then(function (res) {
        var verb = res.created === false ? "Opened existing" : "Created";
        status.innerHTML = verb + ' <a href="' + esc(res.url || "/admin/diary/manage") + '">' +
          esc(res.name || "folder") + "</a>";
        go.hidden = true;
        skip.hidden = true;
      }).catch(function (err) {
        status.textContent = err.message || "Could not create folder";
        go.disabled = false;
        skip.disabled = false;
      });
    });
    return wrap;
  }

  function financeActionCard(action) {
    var wrap = document.createElement("div");
    wrap.className = "ask-action ask-action-finance";
    var amt = action.amount != null ? String(action.amount) : "";
    var meta = [action.txn_date, action.account, action.category, action.payment_method]
      .filter(Boolean).map(String).join(" · ");
    wrap.innerHTML =
      '<div class="ask-action-head"><i class="bi bi-wallet2"></i> Proposed Money Manager entry</div>' +
      '<div class="ask-action-title">' + esc(action.payee || "Expense") +
        (amt ? ' · ₹ ' + esc(amt) : "") + "</div>" +
      (meta ? '<div class="ask-action-meta">' + esc(meta) + "</div>" : "") +
      (action.notes ? '<p class="ask-action-preview">' + esc(String(action.notes).slice(0, 220)) + "</p>" : "") +
      '<div class="ask-action-bar">' +
        '<button type="button" class="btn btn-sm btn-primary ask-action-go">Save to Money Manager</button>' +
        '<button type="button" class="btn btn-sm btn-outline-light ask-action-skip">Dismiss</button>' +
        '<span class="ask-action-status" hidden></span>' +
      "</div>";
    var go = wrap.querySelector(".ask-action-go");
    var skip = wrap.querySelector(".ask-action-skip");
    var status = wrap.querySelector(".ask-action-status");
    skip.addEventListener("click", function () { wrap.remove(); });
    go.addEventListener("click", function () {
      go.disabled = true;
      skip.disabled = true;
      status.hidden = false;
      status.textContent = "Saving…";
      api("/admin/ai/ask/apply-finance-txn", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify(action),
      }).then(function (res) {
        status.innerHTML = 'Saved <a href="' + esc(res.url || "/admin/finance") + '">' +
          esc(res.payee || "transaction") + "</a> on " + esc(res.account_name || "account");
        go.hidden = true;
        skip.hidden = true;
      }).catch(function (err) {
        status.textContent = err.message || "Could not save transaction";
        go.disabled = false;
        skip.disabled = false;
      });
    });
    return wrap;
  }

  function bubble(role, content, typing) {
    var turn = document.createElement("div");
    turn.className = "ask-turn " + (role === "user" ? "user" : "assistant");
    var ico = role === "user" ? "bi-person" : "bi-stars";
    var bubbleEl = document.createElement("div");
    bubbleEl.className = "ask-bubble";
    if (typing) {
      bubbleEl.innerHTML = '<div class="ask-typing" aria-label="Thinking"><i></i><i></i><i></i></div>';
    } else if (role === "assistant") {
      var parts = splitAction(content);
      bubbleEl.innerHTML = renderMd(parts.text);
      if (parts.action) bubbleEl.appendChild(actionCard(parts.action));
    } else {
      bubbleEl.innerHTML = renderMd(content);
    }
    turn.innerHTML = '<div class="ask-avatar" aria-hidden="true"><i class="bi ' + ico + '"></i></div>';
    turn.appendChild(bubbleEl);
    return turn;
  }

  function learnedNote(items) {
    if (!items || !items.length) return null;
    var el = document.createElement("div");
    el.className = "ask-learned";
    var bits = items.slice(0, 3).map(function (m) { return esc(m.content || ""); }).filter(Boolean);
    el.innerHTML = '<i class="bi bi-lightbulb"></i> Saved to brain' +
      (bits.length ? " · " + bits.join("; ") : "") +
      ' <a href="/admin/ai/brain">Review</a>';
    return el;
  }

  function renderMessages(messages) {
    msgsEl.innerHTML = "";
    (messages || []).forEach(function (m) {
      msgsEl.appendChild(bubble(m.role, m.content, false));
    });
    showConversation((messages || []).length > 0);
    toBottom();
  }

  function fmtThreadWhen(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var now = new Date();
    var startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var startThat = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var dayMs = 86400000;
    var dayDiff = Math.round((startToday - startThat) / dayMs);
    var timeOpts = { hour: "numeric", minute: "2-digit" };
    var time = d.toLocaleTimeString(undefined, timeOpts);
    if (dayDiff === 0) return "Today · " + time;
    if (dayDiff === 1) return "Yesterday · " + time;
    var dateOpts = { day: "numeric", month: "short" };
    if (d.getFullYear() !== now.getFullYear()) dateOpts.year = "numeric";
    return d.toLocaleDateString(undefined, dateOpts) + " · " + time;
  }

  function renderThreads() {
    var rows = state.threads || [];
    if (!rows.length) {
      threadBox.innerHTML = '<div class="ask-rail-empty">No chats yet</div>';
      return;
    }
    threadBox.innerHTML = rows.map(function (t) {
      var active = t.id === state.threadId ? " active" : "";
      var when = fmtThreadWhen(t.updated_at || t.created_at);
      return (
        '<div class="ask-thread-row' + active + '" role="listitem">' +
          '<button class="ask-thread" type="button" data-id="' + esc(t.id) + '">' +
            '<i class="bi bi-chat-dots" aria-hidden="true"></i>' +
            '<span class="ask-thread-body">' +
              '<span class="ask-thread-top">' +
                '<span class="ask-thread-title">' + esc(t.title || "New chat") + "</span>" +
                (when ? '<span class="ask-thread-when">' + esc(when) + "</span>" : "") +
              "</span>" +
              (t.preview ? '<span class="ask-thread-preview">' + esc(t.preview) + "</span>" : "") +
            "</span>" +
          "</button>" +
          '<button class="ask-thread-del" type="button" data-id="' + esc(t.id) + '" title="Delete chat" aria-label="Delete chat">' +
            '<i class="bi bi-trash3" aria-hidden="true"></i>' +
          "</button>" +
        "</div>"
      );
    }).join("");
  }

  function deleteThread(id) {
    if (!id) return;
    var run = function () {
      api("/admin/ai/ask/threads/" + encodeURIComponent(id) + "/delete", { method: "POST" })
        .then(function () {
          if (state.threadId === id) {
            return openThread(null).then(function () { return loadThreads(); });
          }
          return loadThreads();
        })
        .catch(function () {});
    };
    if (window.vaultConfirm) {
      window.vaultConfirm("Delete this chat?").then(function (ok) { if (ok) run(); });
      return;
    }
    if (!confirm("Delete this chat?")) return;
    run();
  }

  function closeRail() {
    shell.classList.remove("rail-open");
    if (mask) mask.hidden = true;
  }
  function openRail() {
    shell.classList.add("rail-open");
    if (mask) mask.hidden = false;
  }

  async function api(path, opts) {
    var res = await fetch(path, Object.assign({
      credentials: "same-origin",
      headers: { "Accept": "application/json" },
    }, opts || {}));
    var data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) {
      var err = new Error(data.detail || res.statusText || "Request failed");
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function loadThreads() {
    try {
      state.threads = await api("/admin/ai/ask/threads");
    } catch (e) {
      state.threads = [];
    }
    renderThreads();
  }

  async function openThread(id) {
    if (!id) {
      state.threadId = null;
      titleEl.textContent = "New chat";
      renderMessages([]);
      renderThreads();
      closeRail();
      input && input.focus();
      return;
    }
    var detail = await api("/admin/ai/ask/threads/" + encodeURIComponent(id));
    state.threadId = detail.id;
    titleEl.textContent = detail.title || "Chat";
    renderMessages(detail.messages || []);
    renderThreads();
    closeRail();
  }

  async function send(text) {
    text = (text || "").trim();
    if (!text || state.busy) return;
    if (!boot.hasProvider && !isBrainCommand(text)) {
      window.location.href = "/admin/ai/providers";
      return;
    }
    showConversation(true);
    msgsEl.appendChild(bubble("user", text, false));
    var think = bubble("assistant", "", true);
    msgsEl.appendChild(think);
    toBottom();
    input.value = "";
    grow();
    setBusy(true);
    try {
      var body = await api("/admin/ai/ask/send", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ message: text, thread_id: state.threadId }),
      });
      state.threadId = body.thread_id;
      titleEl.textContent = body.title || "Chat";
      renderMessages(body.messages || []);
      var note = learnedNote(body.learned);
      if (note && msgsEl) {
        var last = msgsEl.querySelector(".ask-turn.assistant:last-child .ask-bubble");
        if (last) last.appendChild(note);
      }
      await loadThreads();
    } catch (e) {
      think.querySelector(".ask-bubble").innerHTML =
        '<p class="ask-err">' + esc(e.message || "Could not reach the provider") + "</p>";
    } finally {
      setBusy(false);
      input && input.focus();
    }
  }

  function grow() {
    if (!input) return;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
  }

  (boot.hints || []).forEach(function (h) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ask-chip";
    btn.textContent = h.label;
    btn.addEventListener("click", function () {
      if (!boot.hasProvider) {
        window.location.href = "/admin/ai/providers";
        return;
      }
      send(h.prompt || h.label);
    });
    hintsEl && hintsEl.appendChild(btn);
  });

  form && form.addEventListener("submit", function (e) {
    e.preventDefault();
    send(input.value);
  });
  input && input.addEventListener("input", grow);
  input && input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input.value);
    }
  });

  document.getElementById("ask-new") && document.getElementById("ask-new").addEventListener("click", function () {
    openThread(null);
  });
  document.getElementById("ask-rail-open") && document.getElementById("ask-rail-open").addEventListener("click", openRail);
  document.getElementById("ask-rail-close") && document.getElementById("ask-rail-close").addEventListener("click", closeRail);
  mask && mask.addEventListener("click", closeRail);

  threadBox && threadBox.addEventListener("click", function (e) {
    var del = e.target.closest(".ask-thread-del");
    if (del) {
      e.preventDefault();
      e.stopPropagation();
      deleteThread(del.getAttribute("data-id"));
      return;
    }
    var btn = e.target.closest(".ask-thread");
    if (!btn) return;
    openThread(btn.getAttribute("data-id")).catch(function (err) {
      msgsEl.hidden = false;
      emptyEl.hidden = true;
      msgsEl.innerHTML = '<p class="ask-err">' + esc(err.message) + "</p>";
    });
  });

  delBtn && delBtn.addEventListener("click", function () {
    deleteThread(state.threadId);
  });

  var testStatus = document.getElementById("ask-test-status");
  function setTestStatus(kind, text) {
    if (!testStatus) return;
    testStatus.hidden = !text;
    testStatus.className = "ask-test-status" + (kind ? " " + kind : "");
    testStatus.textContent = text || "";
  }
  async function testConnection(btn) {
    if (!boot.hasProvider || state.busy) return;
    var buttons = [document.getElementById("ask-test"), document.getElementById("ask-test-bar")].filter(Boolean);
    buttons.forEach(function (b) { b.disabled = true; });
    setTestStatus("busy", "Testing " + (boot.providerName || "provider") + "…");
    try {
      var body = await api("/admin/ai/ask/test", { method: "POST" });
      var sample = (body.sample || "ok").replace(/\s+/g, " ").trim();
      setTestStatus("ok", "Connected · " + (body.name || boot.providerName || "provider") + " · " + sample);
    } catch (e) {
      setTestStatus("err", e.message || "Connection failed");
    } finally {
      buttons.forEach(function (b) { b.disabled = false; });
    }
  }
  document.getElementById("ask-test") && document.getElementById("ask-test").addEventListener("click", function () {
    testConnection(this);
  });
  document.getElementById("ask-test-bar") && document.getElementById("ask-test-bar").addEventListener("click", function () {
    testConnection(this);
  });

  loadThreads();
  if (input) input.focus();
})();
