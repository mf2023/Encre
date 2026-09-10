from __future__ import annotations

"""
鏁村悎鍒嗛暅鎷嗚В鏁版嵁鍜岄挬瀛愬垎鏋愮粨鏋滐紝鐢熸垚 Markdown 瑙嗛鍒嗘瀽鎶ュ憡銆?

Usage:
    python scripts/generate_report.py <breakdown_json> [hook_analysis_json]

Examples:
    python scripts/generate_report.py breakdown.json hook_analysis.json
    python scripts/generate_report.py breakdown.json
    python scripts/generate_report.py breakdown.json hook.json > report.md
"""

import json
import sys
from datetime import datetime


def generate_video_report(breakdown_data: dict, hook_analysis: dict = None) -> str:
    """
    鏁村悎鍒嗛暅鎷嗚В缁撴灉鍜岄挬瀛愬垎鏋愮粨鏋滐紝鐢熸垚 Markdown 瑙嗛鍒嗘瀽鎶ュ憡銆?

    Args:
        breakdown_data: 鍒嗛暅鎷嗚В鐨勫畬鏁寸粨鏋滄暟鎹?
        hook_analysis: 鍓嶄笁绉掗挬瀛愬垎鏋愮粨鏋滐紙鍙夛級

    Returns:
        str: Markdown 鏍煎紡鎶ュ憡
    """
    if hook_analysis is None:
        hook_analysis = {}

    duration = breakdown_data.get("duration", 0)
    segment_count = breakdown_data.get("segment_count", 0)
    resolution = breakdown_data.get("resolution", "N/A")
    bgm = breakdown_data.get("bgm_analysis") or {}
    scene = breakdown_data.get("scene_analysis") or {}

    #  BGM info

    music_style = bgm.get("music_style", {}).get("primary", "N/A") if bgm else "N/A"
    emotion = bgm.get("emotion", {}).get("primary", "N/A") if bgm else "N/A"
    tempo = bgm.get("tempo", {}).get("bpm_estimate", "N/A") if bgm else "N/A"
    tempo_pace = bgm.get("tempo", {}).get("pace", "N/A") if bgm else "N/A"

    # 
    primary_scene = scene.get("primary_scene", "N/A") if scene else "N/A"
    video_style = scene.get("video_style", {}).get("overall", "N/A") if scene else "N/A"
    target_audience = (
        ", ".join(scene.get("video_style", {}).get("target_audience", []))
        if scene
        else "N/A"
    )

    hook_section = _build_hook_section(hook_analysis)
    platform_section = _build_platform_section(scene)
    segments_section = _build_segments_overview(breakdown_data.get("segments", []))

    report = f"""# 瑙嗛鍒嗘瀽鎶ュ憡

# #
- **瑙嗛鏃堕暱**: {duration:.1f}绉?
- **鍒嗛暅鏁伴噺**: {segment_count}涓?
- **鍒嗚鲸鐜?*: {resolution}

---

{hook_section}

---

# #

{segments_section}

---

# # BGM
- **闊充箰椋庢牸**: {music_style}
- **鎯呯华鍩鸿皟**: {emotion}
- **鑺傛媿**: {tempo} BPM（{tempo_pace}鑺傚锛?

---

# #
- **涓昏鍦烘櫙**: {primary_scene}
- **瑙嗛椋庢牸**: {video_style}
- **鐩爣鍙椾紬**: {target_audience}

{platform_section}

---

**鎶ュ憡鐢熸垚鏃堕棿**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
    return report


def _build_hook_section(hook_analysis: dict) -> str:
    if not hook_analysis:
        return "## 鍓嶄笁绉掗挬瀛愬垎鏋怽n\n鏆傛棤閽╁瓙鍒嗘瀽鏁版嵁銆?"

    overall = hook_analysis.get("overall_score", 0)
    hook_type = hook_analysis.get("hook_type", "N/A")
    retention = hook_analysis.get("retention_prediction", "N/A")

    scores_table = f"""| 缁村害 | 寰楀垎 | 璇勪环 |
|------|------|------|
| 瑙嗚鍐插嚮鍔?| {hook_analysis.get("visual_impact", 0)}/10 | {hook_analysis.get("visual_comment", "")} |
| 璇█閽╁瓙 | {hook_analysis.get("language_hook", 0)}/10 | {hook_analysis.get("language_comment", "")} |
| 鎯呯华鍞よ捣 | {hook_analysis.get("emotion_trigger", 0)}/10 | {hook_analysis.get("emotion_comment", "")} |
| 淇伅瀵嗗害 | {hook_analysis.get("information_density", 0)}/10 | {hook_analysis.get("info_comment", "")} |
| 鑺傚鎺屾帶 | {hook_analysis.get("rhythm_control", 0)}/10 | {hook_analysis.get("rhythm_comment", "")} |"""

    strengths = hook_analysis.get("strengths", [])
    weaknesses = hook_analysis.get("weaknesses", [])
    suggestions = hook_analysis.get("suggestions", [])

    strengths_text = "\n".join(f"- {s}" for s in strengths) if strengths else "- 鏆傛棤"
    weaknesses_text = (
        "\n".join(f"- {w}" for w in weaknesses) if weaknesses else "- 鏆傛棤"
    )
    suggestions_text = (
        "\n".join(f"{i + 1}. {s}" for i, s in enumerate(suggestions))
        if suggestions
        else "1. 鏆傛棤"
    )

    return f"""## 鍓嶄笁绉掗挬瀛愬垎鏋愶紙鏍稿績锛?

# ## : {overall}/10

{scores_table}

# ##
**{hook_type}**

# ##
{strengths_text}

# ##
{weaknesses_text}

# ##
{suggestions_text}

# ##
**{retention}**"""


def _build_platform_section(scene: dict) -> str:
    if not scene:
        return ""
    recommendations = scene.get("platform_recommendations", [])
    if not recommendations:
        return ""
    lines = ["### 骞冲彴鎺ㄨ崘"]
    for rec in recommendations:
        platform = rec.get("platform", "N/A")
        suitability = rec.get("suitability", "N/A")
        reason = rec.get("reason", "")
        lines.append(f"- **{platform}**锛堥傚悎搴? {suitability}锛? {reason}")
    return "\n".join(lines)


def _build_segments_overview(segments: list) -> str:
    if not segments:
        return "鏆傛棤鍒嗛暅鏁版嵁銆?"

    lines = [
        "| 闀滃彿 | 鏃堕棿 | 鏅埆 | 杩愰暅 | 鍔熻兘鏍囩 | 鐢婚潰鍐呭 |",
        "|------|------|------|------|----------|----------|",
    ]

    for seg in segments[:10]:
        index = seg.get("segment_index", "-")
        start = seg.get("start_time", 0)
        end = seg.get("end_time", 0)
        time_range = f"{start:.1f}s-{end:.1f}s"
        shot_type = seg.get("shot_type", "-")
        camera = seg.get("camera_movement", "-")
        func_tag = seg.get("function_tag", "-")
        visual = seg.get("visual_content", "-")
        if len(visual) > 40:
            visual = visual[:37] + "..."
        lines.append(
            f"| {index} | {time_range} | {shot_type} | {camera} | {func_tag} | {visual} |"
        )

    if len(segments) > 10:
        lines.append(f"\n*(showing first 10 of {len(segments)} segments only)*")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_report.py <breakdown_json> [hook_analysis_json]")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        bd_data = json.load(f)

    hook_data = None
    if len(sys.argv) > 2:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            hook_data = json.load(f)

    report = generate_video_report(bd_data, hook_data)
    print(report)
