# ea-skill-wechat-article-search

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `wechat-article-search` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-wechat-article-search/
  pyproject.toml
  ea_skill_wechat_article_search/
    __init__.py
    plugin.py
    skills/
      wechat-article-search/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
