# ea-skill-yuque

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `yuque` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-yuque/
  pyproject.toml
  ea_skill_yuque/
    __init__.py
    plugin.py
    skills/
      yuque/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
