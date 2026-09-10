# ea-skill-deep-code-reviewer

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `deep-code-reviewer` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-deep-code-reviewer/
  pyproject.toml
  ea_skill_deep_code_reviewer/
    __init__.py
    plugin.py
    skills/
      deep-code-reviewer/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
