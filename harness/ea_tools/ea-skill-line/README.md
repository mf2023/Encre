# ea-skill-line

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `line` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-line/
  pyproject.toml
  ea_skill_line/
    __init__.py
    plugin.py
    skills/
      line/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
