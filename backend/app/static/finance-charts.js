/* Money Manager Charts — SVG spark, daily flow, donut. Data from #fn-charts-data. */
(function () {
  var el = document.getElementById("fn-charts-data");
  if (!el) return;
  var data;
  try { data = JSON.parse(el.textContent || "{}"); } catch (e) { return; }
  var daily = data.daily || [];
  var cats = (data.categories || []).filter(function (c) { return (c.amount || 0) > 0; });
  var NS = "http://www.w3.org/2000/svg";

  function areaPath(svg, values, w, h, color) {
    var n = values.length;
    if (!n) return;
    var max = 0;
    values.forEach(function (v) { if (v > max) max = v; });
    max = max || 1;
    var pad = 8;
    var step = n > 1 ? (w - pad * 2) / (n - 1) : 0;
    var pts = values.map(function (v, i) {
      return [pad + i * step, h - pad - (v / max) * (h - pad * 2)];
    });
    var d = "M " + pad + " " + (h - pad);
    pts.forEach(function (p) { d += " L " + p[0] + " " + p[1]; });
    d += " L " + (pad + (n - 1) * step) + " " + (h - pad) + " Z";
    var defs = document.createElementNS(NS, "defs");
    var id = "g-" + color.replace("#", "") + "-" + Math.round(Math.random() * 999);
    defs.innerHTML = '<linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.45"/>' +
      '<stop offset="100%" stop-color="' + color + '" stop-opacity="0"/></linearGradient>';
    svg.appendChild(defs);
    var area = document.createElementNS(NS, "path");
    area.setAttribute("d", d);
    area.setAttribute("fill", "url(#" + id + ")");
    svg.appendChild(area);
    var line = document.createElementNS(NS, "polyline");
    line.setAttribute("points", pts.map(function (p) { return p.join(","); }).join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "2.4");
    line.setAttribute("stroke-linecap", "round");
    line.setAttribute("stroke-linejoin", "round");
    svg.appendChild(line);
  }

  var spark = document.getElementById("mmx-spark");
  if (spark) {
    areaPath(spark, daily.map(function (d) { return d.expense || 0; }), 800, 230, "#ff6f6f");
  }
  var flow = document.getElementById("mmx-flow");
  if (flow) {
    areaPath(flow, daily.map(function (d) { return d.expense || 0; }), 900, 210, "#ff6f6f");
    var inc = daily.map(function (d) { return d.income || 0; });
    if (inc.some(function (v) { return v > 0; })) {
      var n = inc.length, w = 900, h = 210, pad = 8, max = 1;
      daily.forEach(function (d) {
        max = Math.max(max, d.expense || 0, d.income || 0);
      });
      var step = n > 1 ? (w - pad * 2) / (n - 1) : 0;
      var pts = inc.map(function (v, i) {
        return [pad + i * step, h - pad - (v / max) * (h - pad * 2)].join(",");
      });
      var line = document.createElementNS(NS, "polyline");
      line.setAttribute("points", pts.join(" "));
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", "#35d68a");
      line.setAttribute("stroke-width", "2");
      line.setAttribute("stroke-linecap", "round");
      flow.appendChild(line);
    }
  }

  var donut = document.getElementById("mmx-donut");
  if (donut && cats.length) {
    var r = 46, cx = 60, cy = 60, circ = 2 * Math.PI * r, offset = 0;
    var bg = document.createElementNS(NS, "circle");
    bg.setAttribute("cx", cx); bg.setAttribute("cy", cy); bg.setAttribute("r", r);
    bg.setAttribute("fill", "none");
    bg.setAttribute("stroke", "rgba(255,255,255,0.05)");
    bg.setAttribute("stroke-width", "14");
    donut.appendChild(bg);
    cats.forEach(function (c) {
      var len = ((c.pct || 0) / 100) * circ;
      var seg = document.createElementNS(NS, "circle");
      seg.setAttribute("cx", cx); seg.setAttribute("cy", cy); seg.setAttribute("r", r);
      seg.setAttribute("fill", "none");
      seg.setAttribute("stroke", c.color || "#8b8cf9");
      seg.setAttribute("stroke-width", "14");
      seg.setAttribute("stroke-dasharray", len + " " + (circ - len));
      seg.setAttribute("stroke-dashoffset", String(-offset));
      seg.setAttribute("transform", "rotate(-90 " + cx + " " + cy + ")");
      donut.appendChild(seg);
      offset += len;
    });
  }
})();
