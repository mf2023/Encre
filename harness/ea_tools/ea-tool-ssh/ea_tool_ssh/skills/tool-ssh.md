---
name: tool-ssh
description: "Run commands, transfer files, or execute multi-line scripts on a remote host via SSH/SCP using the system ssh and scp clients. Use this for remote server operations: `exec` a single command, `upload`/`download` files with SCP, `ping` to verify connectivity, or `script` to run a multi-line bash script remotely. Do NOT use this for interactive shells, port forwarding, or long-running daemons; prefer a persistent session or dedicated tool. Tips: prefer key-based auth via `key_file` over `password` (which requires sshpass); tune `timeout` for slow commands. Pitfalls: StrictHostKeyChecking is disabled and ConnectTimeout is 15s; large SCP transfers may hit the 120s timeout."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# ssh

Run commands, transfer files, or execute multi-line scripts on a remote host via SSH/SCP using the system ssh and scp clients. Use this for remote server operations: `exec` a single command, `upload`/`download` files with SCP, `ping` to verify connectivity, or `script` to run a multi-line bash script remotely. Do NOT use this for interactive shells, port forwarding, or long-running daemons; prefer a persistent session or dedicated tool. Tips: prefer key-based auth via `key_file` over `password` (which requires sshpass); tune `timeout` for slow commands. Pitfalls: StrictHostKeyChecking is disabled and ConnectTimeout is 15s; large SCP transfers may hit the 120s timeout.
