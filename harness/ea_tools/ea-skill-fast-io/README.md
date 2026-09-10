# ea-skill-fast-io

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `fast-io` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-fast-io/
  pyproject.toml
  ea_skill_fast_io/
    __init__.py
    plugin.py
    skills/
      fast-io/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
