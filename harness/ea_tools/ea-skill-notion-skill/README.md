# ea-skill-notion-skill

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `notion-skill` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-notion-skill/
  pyproject.toml
  ea_skill_notion_skill/
    __init__.py
    plugin.py
    skills/
      notion-skill/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
