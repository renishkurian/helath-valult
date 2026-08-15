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
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function renderMd(raw) {
    var text = String(raw || "").replace(/\r\n/g, "\n");
    var blocks = text.split("\n\n");
    var html = [];
    for (var b = 0; b < blocks.length; b++) {
      var block = blocks[b];
      if (!block.trim()) continue;
      var lines = block.split("\n");
      if (lines[0].indexOf("|") !== -1 && lines.length >= 2) {
        html.push(mdTable(lines));
        continue;
      }
      if (/^```/.test(lines[0])) {
        var code = lines.slice(1).join("\n").replace(/```\s*$/, "");
        html.push("<pre><code>" + esc(code) + "</code></pre>");
        continue;
      }
      if (/^#{1,3}\s/.test(lines[0]) && lines.length === 1) {
        html.push("<h3>" + inline(lines[0].replace(/^#{1,3}\s+/, "")) + "</h3>");
        continue;
      }
      var list = lines.every(function (ln) { return /^\s*[-*]\s+/.test(ln) || /^\s*\d+\.\s+/.test(ln); });
      if (list) {
        var ol = /^\s*\d+\./.test(lines[0]);
        var items = lines.map(function (ln) {
          return "<li>" + inline(ln.replace(/^\s*(?:[-*]|\d+\.)\s+/, "")) + "</li>";
        }).join("");
        html.push((ol ? "<ol>" : "<ul>") + items + (ol ? "</ol>" : "</ul>"));
        continue;
      }
      html.push("<p>" + lines.map(inline).join("<br>") + "</p>");
    }
    return html.join("") || "<p></p>";
  }

  function mdTable(lines) {
    var rows = lines.filter(function (ln) { return ln.indexOf("|") !== -1; });
    if (rows.length < 2) return "<p>" + lines.map(inline).join("<br>") + "</p>";
    function cells(ln) {
      return ln.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(function (c) { return c.trim(); });
    }
    var head = cells(rows[0]);
    var start = /^[\s|:-]+$/.test(rows[1]) ? 2 : 1;
    var out = "<table><thead><tr>" + head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") + "</tr></thead><tbody>";
    for (var i = start; i < rows.length; i++) {
      out += "<tr>" + cells(rows[i]).map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
    }
    return out + "</tbody></table>";
  }

  function inline(s) {
    var t = esc(s);
    t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" rel="noopener">$1</a>');
    return t;
  }

  function toBottom() {
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
  }

  function setBusy(on) {
    state.busy = on;
    if (sendBtn) sendBtn.disabled = on || !boot.hasProvider;
    if (input) input.disabled = on || !boot.hasProvider;
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
      preview = '<p class="ask-action-preview">' + esc(String(action.body).slice(0, 220)) + "</p>";
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

  function renderMessages(messages) {
    msgsEl.innerHTML = "";
    (messages || []).forEach(function (m) {
      msgsEl.appendChild(bubble(m.role, m.content, false));
    });
    showConversation((messages || []).length > 0);
    toBottom();
  }

  function renderThreads() {
    var rows = state.threads || [];
    if (!rows.length) {
      threadBox.innerHTML = '<div class="ask-rail-empty">No chats yet</div>';
      return;
    }
    threadBox.innerHTML = rows.map(function (t) {
      var active = t.id === state.threadId ? " active" : "";
      return (
        '<button class="ask-thread' + active + '" type="button" data-id="' + esc(t.id) + '" role="listitem">' +
          '<i class="bi bi-chat-dots"></i>' +
          '<span class="ask-thread-body">' +
            '<span class="ask-thread-title">' + esc(t.title || "New chat") + "</span>" +
            (t.preview ? '<span class="ask-thread-preview">' + esc(t.preview) + "</span>" : "") +
          "</span>" +
        "</button>"
      );
    }).join("");
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
    if (!boot.hasProvider) return;
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
    var btn = e.target.closest(".ask-thread");
    if (!btn) return;
    openThread(btn.getAttribute("data-id")).catch(function (err) {
      msgsEl.hidden = false;
      emptyEl.hidden = true;
      msgsEl.innerHTML = '<p class="ask-err">' + esc(err.message) + "</p>";
    });
  });

  delBtn && delBtn.addEventListener("click", function () {
    if (!state.threadId) return;
    var run = function () {
      api("/admin/ai/ask/threads/" + encodeURIComponent(state.threadId) + "/delete", { method: "POST" })
        .then(function () { return loadThreads(); })
        .then(function () { openThread(null); })
        .catch(function () {});
    };
    if (window.vaultConfirm) {
      window.vaultConfirm("Delete this chat?").then(function (ok) { if (ok) run(); });
      return;
    }
    if (!confirm("Delete this chat?")) return;
    run();
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
  if (boot.hasProvider && input) input.focus();
})();
