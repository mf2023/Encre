# ea-skill-arxiv-watcher

EA (Encre Agent) system-default skill package.

| Field | Value |
| --- | --- |
| Skill | `arxiv-watcher` |
| Tier | `system-default` |
| Version | `0.4.3` |
| Author | Dunimd Team |

## Layout

```
ea-skill-arxiv-watcher/
  pyproject.toml
  ea_skill_arxiv_watcher/
    __init__.py
    plugin.py
    skills/
      arxiv-watcher/   # SKILL.md + references/assets
```

Discovered automatically by the EA directory scan; the skill markdown is
loaded via `EncreSkillRegistry.load_from_dir`.
