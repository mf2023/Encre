# ea-skill-slack-api

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `slack-api` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-slack-api/
  pyproject.toml
  ea_skill_slack_api/
    __init__.py
    plugin.py
    skills/
      slack-api/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
