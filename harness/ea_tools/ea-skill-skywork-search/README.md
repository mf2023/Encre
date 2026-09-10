# ea-skill-skywork-search

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `skywork-search` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-skywork-search/
  pyproject.toml
  ea_skill_skywork_search/
    __init__.py
    plugin.py
    skills/
      skywork-search/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
