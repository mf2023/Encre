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

# Public surface of the multi-agent "swarm" package.
#
# A swarm decomposes a high-level goal into a DAG of tasks (``planner``), assigns
# each task to a role-specialised teammate (``roles``), executes the tasks with
# dependency-aware concurrency (``orchestrator`` / ``manager`` / ``teammate``),
# lets agents coordinate via a shared ``blackboard`` and point-to-point
# ``mailbox``, and optionally resolves disagreements through ``consensus``.
# ``session`` ties the pieces together into a single ``execute`` call.

from encre.swarm.blackboard import BlackboardEntry, EncreBlackboard
from encre.swarm.consensus import ConsensusResult, EncreConsensus, Proposal, Vote
from encre.swarm.mailbox import EncreMailbox, MailboxMessage
from encre.swarm.manager import EncreSwarmManager, SwarmProgress
from encre.swarm.orchestrator import EncreOrchestrator, OrchestrationEvent
from encre.swarm.planner import EncreTaskPlanner, TaskNode, TaskTree
from encre.swarm.roles import (
    ROLE_ARCHITECT,
    ROLE_CODER,
    ROLE_DEBUGGER,
    ROLE_GENERAL,
    ROLE_RESEARCHER,
    ROLE_REVIEWER,
    ROLE_TESTER,
    AgentRole,
    RoleRegistry,
)
from encre.swarm.session import EncreSwarmSession, SwarmEvent, SwarmResult
from encre.swarm.teammate import EncreTeammate, TeammateHandle

__all__ = [
    "ROLE_ARCHITECT",
    "ROLE_CODER",
    "ROLE_DEBUGGER",
    "ROLE_GENERAL",
    "ROLE_RESEARCHER",
    "ROLE_REVIEWER",
    "ROLE_TESTER",
    "AgentRole",
    "BlackboardEntry",
    "ConsensusResult",
    "EncreBlackboard",
    "EncreConsensus",
    "EncreMailbox",
    "EncreOrchestrator",
    "EncreSwarmManager",
    "EncreSwarmSession",
    "EncreTaskPlanner",
    "EncreTeammate",
    "MailboxMessage",
    "OrchestrationEvent",
    "Proposal",
    "RoleRegistry",
    "SwarmEvent",
    "SwarmProgress",
    "SwarmResult",
    "TaskNode",
    "TaskTree",
    "TeammateHandle",
    "Vote",
]
