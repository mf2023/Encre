# ea-skill-brightdata

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `brightdata` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-brightdata/
  pyproject.toml
  ea_skill_brightdata/
    __init__.py
    plugin.py
    skills/
      brightdata/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
