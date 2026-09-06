---
name: tool-docker
description: Docker skill. command/image_or_container/options, manage containers/images without bare docker CLI
hidden: true
context: inline
---

## When to Use
- Manage Docker containers and images (build, run, ps, logs, stop, rm)
- Inspect container state during debugging

## When NOT to Use
- **Run bare `docker` in bash** -> use this tool
- **Deploy** -> `deploy` (higher-level deployment targets)
- **Run project tests** -> `test_run`

## Key Parameters
- `command` (required): docker subcommand (build, run, ps, logs, stop, rm, images, etc.)
- `image_or_container`: target image or container name/id
- `options`: subcommand options/flags

## Best Practices
- Use `ps`/`logs` to inspect before `stop`/`rm` (destructive)
- Confirm container identity before removing

## Common Pitfalls / Anti-patterns
- **rm/stop without inspecting**: `rm` deletes a container and its filesystem; `stop` kills a running service. Always `ps`/`logs` first to confirm it's the right container and you won't lose data
- **Removing by partial id/name**: an ambiguous prefix can match the wrong container. Use the full id or a unique name; confirm via `ps` first
- **Using bash for docker**: this tool integrates with permission/safety checks and parses output; bare `docker` in bash bypasses both
- **Forgetting -d on long-running containers**: a `run` without detach blocks the turn. Background long-running services or use `run_in_background`

## Pairing with Other Tools
- `bash`: for build steps docker depends on
- `deploy`: higher-level deploy
