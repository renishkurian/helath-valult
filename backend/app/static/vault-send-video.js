/**
 * Live video verify for Vault Send access requests (WebRTC + HTTP signaling).
 * Admin: VaultSendVideo.admin({ requestId, grantUrl, onClose })
 * Guest: VaultSendVideo.guest({ token, statusUrl, pollMs })
 */
(function (global) {
  "use strict";

  var ICE = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };

  function postJson(url, body, headers) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: Object.assign({ "Content-Type": "application/json", "X-Requested-With": "fetch" }, headers || {}),
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (j) { throw new Error((j && j.detail) || r.statusText); }, function () { throw new Error(r.statusText); });
      return r.json().catch(function () { return { ok: true }; });
    });
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) {
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
      });
  }

  function stopPc(pc, stream) {
    try {
      if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    } catch (e) {}
    try {
      if (pc) pc.close();
    } catch (e) {}
  }

  function wireIce(pc, postUrl) {
    pc.onicecandidate = function (ev) {
      if (!ev.candidate) return;
      postJson(postUrl, { type: "ice", candidate: ev.candidate.toJSON() }).catch(function () {});
    };
  }

  async function applySignals(pc, messages, role) {
    for (var i = 0; i < messages.length; i++) {
      var m = messages[i];
      if (!m || !m.type) continue;
      if (m.type === "hangup") return "hangup";
      if (m.type === "ready" && role === "admin") continue;
      if (m.type === "offer" && m.sdp) {
        await pc.setRemoteDescription({ type: "offer", sdp: m.sdp });
        var answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        return { answer: answer.sdp };
      }
      if (m.type === "answer" && m.sdp) {
        if (pc.signalingState !== "stable") {
          await pc.setRemoteDescription({ type: "answer", sdp: m.sdp });
        }
      }
      if (m.type === "ice" && m.candidate) {
        try {
          await pc.addIceCandidate(m.candidate);
        } catch (e) {}
      }
    }
    return null;
  }

  function ensureModal() {
    var el = document.getElementById("vault-video-modal");
    if (el) return el;
    el = document.createElement("div");
    el.id = "vault-video-modal";
    el.className = "modal fade";
    el.tabIndex = -1;
    el.innerHTML =
      '<div class="modal-dialog modal-dialog-centered modal-lg">' +
      '<div class="modal-content">' +
      '<div class="modal-header">' +
      '<span class="card-ico plum"><i class="bi bi-camera-video"></i></span>' +
      '<h2 class="modal-title" id="vault-video-title">Live video verify</h2>' +
      '<button class="btn-close" type="button" data-bs-dismiss="modal" aria-label="Close"></button>' +
      "</div>" +
      '<div class="modal-body">' +
      '<p class="text-muted small mb-2" id="vault-video-status">Waiting for the guest to accept…</p>' +
      '<video id="vault-video-remote" playsinline autoplay style="width:100%;max-height:420px;background:#000;border-radius:12px;"></video>' +
      "</div>" +
      '<div class="modal-footer flex-wrap gap-2">' +
      '<button type="button" class="btn btn-ghost" data-bs-dismiss="modal" id="vault-video-end">End video</button>' +
      '<form method="post" id="vault-video-grant-form" class="ms-auto">' +
      '<input type="hidden" name="next" id="vault-video-grant-next" value="">' +
      '<button type="submit" class="btn btn-primary" id="vault-video-grant" disabled>' +
      '<i class="bi bi-check2-circle"></i> Grant access</button>' +
      "</form>" +
      "</div></div></div>";
    document.body.appendChild(el);
    return el;
  }

  function admin(opts) {
    var requestId = opts.requestId;
    var base = "/admin/passwords/send-requests/" + encodeURIComponent(requestId) + "/video";
    var modalEl = ensureModal();
    var remote = document.getElementById("vault-video-remote");
    var statusEl = document.getElementById("vault-video-status");
    var grantBtn = document.getElementById("vault-video-grant");
    var grantForm = document.getElementById("vault-video-grant-form");
    var grantNext = document.getElementById("vault-video-grant-next");
    grantForm.action = "/admin/passwords/send-requests/" + encodeURIComponent(requestId) + "/grant";
    grantNext.value = opts.next || (location.pathname + location.search);
    grantBtn.disabled = true;
    statusEl.textContent = "Asking guest for live video…";
    remote.srcObject = null;

    var pc = new RTCPeerConnection(ICE);
    var pollTimer = null;
    var closed = false;
    wireIce(pc, base + "/signal");
    pc.ontrack = function (ev) {
      remote.srcObject = ev.streams[0] || new MediaStream([ev.track]);
      statusEl.textContent = "Live — verify the person, then grant access.";
      grantBtn.disabled = false;
    };
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    function cleanup() {
      if (closed) return;
      closed = true;
      if (pollTimer) clearInterval(pollTimer);
      stopPc(pc, null);
      postJson(base + "/end", {}).catch(function () {});
    }

    modalEl.addEventListener("hidden.bs.modal", cleanup, { once: true });
    document.getElementById("vault-video-end").onclick = function () {
      cleanup();
      var inst = bootstrap.Modal.getInstance(modalEl);
      if (inst) inst.hide();
    };

    postJson(base + "/request", {})
      .then(function () {
        statusEl.textContent = "Waiting for the guest to accept and turn on the camera…";
        var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
        pollTimer = setInterval(function () {
          if (closed) return;
          getJson(base + "/signals")
            .then(function (data) {
              if ((data.video_status || "") === "ended") {
                statusEl.textContent = "Video ended.";
                cleanup();
                return;
              }
              return applySignals(pc, data.messages || [], "admin").then(function (res) {
                if (res === "hangup") {
                  statusEl.textContent = "Guest ended the video.";
                  cleanup();
                  return;
                }
                if (res && res.answer) {
                  return postJson(base + "/signal", { type: "answer", sdp: res.answer });
                }
              });
            })
            .catch(function () {});
        }, 900);
      })
      .catch(function (err) {
        statusEl.textContent = err.message || "Could not start video request";
        alert(statusEl.textContent);
      });
  }

  function guest(opts) {
    var token = opts.token;
    var root = document.getElementById("guest-video-panel");
    if (!root) return;
    var statusUrl = "/vault/public/" + encodeURIComponent(token) + "/request-status";
    var signalUrl = "/vault/public/" + encodeURIComponent(token) + "/video/signal";
    var signalsUrl = "/vault/public/" + encodeURIComponent(token) + "/video/signals";
    var acceptUrl = "/vault/public/" + encodeURIComponent(token) + "/video/accept";
    var pc = null;
    var localStream = null;
    var pollTimer = null;
    var signalTimer = null;
    var active = false;

    function setUi(state, msg) {
      root.hidden = state === "hidden";
      var wait = root.querySelector("[data-v='wait']");
      var live = root.querySelector("[data-v='live']");
      var note = root.querySelector("[data-v='note']");
      if (wait) wait.hidden = state !== "wait";
      if (live) live.hidden = state !== "live";
      if (note && msg) note.textContent = msg;
    }

    function stopAll() {
      active = false;
      if (signalTimer) clearInterval(signalTimer);
      stopPc(pc, localStream);
      pc = null;
      localStream = null;
      var vid = root.querySelector("video");
      if (vid) vid.srcObject = null;
      setUi("hidden");
    }

    async function startCall() {
      if (active) return;
      active = true;
      setUi("live", "Camera on — the owner can see you now.");
      try {
        localStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
          audio: true,
        });
      } catch (e) {
        active = false;
        setUi("wait", "Camera permission denied. Allow the camera and try again.");
        return;
      }
      var preview = root.querySelector("video");
      if (preview) preview.srcObject = localStream;
      pc = new RTCPeerConnection(ICE);
      localStream.getTracks().forEach(function (t) { pc.addTrack(t, localStream); });
      wireIce(pc, signalUrl);
      await postJson(acceptUrl, {});
      var offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await postJson(signalUrl, { type: "offer", sdp: offer.sdp });
      signalTimer = setInterval(function () {
        getJson(signalsUrl)
          .then(function (data) {
            if ((data.status || "") === "granted") {
              stopAll();
              location.reload();
              return;
            }
            if ((data.video_status || "") === "ended") {
              stopAll();
              setUi("hidden");
              return;
            }
            return applySignals(pc, data.messages || [], "guest").then(function (res) {
              if (res === "hangup") stopAll();
            });
          })
          .catch(function () {});
      }, 900);
    }

    root.querySelector("[data-v='accept']").addEventListener("click", function () {
      startCall();
    });
    root.querySelector("[data-v='hangup']").addEventListener("click", function () {
      postJson(signalUrl, { type: "hangup" }).catch(function () {});
      stopAll();
    });

    pollTimer = setInterval(function () {
      if (active) return;
      getJson(statusUrl)
        .then(function (data) {
          if ((data.status || "") === "granted") {
            clearInterval(pollTimer);
            location.reload();
            return;
          }
          if ((data.status || "") === "dismissed") {
            clearInterval(pollTimer);
            location.reload();
            return;
          }
          var vs = data.video_status || "none";
          if (vs === "requested") {
            setUi("wait", "The owner asked for a live video check before granting access.");
          } else if (vs === "live" && !active) {
            setUi("wait", "Live video was requested — tap Accept to turn on your camera.");
          } else if (vs === "none" || vs === "ended") {
            setUi("hidden");
          }
        })
        .catch(function () {});
    }, opts.pollMs || 2500);

    // Initial paint from server-rendered status
    var initial = root.getAttribute("data-video-status") || "none";
    if (initial === "requested" || initial === "live") {
      setUi("wait", "The owner asked for a live video check before granting access.");
    }
  }

  global.VaultSendVideo = { admin: admin, guest: guest };
})(window);
