#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report Generator
审查报告生成器
"""

from typing import Dict, List


class ReportGenerator:
    """代码审查报告生成器"""

    def generate(self, parsed_code: Dict, security_issues: List[Dict],
                 performance_issues: List[Dict], semantic_issues: List[Dict]) -> Dict:
        """生成完整审查报告"""

        all_issues = security_issues + performance_issues + semantic_issues

        # 去重（基于行号和规则名）
        seen = set()
        unique_issues = []
        for issue in all_issues:
            key = (issue.get("line", 0), issue.get("rule", ""))
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        # 分级统计
        blocker = [i for i in unique_issues if i["severity"] == "阻断"]
        critical = [i for i in unique_issues if i["severity"] == "严重"]
        warning = [i for i in unique_issues if i["severity"] == "中等"]
        minor = [i for i in unique_issues if i["severity"] == "轻微"]

        # 计算健康度
        health_score = max(0, 100 - len(blocker) * 30 - len(critical) * 15 - len(warning) * 5 - len(minor) * 1)

        # 生成正面反馈
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
        """生成核心结论"""
        total = len(blocker) + len(critical) + len(warning) + len(minor)

        if health_score >= 90:
            return f"代码质量优秀（{health_score}分），共发现{total}个问题，以轻微优化建议为主，可安全合并。"
        elif health_score >= 75:
            return f"代码质量良好（{health_score}分），发现{len(critical)}个严重问题，建议修复后合并。"
        elif health_score >= 60:
            return f"代码质量及格（{health_score}分），存在{len(blocker)}个阻断级漏洞和{len(critical)}个严重问题，必须修复后才能合并。"
        else:
            return f"代码质量需重构（{health_score}分），存在严重安全漏洞和逻辑错误，不建议合并，需全面审查。"

    def _health_level(self, score: float) -> str:
        if score >= 90:
            return "优秀"
        elif score >= 75:
            return "良好"
        elif score >= 60:
            return "及格"
        else:
            return "需重构"

    def _generate_positive_feedback(self, parsed_code: Dict, issues: List[Dict]) -> List[str]:
        """生成正面反馈"""
        positive = []
        metadata = parsed_code.get("metadata", {})

        # 注释率
        ratio = metadata.get("comment_ratio", 0)
        if ratio > 0.2:
            positive.append(f"注释覆盖率达{ratio:.0%}，代码可读性较好")

        # 函数长度
        long_funcs = [i for i in issues if i["rule"] == "函数过长"]
        if not long_funcs:
            positive.append("函数长度控制良好，职责划分清晰")

        # 无安全问题
        security = [i for i in issues if i["severity"] in ["阻断", "严重"] and "注入" in i["rule"]]
        if not security:
            positive.append("未发现SQL注入、XSS等常见安全漏洞")

        # 导入规范
        unused = [i for i in issues if i["rule"] == "未使用的导入"]
        if len(unused) <= 1:
            positive.append("导入管理规范，依赖关系清晰")

        # 有正面评价兜底
        if not positive:
            positive.append("代码结构完整，功能实现清晰")

        return positive[:3]

    def _generate_overall_suggestions(self, health_score: float, blocker: List,
                                      critical: List, parsed_code: Dict) -> List[str]:
        """生成整体架构建议"""
        suggestions = []

        if blocker:
            suggestions.append("**优先处理安全漏洞**：存在阻断级安全问题，必须立即修复，建议引入安全编码规范（如OWASP Top 10检查清单）")

        if critical:
            suggestions.append("**性能优化**：存在严重性能陷阱，建议引入性能测试（如压力测试、慢查询监控）到CI流程")

        if health_score < 75:
            suggestions.append("**代码重构**：整体质量偏低，建议分阶段重构：先修复安全问题，再优化性能，最后清理可读性债务")

        # 基于代码规模
        loc = parsed_code.get("metadata", {}).get("lines_of_code", 0)
        if loc > 500:
            suggestions.append(f"**模块拆分**：代码量较大（{loc}行），建议按职责拆分为多个模块/文件，降低耦合度")

        # 基于语言特性
        lang = parsed_code.get("language", "")
        if lang == "python":
            suggestions.append("**类型注解**：建议逐步引入Python类型注解（typing），提升IDE提示和静态检查能力")
        elif lang in ["javascript", "typescript"]:
            suggestions.append("**TypeScript迁移**：如为JS项目，建议核心模块逐步迁移到TS，提升类型安全")

        if not suggestions:
            suggestions.append("**持续改进**：建议引入自动化代码审查工具（如SonarQube、CodeClimate）到CI/CD流程，持续监控代码质量")

        return suggestions

    def _generate_next_actions(self, health_score: float, blocker: List,
                               critical: List, warning: List) -> List[str]:
        """生成下一步行动建议"""
        actions = []

        if blocker:
            actions.append(f"1. **立即修复{len(blocker)}个阻断级安全问题**（预计1-2小时），禁止合并")
        if critical:
            actions.append(f"2. **修复{len(critical)}个严重问题**（预计2-4小时），修复后重新审查")
        if warning:
            actions.append(f"3. **处理{len(warning)}个中等问题**（预计1-3小时），可在下个迭代完成")

        if health_score >= 90:
            actions.append("代码质量优秀，可直接合并，建议后续关注测试覆盖率")
        elif health_score >= 75:
            actions.append("修复严重问题后可合并，建议合并前跑一次完整测试套件")
        elif health_score >= 60:
            actions.append("必须完成所有阻断和严重问题修复后才能合并，建议增加Code Review轮次")
        else:
            actions.append("不建议合并，建议作者先自行修复主要问题后重新提交PR")

        actions.append("建议将本审查报告中的修复代码直接应用到项目中，每个问题都提供了可直接使用的修复方案")

        return actions


# 对外入口
def generate_report(parsed_code: Dict, security_issues: List[Dict],
                    performance_issues: List[Dict], semantic_issues: List[Dict]) -> Dict:
    generator = ReportGenerator()
    return generator.generate(parsed_code, security_issues, performance_issues, semantic_issues)
