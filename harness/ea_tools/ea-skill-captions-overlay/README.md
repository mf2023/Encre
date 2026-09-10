# ea-skill-captions-overlay

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `captions-overlay` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-captions-overlay/
  pyproject.toml
  ea_skill_captions_overlay/
    __init__.py
    plugin.py
    skills/
      captions-overlay/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
