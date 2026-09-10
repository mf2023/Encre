# EA Tool Packages

Bundled EA (Encre Agent) extension packages. **The directory itself is the
registry** — discovery is fully automatic and requires no registration code
anywhere.

## Packages

| Package | Tier | Tools |
|---------|------|-------|
| `ea-tool-file-edit` | mandatory |  |
| `ea-tool-file-read` | mandatory |  |
| `ea-tool-file-write` | mandatory |  |
| `ea-tool-terminal` | mandatory |  |
| `ea-tool-web-fetch` | mandatory |  |
| `ea-tool-web-search` | mandatory |  |
| `ea-tool-agent` | system-default | `agent` |
| `ea-tool-apply-patch` | system-default |  |
| `ea-tool-archive` | system-default |  |
| `ea-tool-bash-io` | system-default | `bash_kill`, `bash_list`, `bash_output` |
| `ea-tool-browser` | system-default | `browser` |
| `ea-tool-chart` | system-default | `chart` |
| `ea-tool-cloud-storage` | system-default | `cloud_storage` |
| `ea-tool-codebase` | system-default | `codebase_context`, `codebase_search` |
| `ea-tool-computer-use` | system-default | `computer_use` |
| `ea-tool-cron-create` | system-default | `cron_create` |
| `ea-tool-cron-delete` | system-default | `cron_delete` |
| `ea-tool-cron-list` | system-default | `cron_list` |
| `ea-tool-database` | system-default | `database` |
| `ea-tool-deploy` | system-default | `deploy` |
| `ea-tool-desktop` | system-default | `desktop` |
| `ea-tool-device-battery` | system-default | `device_battery` |
| `ea-tool-device-display` | system-default | `device_display` |
| `ea-tool-device-info` | system-default | `device_info` |
| `ea-tool-device-location` | system-default | `device_location` |
| `ea-tool-device-network` | system-default | `device_network` |
| `ea-tool-device-sensor` | system-default | `device_sensor` |
| `ea-tool-diagram` | system-default | `diagram` |
| `ea-tool-diff` | system-default |  |
| `ea-tool-docker` | system-default | `docker` |
| `ea-tool-document` | system-default | `document` |
| `ea-tool-email` | system-default | `email` |
| `ea-tool-env-manager` | system-default | `env_manager` |
| `ea-tool-find-tool` | system-default | `find_tool` |
| `ea-tool-generate-image` | system-default | `edit_image`, `generate_image`, `image_variation` |
| `ea-tool-git-tool` | system-default | `git` |
| `ea-tool-github` | system-default | `github` |
| `ea-tool-glob` | system-default | `glob` |
| `ea-tool-grep` | system-default | `grep` |
| `ea-tool-hash-crypto` | system-default | `hash_crypto` |
| `ea-tool-image` | system-default | `image` |
| `ea-tool-info` | system-default | `info` |
| `ea-tool-json-tool` | system-default | `json_tool` |
| `ea-tool-lint-format` | system-default | `lint_format` |
| `ea-tool-lsp` | system-default | `lsp` |
| `ea-tool-manage` | system-default | `manage` |
| `ea-tool-media` | system-default | `media` |
| `ea-tool-media-api` | system-default | `create_embeddings`, `create_moderation`, `transcribe_audio`, `translate_audio` |
| `ea-tool-memory` | system-default | `memory_create`, `memory_delete`, `memory_profile`, `memory_read`, `memory_search`, `memory_update` |
| `ea-tool-notebook` | system-default | `notebook` |
| `ea-tool-notify` | system-default | `notify` |
| `ea-tool-pdf` | system-default | `pdf` |
| `ea-tool-platform-api` | system-default | `batch_api`, `file_api`, `fine_tuning_api` |
| `ea-tool-presentation` | system-default | `presentation` |
| `ea-tool-qr-code` | system-default | `qr_code` |
| `ea-tool-question` | system-default | `question` |
| `ea-tool-rest-client` | system-default | `rest_client` |
| `ea-tool-skill` | system-default | `skill` |
| `ea-tool-spreadsheet` | system-default | `spreadsheet` |
| `ea-tool-ssh` | system-default | `ssh` |
| `ea-tool-swarm-tool` | system-default | `swarm` |
| `ea-tool-task-create` | system-default | `task_create` |
| `ea-tool-task-get` | system-default | `task_get` |
| `ea-tool-task-list` | system-default | `task_list` |
| `ea-tool-task-output` | system-default | `task_output` |
| `ea-tool-task-stop` | system-default | `task_stop` |
| `ea-tool-task-update` | system-default | `task_update` |
| `ea-tool-test-runner` | system-default | `test_run` |
| `ea-tool-todo` | system-default | `todo` |
| `ea-tool-translation` | system-default | `translation` |
| `ea-tool-vlm-computer-use` | system-default | `vlm_computer_use` |
| `ea-tool-workflow` | system-default | `workflow` |

## Skill Packages

Non-tool skills are packaged one-per-skill as `ea-skill-<name>`:

| Package | Tier | Skill |
|---------|------|-------|
| `ea-skill-<name>` | system-default | `<name>` |

The 219 bundled skills live under `ea-skill-*/<module>/skills/<name>/SKILL.md`
(a verbatim copy of the legacy `encre/skills/builtin/<name>/` folder, including
`references/`, `assets/` and scripts).  They are loaded via
`EncreSkillRegistry.load_from_dir` and, like tool packages, are discovered by
the directory scan and shipped automatically inside the PyInstaller bundle.

## Tier Classification

| Tier | Value | Behavior |
|------|-------|----------|
| Built-in mandatory | `mandatory` | Hardcoded in core, cannot be disabled |
| System default | `system-default` | Ships with package, can be uninstalled |
| User custom | `user` | External pip installation |

Tier is declared per package in `pyproject.toml`:

```toml
[tool.ea]
tier = "mandatory"
```

- `mandatory` / `system-default`: auto-discovered by the directory scan and
  auto-activated. `mandatory` additionally cannot be deactivated.
- `user`: third-party packages installed via pip; discovered through the
  `ea.plugins` entry-point group instead of this directory.

## Discovery (zero registration)

The EA directory scanner (`encre.plugins.ea_scan`) scans every `ea-tool-*` and
`ea-skill-*` folder under `ea_tools/`, reads its `pyproject.toml`, inserts the package on
`sys.path`, imports the plugin factory, and registers + auto-activates it.
The same logic runs in frozen (PyInstaller) builds, where the whole `ea_tools/`
tree is shipped under `sys._MEIPASS/ea_tools/`.

**Drop a new package folder into this directory and it just works** — both at
runtime and in the next PyInstaller build (the whole tree is staged and packed
as data).

Skills are loaded automatically too: each `<module>/skills/*.md` is picked up
by `EncreSkillRegistry.load_from_dir` at agent startup (BUNDLED priority).

## Structure

```
harness/ea_tools/
  ea-tool-file-read/
    README.md
    pyproject.toml          # Metadata + [tool.ea] tier
    ea_tool_file_read/
      __init__.py           # Lazy re-exports
      tool.py               # Tool implementation (build_tool)
      plugin.py             # EncrePlugin manifest + create_plugin factory
      skills/
        tool-file-read.md   # Skill instructions (YAML frontmatter)
```

## Standalone install (optional)

Each package remains a valid pip project, so it can also be built and
installed standalone:

```bash
pip install ./ea-tool-file-read
```

The `ea.plugins` entry point in each package keeps that path working; inside
the Encre app the directory scan wins (first registered wins).
