# ea-skill-podcast-generation

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `podcast-generation` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-podcast-generation/
  pyproject.toml
  ea_skill_podcast_generation/
    __init__.py
    plugin.py
    skills/
      podcast-generation/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
