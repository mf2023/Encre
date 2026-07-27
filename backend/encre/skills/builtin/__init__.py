#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""Built-in skills shipped with Encre.

Each skill lives in its own sub-directory as a ``SKILL.md`` file with YAML
frontmatter.  They are loaded at runtime via :func:`builtin_skills_dir` and
registered with :class:`~encre.skills.types.SkillSource.BUNDLED` so user /
project / managed skills can override them by name.

Unlike the programmatically-registered skills in ``encre.skills.bundled``
(which need runtime logic such as argument parsing), these are pure static
markdown - adding a new built-in skill is just dropping a folder here.
"""

from importlib import resources


def builtin_skills_dir() -> str:
    """Return the on-disk path to the built-in skills directory.

    Uses :mod:`importlib.resources` so the directory resolves correctly both
    in editable installs (``-e``) and inside packaged wheels / frozen builds.
    """
    with resources.as_file(resources.files(__name__).joinpath(".")) as path:
        return str(path)
