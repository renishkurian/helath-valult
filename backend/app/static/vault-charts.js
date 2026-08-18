/* Compact canvas charts for Money Manager — no CDN. */
(function (global) {
  function css(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v && v.trim()) || fallback;
  }
  function size(canvas) {
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    var cssW = Math.max(120, rect.width || canvas.clientWidth || 300);
    var cssH = Math.max(140, parseFloat(getComputedStyle(canvas).height) || 220);
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx: ctx, w: cssW, h: cssH };
  }
  function maxOf(vals) {
    var m = 0;
    for (var i = 0; i < vals.length; i++) m = Math.max(m, vals[i] || 0);
    return m || 1;
  }
  function niceMax(n) {
    if (n <= 0) return 1;
    var exp = Math.pow(10, Math.floor(Math.log10(n)));
    var m = n / exp;
    var nice = m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10;
    return nice * exp;
  }
  function roundRect(ctx, x, y, w, h, r) {
    var rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
  }
  function axis(ctx, pad, w, h, ink) {
    ctx.strokeStyle = ink;
    ctx.globalAlpha = 0.18;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.l, pad.t);
    ctx.lineTo(pad.l, h - pad.b);
    ctx.lineTo(w - pad.r, h - pad.b);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  function labelsX(ctx, labels, pad, w, h, ink, band) {
    ctx.fillStyle = ink;
    ctx.globalAlpha = 0.7;
    ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    var inner = w - pad.l - pad.r;
    var n = labels.length || 1;
    var skip = Math.max(1, Math.ceil(n / 10));
    for (var i = 0; i < labels.length; i++) {
      if (i % skip && i !== labels.length - 1 && i !== 0) continue;
      var x = band || n <= 1
        ? pad.l + (inner * (i + 0.5)) / n
        : pad.l + (inner * i) / (n - 1);
      ctx.fillText(String(labels[i]), x, h - pad.b + 6);
    }
    ctx.globalAlpha = 1;
  }

  function line(canvas, opt) {
    var s = size(canvas);
    var ctx = s.ctx, w = s.w, h = s.h;
    var pad = { t: 16, r: 12, b: 28, l: 8 };
    var labels = opt.labels || [];
    var series = opt.series || [];
    var ink = css("--v-ink-3", "#9AA2B4");
    ctx.clearRect(0, 0, w, h);
    var all = [];
    series.forEach(function (ser) { (ser.values || []).forEach(function (v) { all.push(v || 0); }); });
    var top = niceMax(maxOf(all));
    axis(ctx, pad, w, h, ink);
    var innerW = w - pad.l - pad.r;
    var innerH = h - pad.t - pad.b;
    var n = labels.length;
    function xAt(i) {
      if (n <= 1) return pad.l + innerW / 2;
      return pad.l + (innerW * i) / (n - 1);
    }
    function yAt(v) { return pad.t + innerH * (1 - (v || 0) / top); }
    series.forEach(function (ser) {
      var vals = ser.values || [];
      ctx.beginPath();
      for (var i = 0; i < n; i++) {
        var x = xAt(i), y = yAt(vals[i] || 0);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      if (ser.fill) {
        ctx.lineTo(xAt(n - 1), pad.t + innerH);
        ctx.lineTo(xAt(0), pad.t + innerH);
        ctx.closePath();
        ctx.fillStyle = ser.fill;
        ctx.globalAlpha = 0.18;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.beginPath();
        for (i = 0; i < n; i++) {
          x = xAt(i); y = yAt(vals[i] || 0);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
      }
      ctx.strokeStyle = ser.color || "#3FE0C5";
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.stroke();
    });
    labelsX(ctx, labels, pad, w, h, ink, false);
  }

  function bars(canvas, opt) {
    var s = size(canvas);
    var ctx = s.ctx, w = s.w, h = s.h;
    var pad = { t: 12, r: 10, b: 28, l: 8 };
    var labels = opt.labels || [];
    var series = opt.series || [];
    var ink = css("--v-ink-3", "#9AA2B4");
    ctx.clearRect(0, 0, w, h);
    var all = [];
    series.forEach(function (ser) { (ser.values || []).forEach(function (v) { all.push(v || 0); }); });
    var top = niceMax(maxOf(all));
    axis(ctx, pad, w, h, ink);
    var n = labels.length || 1;
    var innerW = w - pad.l - pad.r;
    var innerH = h - pad.t - pad.b;
    var group = innerW / n;
    var gap = Math.min(8, group * 0.18);
    var sw = series.length || 1;
    var bw = Math.max(3, (group - gap * 2) / sw);
    series.forEach(function (ser, si) {
      ctx.fillStyle = ser.color || "#3FE0C5";
      (ser.values || []).forEach(function (v, i) {
        var bh = innerH * ((v || 0) / top);
        var x = pad.l + i * group + gap + si * bw;
        var y = pad.t + innerH - bh;
        roundRect(ctx, x, y, Math.max(2, bw - 2), Math.max(0, bh), 4);
        ctx.fill();
      });
    });
    labelsX(ctx, labels, pad, w, h, ink, true);
  }

  function histogram(canvas, opt) {
    bars(canvas, {
      labels: opt.labels || [],
      series: [{ color: opt.color || "#3FE0C5", values: opt.values || [] }]
    });
  }

  function donut(canvas, opt) {
    var s = size(canvas);
    var ctx = s.ctx, w = s.w, h = s.h;
    ctx.clearRect(0, 0, w, h);
    var rows = (opt.rows || []).filter(function (r) { return (r.amount || 0) > 0; });
    var cx = w / 2, cy = h / 2;
    var r = Math.min(w, h) * 0.38;
    var r0 = r * 0.58;
    var total = 0;
    rows.forEach(function (row) { total += row.amount || 0; });
    if (!total) {
      ctx.strokeStyle = css("--v-line", "rgba(255,255,255,.12)");
      ctx.lineWidth = 12;
      ctx.beginPath();
      ctx.arc(cx, cy, (r + r0) / 2, 0, Math.PI * 2);
      ctx.stroke();
      return;
    }
    var a = -Math.PI / 2;
    rows.forEach(function (row) {
      var slice = ((row.amount || 0) / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      ctx.arc(cx, cy, r, a, a + slice);
      ctx.arc(cx, cy, r0, a + slice, a, true);
      ctx.closePath();
      ctx.fillStyle = row.color || "#3FE0C5";
      ctx.fill();
      a += slice;
    });
  }

  global.VaultCharts = { line: line, bars: bars, histogram: histogram, donut: donut };
})(window);
