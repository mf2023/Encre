# ea-skill-s3

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `s3` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-s3/
  pyproject.toml
  ea_skill_s3/
    __init__.py
    plugin.py
    skills/
      s3/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
