/** Shared lightweight Markdown → HTML (tables, lists, headings, inline). */
(function (root) {
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function inline(s) {
    var t = esc(s);
    t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" rel="noopener" target="_blank">$1</a>');
    return t;
  }

  function isTableRow(ln) {
    var t = String(ln || "").trim();
    return t.indexOf("|") !== -1 && t.length > 0;
  }

  function isSepRow(ln) {
    var t = String(ln || "").trim();
    return t.indexOf("|") !== -1 && t.indexOf("-") !== -1 && /^[\s|:\-]+$/.test(t);
  }

  function cells(ln) {
    return String(ln)
      .replace(/^\s*\|/, "")
      .replace(/\|\s*$/, "")
      .split("|")
      .map(function (c) { return c.trim(); });
  }

  function mdTable(rows) {
    if (!rows || rows.length < 1) return "";
    var head = cells(rows[0]);
    var start = rows.length > 1 && isSepRow(rows[1]) ? 2 : 1;
    var out = '<div class="md-table-wrap"><table class="md-table"><thead><tr>' +
      head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") +
      "</tr></thead><tbody>";
    for (var i = start; i < rows.length; i++) {
      if (isSepRow(rows[i])) continue;
      var cols = cells(rows[i]);
      out += "<tr>" + cols.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>";
    }
    return out + "</tbody></table></div>";
  }

  function render(raw) {
    var text = String(raw || "").replace(/\r\n/g, "\n");
    var lines = text.split("\n");
    var html = [];
    var i = 0;

    while (i < lines.length) {
      var ln = lines[i];
      if (!String(ln).trim()) {
        i++;
        continue;
      }

      if (/^```/.test(ln)) {
        var code = [];
        i++;
        while (i < lines.length && !/^```/.test(lines[i])) {
          code.push(lines[i]);
          i++;
        }
        if (i < lines.length) i++;
        html.push("<pre><code>" + esc(code.join("\n")) + "</code></pre>");
        continue;
      }

      if (isTableRow(ln) && i + 1 < lines.length && (isSepRow(lines[i + 1]) || isTableRow(lines[i + 1]))) {
        var rows = [];
        while (i < lines.length && isTableRow(lines[i])) {
          rows.push(lines[i]);
          i++;
        }
        html.push(mdTable(rows));
        continue;
      }

      var hm = /^(#{1,3})\s+(.+)$/.exec(ln);
      if (hm) {
        var level = Math.min(3, hm[1].length);
        html.push("<h" + level + ">" + inline(hm[2]) + "</h" + level + ">");
        i++;
        continue;
      }

      if (/^\s*[-*]\s+/.test(ln) || /^\s*\d+\.\s+/.test(ln)) {
        var ol = /^\s*\d+\./.test(ln);
        var items = [];
        while (i < lines.length && (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]))) {
          items.push("<li>" + inline(lines[i].replace(/^\s*(?:[-*]|\d+\.)\s+/, "")) + "</li>");
          i++;
        }
        html.push((ol ? "<ol>" : "<ul>") + items.join("") + (ol ? "</ol>" : "</ul>"));
        continue;
      }

      var para = [];
      while (i < lines.length) {
        var cur = lines[i];
        if (!String(cur).trim()) break;
        if (/^```/.test(cur) || /^(#{1,3})\s+/.test(cur)) break;
        if (isTableRow(cur) && i + 1 < lines.length && (isSepRow(lines[i + 1]) || isTableRow(lines[i + 1]))) break;
        if (/^\s*[-*]\s+/.test(cur) || /^\s*\d+\.\s+/.test(cur)) break;
        para.push(cur);
        i++;
      }
      if (para.length) {
        html.push("<p>" + para.map(inline).join("<br>") + "</p>");
      }
    }

    return html.join("") || "<p></p>";
  }

  root.VaultMd = { render: render, esc: esc, inline: inline };
})(typeof window !== "undefined" ? window : typeof globalThis !== "undefined" ? globalThis : this);
