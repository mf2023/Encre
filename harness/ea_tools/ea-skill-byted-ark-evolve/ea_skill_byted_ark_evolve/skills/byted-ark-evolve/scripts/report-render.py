from __future__ import annotations

"""
Render evolution report HTML from JSON data.

The Agent fills a JSON file (pure data, no logic).
This script handles all conditional rendering.

Usage:
  python report-render.py report-data.json
  python report-render.py report-data.json --output report.html
  cat report-data.json | python report-render.py -

JSON schema: see references/report-schema-example.json
"""

import json
import os
import sys
from datetime import datetime

for stream in [sys.stdout, sys.stderr, sys.stdin]:
    if stream and hasattr(stream, "reconfigure") and stream.encoding != "utf-8":
        stream.reconfigure(encoding="utf-8")


LAYER_CN = {
    "identity": "韬唤",
    "context": "涓婁笅鏂?",
    "protocol": "鍗忚",
    "capability": "鑳藉姏",
    "runtime": "杩愯鏃?",
}
LAYER_CSS = {
    "identity": ("badge-identity", "#faf5ff", "#7c3aed", "#ddd6fe"),
    "context": ("badge-context", "#fffbeb", "#d97706", "#fde68a"),
    "protocol": ("badge-protocol", "#eff6ff", "#2563eb", "#bfdbfe"),
    "capability": ("badge-capability", "#f0fdf4", "#16a34a", "#bbf7d0"),
    "runtime": ("badge-runtime", "#f3f4f6", "#6b7280", "#e5e7eb"),
}
STATUS_CN = {
    "applied": "宸茬敓鏁?",
    "approved": "宸叉壒鍑?",
    "proposed": "寰呭鏍?",
    "rejected": "宸叉嫆缁?",
    "verified": "宸查獙璇?",
    "pending": "寰呴獙璇?",
    "observed": "宸茶瀵?",
    "regression": "宸插鍙?",
    "partial": "閮ㄥ垎鐢熸晥",
}
STATUS_COLOR = {
    "applied": "#16a34a",
    "approved": "#2563eb",
    "proposed": "#6b7280",
    "rejected": "#dc2626",
    "verified": "#16a34a",
    "pending": "#d97706",
    "observed": "#2563eb",
    "regression": "#dc2626",
    "partial": "#d97706",
}
SIGNAL_TYPE_CN = {
    "correction": "绾犳",
    "negative": "璐熼潰",
    "positive": "姝ｉ潰",
    "suggestion": "寤鸿",
}


def esc(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def badge(layer):
    cn = LAYER_CN.get(layer, layer or "")
    _, bg, fg, border = LAYER_CSS.get(layer, ("", "#f3f4f6", "#6b7280", "#e5e7eb"))
    return f'<span style="display:inline-block;font-size:11px;font-weight:600;padding:1px 6px;border-radius:3px;background:{bg};color:{fg};border:1px solid {border}">{esc(cn)}</span>'


def render(data):
    d = data
    date = d.get("date", datetime.now().strftime("%Y-%m-%d"))
    stats = d.get("stats", {})
    signals = stats.get("signals", 0)
    changes_count = stats.get("changes", 0)
    rejected = stats.get("rejected", 0)
    summary = d.get("summary", "")
    changes = d.get("changes", [])
    signals_by_layer = d.get("signals_by_layer", {})
    high_signals = d.get("high_severity_signals", [])
    all_signals = d.get("all_signals", [])
    traj = d.get("trajectory", {})
    sat = d.get("saturation", {})
    cost = d.get("cost", {})
    user_direct = d.get("user_direct_changes", 0)
    next_steps = d.get("next_steps", [])

    h = []

    # === HEAD ===
    h.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>杩涘寲鎶ュ憡 鈥?{date}</title>
<style>
:root {{
  --bg:#fafafa;--surface:#fff;--border:#e5e7eb;--text:#1f2937;--muted:#6b7280;
  --accent:#2563eb;--green:#16a34a;--red:#dc2626;--amber:#d97706;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);line-height:1.75;max-width:720px;margin:0 auto;padding:40px 24px 80px;font-size:16px}}
h1{{font-size:24px;font-weight:700;margin-bottom:4px}}
h2{{font-size:18px;font-weight:700;margin:24px 0 10px}}
p{{margin-bottom:10px}}
hr{{border:none;border-top:1px solid var(--border);margin:28px 0}}
code{{font-family:'SF Mono',monospace;font-size:13px;background:#f3f4f6;padding:1px 4px;border-radius:2px}}
details{{margin-bottom:10px}}
summary{{cursor:pointer;font-weight:600;font-size:14px;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:14px;margin-bottom:10px}}
th{{text-align:left;font-weight:600;padding:6px 8px;border-bottom:2px solid var(--text);font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}}
td{{padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:top}}
.meta{{color:var(--muted);font-size:14px;margin-bottom:24px}}
.stat-row{{display:flex;gap:10px;margin-bottom:20px}}
.stat-pill{{display:flex;align-items:baseline;gap:6px;padding:8px 14px;border-radius:6px;background:var(--surface);border:1px solid var(--border)}}
.stat-pill .num{{font-size:20px;font-weight:700}}
.stat-pill .label{{font-size:12px;color:var(--muted)}}
.change-item{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px 16px;margin-bottom:10px}}
.change-item .file-tag{{font-size:12px;font-weight:600;color:var(--accent);margin-bottom:2px}}
.change-item .desc{{font-size:15px;font-weight:600;margin-bottom:4px}}
.change-item .reason{{font-size:13px;color:var(--muted)}}
.anchor{{text-align:center;font-size:12px;color:var(--muted);padding:8px 0;margin:16px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}}
.ba-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}}
.ba-box{{padding:8px 10px;border-radius:4px;font-size:13px}}
.ba-before{{background:#fef2f2;border:1px solid #fecaca}}
.ba-after{{background:#f0fdf4;border:1px solid #bbf7d0}}
.ba-label{{font-size:11px;font-weight:600;margin-bottom:2px}}
.action-box{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:14px 16px}}
.action-box .action-title{{font-size:13px;font-weight:600;color:var(--accent);margin-bottom:6px}}
.action-box li{{font-size:13px;margin-bottom:4px}}
.bar-row{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
.bar-label{{font-size:13px;width:50px;text-align:right}}
.bar{{height:18px;border-radius:3px;min-width:4px}}
.bar-count{{font-size:13px;color:var(--muted)}}
.info-pair{{display:flex;gap:12px;margin-top:16px}}
.info-card{{flex:1;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px 14px;font-size:13px}}
.info-card .title{{font-weight:600;margin-bottom:4px}}
</style>
</head>
<body>
""")

    # === GLOSSARY ===
    h.append("""
<details style="margin-bottom:16px;background:#f8f9fa;border:1px solid var(--border);border-radius:6px;padding:10px 14px">
  <summary style="font-size:13px;cursor:pointer">馃摉 鏈閫熸煡锛堥娆￠槄璇诲缓璁睍寮锛?/summary>
  <table style="margin-top:8px;font-size:12px">
    <tbody>
      <tr><td style="font-weight:600;width:80px">鍙嶉</td><td>浣犳棩甯哥籂姝ｃ佸缓璁腑璇嗗埆鍑虹殑鏀硅繘绾跨储</td></tr>
      <tr><td style="font-weight:600">鍙樻洿</td><td>鍩轰簬鍙嶉璁捐鐨勫叿浣撴枃浠舵敼鍔?/td></tr>
      <tr><td style="font-weight:600">鍗忚灞?/td><td>Agent 鐨勮涓鸿鍒欏拰鍐崇瓥娴佺▼</td></tr>
      <tr><td style="font-weight:600">鑳藉姏灞?/td><td>Agent 鐨勬妧鑳藉拰鏂规硶璁?/td></tr>
      <tr><td style="font-weight:600">甯曠疮鎵樻鏌?/td><td>纭鏀瑰姩涓嶄細璁╁叾浠栨柟闈㈠彉宸?/td></tr>
      <tr><td style="font-weight:600">楗卞拰</td><td>杩炵画澶氭杩涘寲浜у嚭鏋佸皯鏂版柟妗堬紝褰撳墠鏂瑰悜宸插厖鍒嗕紭鍖?/td></tr>
      <tr><td style="font-weight:600">杞ㄨ抗</td><td>Golden = 鍋氬浜嗙殑璁板綍锛汣orrection = 鍋氶敊鍚庝慨姝ｇ殑璁板綍</td></tr>
    </tbody>
  </table>
</details>
""")

    # === HERO ===
    h.append(f'<h1>杩涘寲鎶ュ憡</h1>\n<div class="meta">{esc(date)}</div>\n')
    if summary:
        h.append(
            f'<p style="font-size:15px;line-height:1.6;margin-bottom:16px">{esc(summary)}</p>\n'
        )

    # Stats: 3 pills (if rejected > 0, show rejected; otherwise show 0 in green)
    h.append('<div class="stat-row">\n')
    h.append(
        f'  <div class="stat-pill"><span class="num">{signals}</span><span class="label">鏉弽棣?/span></div>\n'
    )
    h.append(
        f'  <div class="stat-pill"><span class="num">{changes_count}</span><span class="label">鏉彉鏇?/span></div>\n'
    )
    if rejected > 0:
        h.append(
            f'  <div class="stat-pill"><span class="num" style="color:var(--red)">{rejected}</span><span class="label">鏉嫆缁?/span></div>\n'
        )
    else:
        h.append(
            '  <div class="stat-pill"><span class="num" style="color:var(--green)">0</span><span class="label">鏉嫆缁?/span></div>\n'
        )
    h.append("</div>\n")

    # === CHANGES ===
    if changes:
        h.append("<h2>鍙樻洿娓呭崟</h2>\n")
        for c in changes:
            status = c.get("status", "applied")
            dot_color = STATUS_COLOR.get(status, "#16a34a")
            h.append('<div class="change-item">\n')
            h.append(
                f'  <div class="file-tag"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{dot_color};margin-right:4px;vertical-align:middle"></span>{esc(c.get("file", ""))}</div>\n'
            )
            h.append(f'  <div class="desc">{esc(c.get("description", ""))}</div>\n')
            if c.get("reason"):
                h.append(f'  <div class="reason">鍘熷洜锛{esc(c["reason"])}</div>\n')
            # Folded diff
            before = c.get("before")
            after = c.get("after")
            if before or after:
                h.append(
                    '  <details style="margin-top:6px"><summary>鏌ョ湅鍏蜂綋鍙樻洿</summary>\n'
                )
                h.append('    <div class="ba-grid">\n')
                h.append(
                    f'      <div class="ba-box ba-before"><div class="ba-label" style="color:var(--red)">Before</div>{esc(before or "(none)")}</div>\n'
                )
                h.append(
                    f'      <div class="ba-box ba-after"><div class="ba-label" style="color:var(--green)">After</div>{esc(after or "(none)")}</div>\n'
                )
                h.append("    </div>\n  </details>\n")
            h.append("</div>\n")

        # Rejected changes (only if any)
        rejected_changes = [c for c in changes if c.get("status") == "rejected"]
        if rejected_changes:
            h.append('<h2 style="color:var(--red)">琚嫆缁濈殑鍙樻洿</h2>\n')
            for c in rejected_changes:
                h.append('<div class="change-item" style="border-color:#fecaca">\n')
                h.append(
                    f'  <div class="file-tag" style="color:var(--red)">{esc(c.get("file", ""))}</div>\n'
                )
                h.append(f'  <div class="desc">{esc(c.get("description", ""))}</div>\n')
                if c.get("reject_reason"):
                    h.append(
                        f'  <div class="reason">鎷掔粷鍘熷洜锛{esc(c["reject_reason"])}</div>\n'
                    )
                h.append("</div>\n")

        h.append(
            f'<div class="anchor">{len(changes)} changes written' + (f" ({rejected} rejected)" if rejected > 0 else "") + '</div>\n'
        )
    else:
        h.append(
            '<h2>鍙樻洿娓呭崟</h2>\n<p style="color:var(--muted)">鏈鍒嗘瀽鏈骇鐢熷彉鏇存柟妗堛?/p>\n'
        )

    # === SIGNAL SOURCE ===
    if signals_by_layer:
        h.append("<h2>鍙嶉鏉ユ簮</h2>\n")
        max_count = max(signals_by_layer.values()) if signals_by_layer else 1
        bar_colors = {
            "protocol": "#2563eb",
            "capability": "#16a34a",
            "identity": "#7c3aed",
            "context": "#d97706",
            "runtime": "#6b7280",
        }
        for layer, cnt in sorted(signals_by_layer.items(), key=lambda x: -x[1]):
            w = max(int(cnt / max_count * 160), 8)
            color = bar_colors.get(layer, "#6b7280")
            h.append(
                f'<div class="bar-row"><div class="bar-label">{badge(layer)}</div><div class="bar" style="width:{w}px;background:{color}"></div><div class="bar-count">{cnt}</div></div>\n'
            )

    # High severity (only if any)
    if high_signals:
        h.append(
            '<p style="font-size:13px;color:var(--muted);margin-top:10px;margin-bottom:4px">楂樹紭鍏堢骇鍙嶉锛?/p>\n'
        )
        for sig in high_signals:
            h.append(
                f'<div style="font-size:13px;color:var(--red);font-style:italic;padding:6px 12px;border-left:3px solid var(--red);margin-bottom:6px">&ldquo;{esc(sig.get("text", ""))}&rdquo;</div>\n'
            )

    # All signals (folded)
    if all_signals:
        h.append(
            f'<details style="margin-top:8px"><summary>鏌ョ湅鍏ㄩ儴 {len(all_signals)} 鏉弽棣?/summary>\n'
        )
        h.append(
            '<table style="margin-top:8px"><thead><tr><th>鍙嶉</th><th>绫诲瀷</th></tr></thead><tbody>\n'
        )
        for sig in all_signals:
            stype = SIGNAL_TYPE_CN.get(sig.get("type", ""), sig.get("type", ""))
            h.append(
                f"<tr><td>{esc(sig.get('text', ''))}</td><td>{esc(stype)}</td></tr>\n"
            )
        h.append("</tbody></table></details>\n")

    if signals_by_layer or high_signals or all_signals:
        h.append('<div class="anchor">浠ヤ笂鏄湰娆垎鏋愮殑鍙嶉鏉ユ簮</div>\n')

    # === NEXT STEPS ===
    if next_steps:
        h.append(
            '<h2>涓嬩竴姝?/h2>\n<div class="action-box">\n<div class="action-title">楠岃瘉璁垝</div>\n<ul style="padding-left:18px">\n'
        )
        for step in next_steps:
            h.append(f"  <li>{esc(step)}</li>\n")
        h.append("</ul>\n</div>\n")

    # === TRAJECTORY + SATURATION ===
    golden = traj.get("golden", 0)
    correction = traj.get("correction", 0)
    has_traj = golden > 0 or correction > 0
    has_sat = "is_saturated" in sat

    if has_traj or has_sat:
        h.append('<div class="info-pair">\n')
        if has_traj:
            h.append(
                f'<div class="info-card"><div class="title">杞ㄨ抗搴?/div>{golden} golden / {correction} correction</div>\n'
            )
        if has_sat:
            if sat.get("is_saturated"):
                sat_text = '<span style="color:var(--amber)">瓒嬩簬楗卞拰</span>'
            else:
                added = sat.get("added", 0)
                modified = sat.get("modified", 0)
                sat_text = f'<span style="color:var(--green)">鏈ケ鍜?/span> 路 {added} 鏂板 / {modified} 淇敼'
            h.append(
                f'<div class="info-card"><div class="title">楗卞拰璇勪及</div>{sat_text}</div>\n'
            )
        h.append("</div>\n")

    # Cost (compact line)
    analysis_cost = cost.get("analysis_cost", 0)
    roi = cost.get("roi_percent", 0)
    cost_parts = []
    if analysis_cost > 0:
        cost_parts.append(f"鍒嗘瀽鎴愭湰 ~${analysis_cost:.1f}")
    if roi > 0:
        cost_parts.append(f"ROI {roi}%")
    if user_direct > 0:
        cost_parts.append(f"User-direct changes: {user_direct}")
    if cost_parts:
        h.append(
            f'<div style="margin-top:10px;font-size:12px;color:var(--muted);text-align:right">{" 路 ".join(cost_parts)}</div>\n'
        )

    # === FOOTER ===
    h.append(f"""
<hr>
<p style="color:var(--muted);font-size:12px;text-align:center">
  Evolution Skill v0.1.2 鈥?{esc(date)}
</p>
</body>
</html>
""")
    return "".join(h)


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: python report-render.py <json-file> [--output <html-file>]",
            file=sys.stderr,
        )
        sys.exit(1)

    json_path = sys.argv[1]
    if json_path == "-":
        data = json.load(sys.stdin)
    else:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    html = render(data)

    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(json.dumps({"status": "ok", "path": output_path}, ensure_ascii=False))
    else:
        print(html)


if __name__ == "__main__":
    main()
