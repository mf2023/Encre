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

"""Reusable "target model selection" logic.

The target-model-selection feature lets a consumer (e.g. a gateway adapter
configured via Settings -> Gateway -> Target Models) restrict which
configured models may serve its runs.  This module centralises the
transport-agnostic pieces shared by every consumer:

* :func:`parse_target_model_ids` -- turn a stored selection (a JSON string
  or a raw list, the shape persisted via the flat ``adapter_<id>_models``
  config key) into a list of model ids, or ``None`` when unrestricted.
* :func:`target_models_from_config_dict` -- read a selection straight out
  of a stored per-consumer config dict.
* :func:`apply_target_models` -- restrict a config copy to the given target
  models and pin it to the first eligible candidate so a run starts there.

Both the gateway runner and any future consumer (automation, relay, ...)
can reuse these functions without knowing each other's storage layout.
"""

import json
from typing import Any

from encre.config import EncreConfig, ModelConfig


def parse_target_model_ids(raw: Any) -> list[str] | None:
    """Parse a stored target-model selection into a list of model ids.

    Accepts either a JSON-encoded string (the shape written by the
    frontend) or a raw list.  Returns ``None`` when the value is empty,
    malformed or not a non-empty list -- i.e. the consumer is unrestricted
    and should fall back to its normal model resolution.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, list) or not raw:
        return None
    return [str(i) for i in raw]


def target_models_from_config_dict(stored: dict[str, Any]) -> list[str] | None:
    """Read the target model selection out of a stored config dict.

    The selection is stored under the ``models`` field (``models`` is also
    the field name the frontend persists as ``adapter_<id>_models``); the
    ``model_ids`` alias is accepted for legacy configs.
    """
    raw = stored.get("models") if stored.get("models") is not None else stored.get("model_ids")
    return parse_target_model_ids(raw)


def apply_target_models(
    cfg: EncreConfig,
    target_model_ids: list[str] | None,
) -> ModelConfig | None:
    """Restrict *cfg* to the given target models and pin it to the first
    eligible candidate.

    Sets ``cfg.target_model_ids`` so the agent's runtime model-failure
    fallback only considers those models, then pins ``cfg`` onto the first
    eligible candidate (target models first, then indicator, then a random
    enabled model).  Returns the pinned model, or ``None`` when no target
    model was requested or no candidate is eligible.
    """
    if not target_model_ids:
        return None
    cfg.target_model_ids = list(target_model_ids)
    candidates = cfg.resolve_model_candidates()
    if not candidates:
        return None
    first = candidates[0]
    cfg.model = first.model_id
    cfg.backend_type = first.backend_type
    cfg.api_key = first.api_key
    cfg.base_url = first.base_url
    cfg.max_tokens = first.max_tokens
    return first
