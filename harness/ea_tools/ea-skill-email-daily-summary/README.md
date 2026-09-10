# ea-skill-email-daily-summary

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `email-daily-summary` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-email-daily-summary/
  pyproject.toml
  ea_skill_email_daily_summary/
    __init__.py
    plugin.py
    skills/
      email-daily-summary/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
