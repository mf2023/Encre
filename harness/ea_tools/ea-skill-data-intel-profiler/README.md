# ea-skill-data-intel-profiler

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `data-intel-profiler` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-data-intel-profiler/
  pyproject.toml
  ea_skill_data_intel_profiler/
    __init__.py
    plugin.py
    skills/
      data-intel-profiler/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
