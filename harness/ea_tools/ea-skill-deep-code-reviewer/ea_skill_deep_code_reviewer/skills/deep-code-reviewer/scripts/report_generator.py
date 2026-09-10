from __future__ import annotations

"""
Report Generator
瀹煡鎶ュ憡鐢熸垚鍣?
"""

from typing import Dict, List


class ReportGenerator:
    """Generates a complete code review report."""

    def generate(self, parsed_code: Dict, security_issues: List[Dict],
                 performance_issues: List[Dict], semantic_issues: List[Dict]) -> Dict:
        """鐢熸垚瀹屾暣瀹煡鎶ュ憡"""

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
        warning = [i for i in unique_issues if i["severity"] == "涓瓑"]
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
        """鐢熸垚鏍稿績缁撹"""
        total = len(blocker) + len(critical) + len(warning) + len(minor)

        if health_score >= 90:
            return f"Excellent code quality ({health_score} pts), {total} issues found, minor optimizations suggested; safe to merge."
        elif health_score >= 75:
            return f"Good code quality ({health_score} pts), {len(critical)} critical issues found; recommend fixing before merge."
        elif health_score >= 60:
            return f"Passable code quality ({health_score} pts), {len(blocker)} blockers and {len(critical)} critical issues; must fix before merge."
        else:
            return f"浠ｇ爜璐ㄩ噺闇閲嶆瀯（{health_score}鍒嗭級锛屽瓨鍦ㄤ弗閲嶅畨鍏ㄦ紡娲炲拰閫昏緫閿欒锛屼笉寤鸿鍚堝苟锛岄渶鍏ㄩ潰瀹煡銆?"

    def _health_level(self, score: float) -> str:
        if score >= 90:
            return "浼樼"
        elif score >= 75:
            return "鑹ソ"
        elif score >= 60:
            return "鍙婃牸"
        else:
            return "闇閲嶆瀯"

    def _generate_positive_feedback(self, parsed_code: Dict, issues: List[Dict]) -> List[str]:
        """鐢熸垚姝ｉ潰鍙嶉"""
        positive = []
        metadata = parsed_code.get("metadata", {})

        # 
        ratio = metadata.get("comment_ratio", 0)
        if ratio > 0.2:
            positive.append(f"娉ㄩ噴瑕嗙洊鐜囪揪{ratio:.0%}锛屼唬鐮佸彲璇绘ц緝濂?")

        # 
        long_funcs = [i for i in issues if i["rule"] == "鍑芥暟杩囬暱"]
        if not long_funcs:
            positive.append("鍑芥暟闀垮害鎺у埗鑹ソ锛岃亴璐ｅ垝鍒嗘竻鏅?")

        # 
        security = [i for i in issues if i["severity"] in ["闃绘柇", "涓ラ噸"] and "娉ㄥ叆" in i["rule"]]
        if not security:
            positive.append("鏈彂鐜癝QL娉ㄥ叆銆乆SS绛夊父瑙佸畨鍏ㄦ紡娲?")

        # 
        unused = [i for i in issues if i["rule"] == "鏈娇鐢ㄧ殑瀵煎叆"]
        if len(unused) <= 1:
            positive.append("瀵煎叆绠悊瑙勮寖锛屼緷璧栧叧绯绘竻鏅?")

        # 
        if not positive:
            positive.append("浠ｇ爜缁撴瀯瀹屾暣锛屽姛鑳藉疄鐜版竻鏅?")

        return positive[:3]

    def _generate_overall_suggestions(self, health_score: float, blocker: List,
                                      critical: List, parsed_code: Dict) -> List[str]:
        """鐢熸垚鏁翠綋鏋舵瀯寤鸿"""
        suggestions = []

        if blocker:
            suggestions.append("**浼樺厛澶勭悊瀹夊叏婕忔礊**锛氬瓨鍦ㄩ樆鏂骇瀹夊叏闂锛屽繀椤荤珛鍗充慨澶嶏紝寤鸿寮曞叆瀹夊叏缂栫爜瑙勮寖锛堝OWASP Top 10妫鏌ユ竻鍗曪級")

        if critical:
            suggestions.append("**鎬ц兘浼樺寲**锛氬瓨鍦ㄤ弗閲嶆ц兘闄烽槺锛屽缓璁紩鍏ユц兘娴嬭瘯锛堝鍘嬪姏娴嬭瘯銆佹參鏌ヨ鐩戞帶锛夊埌CI娴佺▼")

        if health_score < 75:
            suggestions.append("**浠ｇ爜閲嶆瀯**锛氭暣浣撹川閲忓亸浣庯紝寤鸿鍒嗛樁娈甸噸鏋勶細鍏堜慨澶嶅畨鍏ㄩ棶棰橈紝鍐嶄紭鍖栨ц兘锛屾渶鍚庢竻鐞嗗彲璇绘у哄姟")

        # 
        loc = parsed_code.get("metadata", {}).get("lines_of_code", 0)
        if loc > 500:
            suggestions.append(f"**妯潡鎷嗗垎**锛氫唬鐮侀噺杈冨ぇ（{loc}琛岋級锛屽缓璁寜鑱岃矗鎷嗗垎涓哄涓ā鍧?鏂囦欢锛岄檷浣庤悎搴?")

        # 
        lang = parsed_code.get("language", "")
        if lang == "python":
            suggestions.append("**绫诲瀷娉ㄨВ**锛氬缓璁愭寮曞叆Python绫诲瀷娉ㄨВ锛坱yping锛夛紝鎻愬崌IDE鎻愮ず鍜岄潤鎬佹鏌ヨ兘鍔?")
        elif lang in ["javascript", "typescript"]:
            suggestions.append("**TypeScript杩佺Щ**锛氬涓篔S椤圭洰锛屽缓璁牳蹇冩ā鍧楅愭杩佺Щ鍒癟S锛屾彁鍗囩被鍨嬪畨鍏?")

        if not suggestions:
            suggestions.append("**鎸佺画鏀硅繘**锛氬缓璁紩鍏ヨ嚜鍔ㄥ寲浠ｇ爜瀹煡宸ュ叿锛堝SonarQube銆丆odeClimate锛夊埌CI/CD娴佺▼锛屾寔缁洃鎺т唬鐮佽川閲?")

        return suggestions

    def _generate_next_actions(self, health_score: float, blocker: List,
                               critical: List, warning: List) -> List[str]:
        """鐢熸垚涓嬩竴姝ヨ鍔ㄥ缓璁"""
        actions = []

        if blocker:
            actions.append(f"1. **绔嬪嵆淇{len(blocker)}涓樆鏂骇瀹夊叏闂**锛堥璁?-2灏忔椂锛夛紝绂佹鍚堝苟")
        if critical:
            actions.append(f"2. **淇{len(critical)}涓弗閲嶉棶棰?*锛堥璁?-4灏忔椂锛夛紝淇鍚庨噸鏂板鏌?")
        if warning:
            actions.append(f"3. **澶勭悊{len(warning)}涓腑绛夐棶棰?*锛堥璁?-3灏忔椂锛夛紝鍙湪涓嬩釜杩唬瀹屾垚")

        if health_score >= 90:
            actions.append("浠ｇ爜璐ㄩ噺浼樼锛屽彲鐩存帴鍚堝苟锛屽缓璁悗缁叧娉ㄦ祴璇曡鐩栫巼")
        elif health_score >= 75:
            actions.append("淇涓ラ噸闂鍚庡彲鍚堝苟锛屽缓璁悎骞跺墠璺戜竴娆畬鏁存祴璇曞浠?")
        elif health_score >= 60:
            actions.append("蹇呴』瀹屾垚鎵鏈夐樆鏂拰涓ラ噸闂淇鍚庢墠鑳藉悎骞讹紝寤鸿澧炲姞Code Review杞")
        else:
            actions.append("涓嶅缓璁悎骞讹紝寤鸿浣滆呭厛鑷淇涓昏闂鍚庨噸鏂版彁浜R")

        actions.append("寤鸿灏嗘湰瀹煡鎶ュ憡涓殑淇浠ｇ爜鐩存帴搴旂敤鍒伴」鐩腑锛屾瘡涓棶棰橀兘鎻愪緵浜嗗彲鐩存帴浣跨敤鐨勪慨澶嶆柟妗?")

        return actions


# 
def generate_report(parsed_code: Dict, security_issues: List[Dict],
                    performance_issues: List[Dict], semantic_issues: List[Dict]) -> Dict:
    generator = ReportGenerator()
    return generator.generate(parsed_code, security_issues, performance_issues, semantic_issues)
