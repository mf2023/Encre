# Copyright 2026 Beijing Volcano Engine Technology Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Resolve the runtime workspace root for arkclaw / openclaw / other *claw* runtimes.

Resolution order:
  1. CLAW_WORKSPACE env var (explicit override)
  2. Scan ~/ for any ~/.{name}/workspace where 'claw' is in {name};
     prefer dirs that already contain evolution-data/, then prefer
     .arkclaw > .openclaw > others (alpha order).
  3. Fallback: ~/.arkclaw/workspace (production default for new installs).
"""

import os

ENV_VAR = "CLAW_WORKSPACE"
_FALLBACK = "~/.arkclaw/workspace"


def _scan_home():
    home = os.path.expanduser("~")
    if not os.path.isdir(home):
        return None
    try:
        entries = os.listdir(home)
    except OSError:
        return None
    found = []
    for name in entries:
        if not (name.startswith(".") and "claw" in name.lower()):
            continue
        ws = os.path.join(home, name, "workspace")
        if not os.path.isdir(ws):
            continue
        has_data = os.path.isdir(os.path.join(ws, "evolution-data"))
        found.append((has_data, name, ws))
    if not found:
        return None

    def sort_key(item):
        has_data, name, _ws = item
        priority = 0 if name == ".arkclaw" else (1 if name == ".openclaw" else 2)
        return (0 if has_data else 1, priority, name)

    found.sort(key=sort_key)
    return found[0][2]


def resolve_workspace_root():
    """Return absolute path to the runtime workspace root."""
    override = os.environ.get(ENV_VAR)
    if override:
        return os.path.expanduser(override)
    found = _scan_home()
    if found:
        return found
    return os.path.expanduser(_FALLBACK)


def resolve_runtime_home():
    """Return parent of the workspace (e.g. ~/.arkclaw)."""
    return os.path.dirname(resolve_workspace_root())


def claw_exclude_dirs():
    """All ~/.X dirnames where 'claw' is in name (used for scan-exclude)."""
    home = os.path.expanduser("~")
    out = set()
    try:
        for name in os.listdir(home):
            if name.startswith(".") and "claw" in name.lower():
                out.add(name)
    except OSError:
        pass
    out.update({".arkclaw", ".openclaw"})
    return out


if __name__ == "__main__":
    import json

    print(
        json.dumps(
            {
                "workspace_root": resolve_workspace_root(),
                "runtime_home": resolve_runtime_home(),
                "claw_exclude_dirs": sorted(claw_exclude_dirs()),
                "env_var": ENV_VAR,
            },
            indent=2,
        )
    )
