from __future__ import annotations

"""
浠庡垎闀滄媶瑙ｇ粨鏋滀腑鎻愬彇鍓嶄笁绉掑垎闀滄暟鎹紝鏋勯犻挬瀛愬垎鏋愪笂涓嬫枃銆?

Usage:
    python scripts/analyze_hook_segments.py <breakdown_json_file>
    cat breakdown.json | python scripts/analyze_hook_segments.py -

Examples:
    python scripts/analyze_hook_segments.py breakdown_result.json
    echo '{"segments":[...]}' | python scripts/analyze_hook_segments.py -
"""

import json
import sys


def analyze_hook_segments(breakdown_data: dict) -> dict:
    """
    鎻愬彇骞跺垎鏋愯棰戝墠涓夌鐨勫垎闀滄暟鎹紝涓洪挬瀛愬垎鏋愭彁渚涚粨鏋勫寲涓婁笅鏂囥?

    Args:
        breakdown_data: 瀹屾暣鐨勫垎闀滄媶瑙ｇ粨鏋滐紙鍖呭惈 segments 瀛楁锛?

    Returns:
        dict: 鍓嶄笁绉掑垎闀滅殑缁撴瀯鍖栧垎鏋愪笂涓嬫枃
    """
    segments = breakdown_data.get("segments", [])

    if not segments:
        return {
            "error": "娌湁鍒嗛暅鏁版嵁",
            "segment_count": 0,
            "total_duration": 0,
            "segments": [],
        }

    # 
    first_segments = []
    cumulative_time = 0

    for seg in segments:
        end_time = seg.get("end_time", 0)
        if cumulative_time >= 3.0 and first_segments:
            break
        first_segments.append(seg)
        cumulative_time = end_time

    # 锛堬級
    context = {
        "segment_count": len(first_segments),
        "total_duration": cumulative_time,
        "total_video_segments": len(segments),
        "analysis_mode": "multimodal",
        "segments": [],
    }

    # 
    for s in first_segments:
        frame_urls = s.get("frame_urls", [])

        segment_info = {
            "index": s.get("segment_index", 0),
            "start_time": s.get("start_time", 0),
            "end_time": s.get("end_time", 0),
            "duration": s.get("duration", 0),
            "visual_content": s.get("visual_content", ""),
            "speech_text": s.get("speech_text", ""),
            "shot_type": s.get("shot_type", ""),
            "camera_movement": s.get("camera_movement", ""),
            "function_tag": s.get("function_tag", ""),
            "headline": s.get("headline", ""),
            "content_tags": s.get("content_tags", []),
            "voice_type": s.get("voice_type", ""),
            "clip_url": s.get("clip_url", ""),
        }

        # 锛?vision 锛夛紝3
        if frame_urls:
            segment_info["frame_images"] = [
                {"type": "image_url", "image_url": {"url": url}}
                for url in frame_urls[:3]
            ]
            segment_info["frame_count"] = len(frame_urls)
        else:
            segment_info["frame_images"] = []
            segment_info["frame_count"] = 0

        context["segments"].append(segment_info)

    total_frames = sum(s.get("frame_count", 0) for s in context["segments"])
    print(
        f"First-three-seconds extraction done: {len(first_segments)} segments, "
        f"total {cumulative_time:.1f}s, {total_frames} key frames",
        file=sys.stderr,
    )

    return context


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_hook_segments.py <breakdown_json_file>")
        print("       cat breakdown.json | python analyze_hook_segments.py -")
        sys.exit(1)

    source = sys.argv[1]

    if source == "-":
        data = json.load(sys.stdin)
    else:
        with open(source, "r", encoding="utf-8") as f:
            data = json.load(f)

    result = analyze_hook_segments(data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
