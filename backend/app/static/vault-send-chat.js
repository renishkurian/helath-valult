/**
 * Pre-video chat between Vault Send owner and guest (HTTP poll).
 * Mount: <div class="js-send-chat" data-role="admin|guest" data-request-id="..." data-token="..."></div>
 */
(function (global) {
  "use strict";

  var POLL_MS = 2200;
  var mounts = {};

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtTime(iso) {
    if (!iso) return "";
    var t = String(iso).replace("T", " ");
    return t.slice(0, 16) + " UTC";
  }

  function urls(el) {
    var role = el.getAttribute("data-role") || "guest";
    var requestId = el.getAttribute("data-request-id") || "";
    var token = el.getAttribute("data-token") || "";
    if (role === "admin") {
      return {
        role: role,
        list: function (after) {
          var u = "/admin/passwords/send-requests/" + encodeURIComponent(requestId) + "/chat";
          return after ? u + "?after=" + encodeURIComponent(after) : u;
        },
        post: "/admin/passwords/send-requests/" + encodeURIComponent(requestId) + "/chat",
        requestId: requestId,
      };
    }
    return {
      role: role,
      list: function (after) {
        var u = "/vault/public/" + encodeURIComponent(token) + "/chat";
        return after ? u + "?after=" + encodeURIComponent(after) : u;
      },
      post: "/vault/public/" + encodeURIComponent(token) + "/chat",
      requestId: requestId,
    };
  }

  function appendMessages(state, messages) {
    if (!messages || !messages.length) return;
    var box = state.log;
    var wasBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    messages.forEach(function (m) {
      if (!m || !m.id || state.seen[m.id]) return;
      state.seen[m.id] = true;
      state.after = m.id;
      var mine =
        (state.role === "admin" && m.from_role === "admin") ||
        (state.role === "guest" && m.from_role === "guest");
      var who = m.from_role === "admin" ? "Owner" : "Guest";
      var row = document.createElement("div");
      row.className = "send-chat-msg" + (mine ? " mine" : " theirs");
      row.innerHTML =
        '<div class="send-chat-bubble">' +
        esc(m.body).replace(/\n/g, "<br>") +
        '</div><div class="send-chat-meta">' +
        esc(who) +
        " · " +
        esc(fmtTime(m.created_at)) +
        "</div>";
      box.appendChild(row);
    });
    if (wasBottom) box.scrollTop = box.scrollHeight;
  }

  function setClosed(state, closed) {
    state.closed = !!closed;
    state.input.disabled = state.closed;
    state.btn.disabled = state.closed;
    state.hint.textContent = state.closed
      ? "Chat closed — this request is no longer pending."
      : "Chat before live video. Messages stay with this request.";
  }

  function poll(state) {
    if (state.busyPoll) return;
    state.busyPoll = true;
    fetch(state.urls.list(state.after), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data) return;
        if (data.status && data.status !== "pending" && data.status !== "seen") {
          setClosed(state, true);
          if (state.role === "guest" && (data.status === "granted" || data.status === "dismissed")) {
            location.reload();
            return;
          }
        }
        appendMessages(state, data.messages || []);
      })
      .catch(function () {})
      .finally(function () {
        state.busyPoll = false;
      });
  }

  function send(state) {
    var text = (state.input.value || "").trim();
    if (!text || state.closed || state.busySend) return;
    state.busySend = true;
    state.btn.disabled = true;
    fetch(state.urls.post, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "fetch",
      },
      body: JSON.stringify({ text: text }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          state.hint.textContent =
            (res.data && res.data.detail) || "Could not send message.";
          return;
        }
        state.input.value = "";
        if (res.data && res.data.message) {
          appendMessages(state, [res.data.message]);
        } else {
          poll(state);
        }
      })
      .catch(function () {
        state.hint.textContent = "Could not send message.";
      })
      .finally(function () {
        state.busySend = false;
        state.btn.disabled = state.closed;
        state.input.focus();
      });
  }

  function mount(el) {
    if (!el || el.getAttribute("data-mounted") === "1") return null;
    var u = urls(el);
    if (u.role === "admin" && !u.requestId) return null;
    if (u.role === "guest" && !(el.getAttribute("data-token") || "")) return null;

    el.setAttribute("data-mounted", "1");
    el.classList.add("send-chat");
    el.innerHTML =
      '<div class="send-chat-head"><i class="bi bi-chat-dots"></i> Chat</div>' +
      '<div class="send-chat-log" data-chat="log"></div>' +
      '<div class="send-chat-compose">' +
      '<textarea class="form-control form-control-sm" rows="2" maxlength="1000" ' +
      'placeholder="Write a message…" data-chat="input"></textarea>' +
      '<button type="button" class="btn btn-sm btn-primary" data-chat="send">' +
      '<i class="bi bi-send"></i> Send</button>' +
      "</div>" +
      '<div class="form-text send-chat-hint" data-chat="hint">Chat before live video. Messages stay with this request.</div>';

    var state = {
      el: el,
      role: u.role,
      urls: u,
      requestId: u.requestId || "",
      after: "",
      seen: {},
      closed: false,
      busyPoll: false,
      busySend: false,
      log: el.querySelector('[data-chat="log"]'),
      input: el.querySelector('[data-chat="input"]'),
      btn: el.querySelector('[data-chat="send"]'),
      hint: el.querySelector('[data-chat="hint"]'),
      timer: null,
    };

    state.btn.addEventListener("click", function () {
      send(state);
    });
    state.input.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        send(state);
      }
    });

    poll(state);
    state.timer = setInterval(function () {
      poll(state);
    }, POLL_MS);

    var key = state.requestId || el.getAttribute("data-token") || String(Math.random());
    mounts[key] = state;
    if (state.requestId) mounts["id:" + state.requestId] = state;
    return state;
  }

  function boot(root) {
    (root || document).querySelectorAll(".js-send-chat").forEach(function (el) {
      mount(el);
    });
  }

  function refresh(requestId) {
    var state = mounts["id:" + requestId];
    if (state) poll(state);
  }

  global.VaultSendChat = { mount: mount, boot: boot, refresh: refresh };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      boot();
    });
  } else {
    boot();
  }
})(window);
