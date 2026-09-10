---
name: tool-deploy
description: Deployment skill. target/action/config_file/project_name, deploy apps without bare kubectl/gcloud/vercel
hidden: true
context: inline
---

## When to Use
- Deploy an application to a target environment
- Manage deployment actions (deploy/status/rollback) through a unified interface

## When NOT to Use
- **Run bare `kubectl`/`gcloud`/`vercel`/`netlify` in bash** -> use this tool
- **Build the app** -> `bash` (build tools)
- **Run tests before deploy** -> `test_run`

## Key Parameters
- `target` (required): deployment target (e.g. k8s, vercel, netlify, gcloud)
- `action`: deploy/status/rollback
- `config_file`: deployment config path
- `project_name`: project identifier on the target

## Best Practices
- Run tests (`test_run`) and lint (`lint_format`) before deploying
- Confirm the target and action before triggering; deploys affect shared state
- For rollbacks, verify the target's previous state first

## Common Pitfalls / Anti-patterns
- **Deploying without testing**: always verify before deploy
- **Using bash for deploy commands**: use this tool; it integrates with permission/safety checks
- **Wrong target/action**: deployments are hard to reverse; confirm before triggering
- **Skipping pre-deploy checks** - tests, build, lint all matter before a deploy. Run the verification pipeline first.
- **Deploying from the wrong branch** - a deploy from a feature branch that is not ready or merged to main. Confirm the branch is current and the target is right.

## Pairing with Other Tools
- `test_run`/`lint_format`: verify before deploy
- `bash`: build step if the target needs a build first
