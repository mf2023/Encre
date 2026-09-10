# ea-skill-gmail-sender

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `gmail-sender` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-gmail-sender/
  pyproject.toml
  ea_skill_gmail_sender/
    __init__.py
    plugin.py
    skills/
      gmail-sender/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
