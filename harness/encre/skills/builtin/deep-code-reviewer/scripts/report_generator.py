#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Report Generator
瀹℃煡鎶ュ憡鐢熸垚鍣?
"""

from typing import Dict, List


class ReportGenerator:
    """浠ｇ爜瀹℃煡鎶ュ憡鐢熸垚鍣?""

    def generate(self, parsed_code: Dict, security_issues: List[Dict],
                 performance_issues: List[Dict], semantic_issues: List[Dict]) -> Dict:
        """鐢熸垚瀹屾暣瀹℃煡鎶ュ憡"""

        all_issues = security_issues + performance_issues + semantic_issues

        # 锛堬級
        seen = set()
        unique_issues = []
        for issue in all_issues:
            key = (issue.get("line", 0), issue.get("rule", ""))
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        # 
        blocker = [i for i in unique_issues if i["severity"] == "闃绘柇"]
        critical = [i for i in unique_issues if i["severity"] == "涓ラ噸"]
        warning = [i for i in unique_issues if i["severity"] == "涓瓑"]
        minor = [i for i in unique_issues if i["severity"] == "杞诲井"]

        # 
        health_score = max(0, 100 - len(blocker) * 30 - len(critical) * 15 - len(warning) * 5 - len(minor) * 1)

        # 
        positive = self._generate_positive_feedback(parsed_code, unique_issues)

        report = {
            "status": "success",
            "summary": self._generate_summary(health_score, blocker, critical, warning, minor),
            "language": parsed_code.get("language", "unknown"),
            "metadata": parsed_code.get("metadata", {}),
            "health_score": round(health_score, 1),
            "health_level": self._health_level(health_score),
            "issue_summary": {
                "total": len(unique_issues),
                "blocker": len(blocker),
                "critical": len(critical),
                "warning": len(warning),
                "minor": len(minor)
            },
            "critical_issues": blocker + critical,
            "warnings": warning,
            "minor_issues": minor,
            "positive_findings": positive,
            "overall_suggestions": self._generate_overall_suggestions(health_score, blocker, critical, parsed_code),
            "next_actions": self._generate_next_actions(health_score, blocker, critical, warning)
        }

        return report

    def _generate_summary(self, health_score: float, blocker: List, critical: List,
                          warning: List, minor: List) -> str:
        """鐢熸垚鏍稿績缁撹"""
        total = len(blocker) + len(critical) + len(warning) + len(minor)

        if health_score >= 90:
            return f"浠ｇ爜璐ㄩ噺浼樼锛坽health_score}鍒嗭級锛屽叡鍙戠幇{total}涓棶棰橈紝浠ヨ交寰紭鍖栧缓璁负涓伙紝鍙畨鍏ㄥ悎骞躲€?
        elif health_score >= 75:
            return f"浠ｇ爜璐ㄩ噺鑹ソ锛坽health_score}鍒嗭級锛屽彂鐜皗len(critical)}涓弗閲嶉棶棰橈紝寤鸿淇鍚庡悎骞躲€?
        elif health_score >= 60:
            return f"浠ｇ爜璐ㄩ噺鍙婃牸锛坽health_score}鍒嗭級锛屽瓨鍦▄len(blocker)}涓樆鏂骇婕忔礊鍜寋len(critical)}涓弗閲嶉棶棰橈紝蹇呴』淇鍚庢墠鑳藉悎骞躲€?
        else:
            return f"浠ｇ爜璐ㄩ噺闇€閲嶆瀯锛坽health_score}鍒嗭級锛屽瓨鍦ㄤ弗閲嶅畨鍏ㄦ紡娲炲拰閫昏緫閿欒锛屼笉寤鸿鍚堝苟锛岄渶鍏ㄩ潰瀹℃煡銆?

    def _health_level(self, score: float) -> str:
        if score >= 90:
            return "浼樼"
        elif score >= 75:
            return "鑹ソ"
        elif score >= 60:
            return "鍙婃牸"
        else:
            return "闇€閲嶆瀯"

    def _generate_positive_feedback(self, parsed_code: Dict, issues: List[Dict]) -> List[str]:
        """鐢熸垚姝ｉ潰鍙嶉"""
        positive = []
        metadata = parsed_code.get("metadata", {})

        # 
        ratio = metadata.get("comment_ratio", 0)
        if ratio > 0.2:
            positive.append(f"娉ㄩ噴瑕嗙洊鐜囪揪{ratio:.0%}锛屼唬鐮佸彲璇绘€ц緝濂?)

        # 
        long_funcs = [i for i in issues if i["rule"] == "鍑芥暟杩囬暱"]
        if not long_funcs:
            positive.append("鍑芥暟闀垮害鎺у埗鑹ソ锛岃亴璐ｅ垝鍒嗘竻鏅?)

        # 
        security = [i for i in issues if i["severity"] in ["闃绘柇", "涓ラ噸"] and "娉ㄥ叆" in i["rule"]]
        if not security:
            positive.append("鏈彂鐜癝QL娉ㄥ叆銆乆SS绛夊父瑙佸畨鍏ㄦ紡娲?)

        # 
        unused = [i for i in issues if i["rule"] == "鏈娇鐢ㄧ殑瀵煎叆"]
        if len(unused) <= 1:
            positive.append("瀵煎叆绠＄悊瑙勮寖锛屼緷璧栧叧绯绘竻鏅?)

        # 
        if not positive:
            positive.append("浠ｇ爜缁撴瀯瀹屾暣锛屽姛鑳藉疄鐜版竻鏅?)

        return positive[:3]

    def _generate_overall_suggestions(self, health_score: float, blocker: List,
                                      critical: List, parsed_code: Dict) -> List[str]:
        """鐢熸垚鏁翠綋鏋舵瀯寤鸿"""
        suggestions = []

        if blocker:
            suggestions.append("**浼樺厛澶勭悊瀹夊叏婕忔礊**锛氬瓨鍦ㄩ樆鏂骇瀹夊叏闂锛屽繀椤荤珛鍗充慨澶嶏紝寤鸿寮曞叆瀹夊叏缂栫爜瑙勮寖锛堝OWASP Top 10妫€鏌ユ竻鍗曪級")

        if critical:
            suggestions.append("**鎬ц兘浼樺寲**锛氬瓨鍦ㄤ弗閲嶆€ц兘闄烽槺锛屽缓璁紩鍏ユ€ц兘娴嬭瘯锛堝鍘嬪姏娴嬭瘯銆佹參鏌ヨ鐩戞帶锛夊埌CI娴佺▼")

        if health_score < 75:
            suggestions.append("**浠ｇ爜閲嶆瀯**锛氭暣浣撹川閲忓亸浣庯紝寤鸿鍒嗛樁娈甸噸鏋勶細鍏堜慨澶嶅畨鍏ㄩ棶棰橈紝鍐嶄紭鍖栨€ц兘锛屾渶鍚庢竻鐞嗗彲璇绘€у€哄姟")

        # 
        loc = parsed_code.get("metadata", {}).get("lines_of_code", 0)
        if loc > 500:
            suggestions.append(f"**妯″潡鎷嗗垎**锛氫唬鐮侀噺杈冨ぇ锛坽loc}琛岋級锛屽缓璁寜鑱岃矗鎷嗗垎涓哄涓ā鍧?鏂囦欢锛岄檷浣庤€﹀悎搴?)

        # 
        lang = parsed_code.get("language", "")
        if lang == "python":
            suggestions.append("**绫诲瀷娉ㄨВ**锛氬缓璁€愭寮曞叆Python绫诲瀷娉ㄨВ锛坱yping锛夛紝鎻愬崌IDE鎻愮ず鍜岄潤鎬佹鏌ヨ兘鍔?)
        elif lang in ["javascript", "typescript"]:
            suggestions.append("**TypeScript杩佺Щ**锛氬涓篔S椤圭洰锛屽缓璁牳蹇冩ā鍧楅€愭杩佺Щ鍒癟S锛屾彁鍗囩被鍨嬪畨鍏?)

        if not suggestions:
            suggestions.append("**鎸佺画鏀硅繘**锛氬缓璁紩鍏ヨ嚜鍔ㄥ寲浠ｇ爜瀹℃煡宸ュ叿锛堝SonarQube銆丆odeClimate锛夊埌CI/CD娴佺▼锛屾寔缁洃鎺т唬鐮佽川閲?)

        return suggestions

    def _generate_next_actions(self, health_score: float, blocker: List,
                               critical: List, warning: List) -> List[str]:
        """鐢熸垚涓嬩竴姝ヨ鍔ㄥ缓璁?""
        actions = []

        if blocker:
            actions.append(f"1. **绔嬪嵆淇{len(blocker)}涓樆鏂骇瀹夊叏闂**锛堥璁?-2灏忔椂锛夛紝绂佹鍚堝苟")
        if critical:
            actions.append(f"2. **淇{len(critical)}涓弗閲嶉棶棰?*锛堥璁?-4灏忔椂锛夛紝淇鍚庨噸鏂板鏌?)
        if warning:
            actions.append(f"3. **澶勭悊{len(warning)}涓腑绛夐棶棰?*锛堥璁?-3灏忔椂锛夛紝鍙湪涓嬩釜杩唬瀹屾垚")

        if health_score >= 90:
            actions.append("浠ｇ爜璐ㄩ噺浼樼锛屽彲鐩存帴鍚堝苟锛屽缓璁悗缁叧娉ㄦ祴璇曡鐩栫巼")
        elif health_score >= 75:
            actions.append("淇涓ラ噸闂鍚庡彲鍚堝苟锛屽缓璁悎骞跺墠璺戜竴娆″畬鏁存祴璇曞浠?)
        elif health_score >= 60:
            actions.append("蹇呴』瀹屾垚鎵€鏈夐樆鏂拰涓ラ噸闂淇鍚庢墠鑳藉悎骞讹紝寤鸿澧炲姞Code Review杞")
        else:
            actions.append("涓嶅缓璁悎骞讹紝寤鸿浣滆€呭厛鑷淇涓昏闂鍚庨噸鏂版彁浜R")

        actions.append("寤鸿灏嗘湰瀹℃煡鎶ュ憡涓殑淇浠ｇ爜鐩存帴搴旂敤鍒伴」鐩腑锛屾瘡涓棶棰橀兘鎻愪緵浜嗗彲鐩存帴浣跨敤鐨勪慨澶嶆柟妗?)

        return actions


# 
def generate_report(parsed_code: Dict, security_issues: List[Dict],
                    performance_issues: List[Dict], semantic_issues: List[Dict]) -> Dict:
    generator = ReportGenerator()
    return generator.generate(parsed_code, security_issues, performance_issues, semantic_issues)
