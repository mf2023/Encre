# ea-skill-data-viz

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `data-viz` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-data-viz/
  pyproject.toml
  ea_skill_data_viz/
    __init__.py
    plugin.py
    skills/
      data-viz/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
