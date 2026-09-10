# ea-skill-gmail-skill

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `gmail-skill` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-gmail-skill/
  pyproject.toml
  ea_skill_gmail_skill/
    __init__.py
    plugin.py
    skills/
      gmail-skill/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
