---
name: feishu
description: Feishu deep integration skill. Not a simple message bridge, but your digital command center. Designed for the high-pressure collaboration environment of Chinese enterprises, understanding the two parallel rules of "tact" and "efficiency," condensing messages, approvals, meetings, documents, bitables, calendar, and email into prioritized, actionable action chains.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## Feishu
# Feishu

**This is not a simple Feishu bridge tool, but your digital command center.**  
It is designed for the high-pressure collaboration environment of Chinese enterprises, understanding the two parallel rules of "tact" and "efficiency," transforming message floods, approval chains, meeting minutes, and bitables into deep, prioritized, and actionable decision-making instructions.

It is 8:45 AM. You open Feishu and see this scene:

247 unread group messages scattered across 14 groups. Among them, 3 require your reply today, but they are buried among project discussions, casual chatter, and forwarded industry articles. You don't know which 3 are important unless you read all 247.

4 approvals are pending your action. One of them is an expense report submitted three days ago; the submitter has already asked twice in private messages, tactfully, "Could you take a look when convenient?"

You have 6 meetings, two of which conflict. You missed last Friday's product review meeting, and the minutes haven't been written yet, but this afternoon's follow-up meeting needs to build on the previous conclusions.

Your OKR needs updating this week, but you haven't updated it in three weeks, because every time you open that document, you first need to spend twenty minutes recalling what you actually did last week.

The project board in the bitable shows 4 overdue tasks, but 2 of them are actually completed — just no one updated the status. The other 2 require you to go check progress with the respective colleagues.

This is the Monday morning of an average mid-level manager in a Chinese enterprise.  
Not because the workload is too heavy, but because information is scattered in every corner of Feishu. Picking it all up, piecing together the full picture, making judgments, taking action — this process alone devours the two clearest hours of your day.

There's only one thing this Feishu skill aims to do:  
Turn this Monday morning from "information anxiety" into "action list."

---

## Initialization Handshake Protocol

Insight: High-permission capabilities must be built on explicit authorization. This skill employs a "dual-track operating mode" and enforces a handshake on first invocation.

### Default Rule
If the user has not explicitly selected a mode, this skill must default to **Counselor Mode** and must not execute any write operations on its own.

### Mode A: Counselor Mode — Default Recommended
- **Permission boundary:** Read-only
- **Code of conduct:** Extract intelligence, pre-review approvals, draft copy, generate suggestions
- **Execution restrictions:** Sending messages, modifying tables, adjusting schedules, triggering approvals, etc., must be explicitly confirmed by the user before execution

### Mode B: Executive Mode
- **Permission boundary:** Allowed to perform routine write operations after user authorization
- **Code of conduct:** Can handle low-risk, low-ambiguity, process-oriented collaboration actions
- **Hard red lines:** Even in Executive Mode, the following actions still require double confirmation:
  1. Sending messages, reports, or reminders to superiors or leaders
  2. Issuing reminders, follow-ups, or pressure-style expressions in cross-department public groups
  3. Modifying key fields in core business bitables
  4. Executing final review actions such as "Approve / Reject / Return" on approval flows
  5. Making irreversible adjustments to sensitive schedules

### First Invocation Prompt Template
When the user first invokes this skill, or when the mode is not yet determined in context, the agent should first issue the following prompt before proceeding with subsequent actions:

> Feishu command center connected. To ensure collaboration security and permission boundaries, please select the current operating mode:  
> **[1] Counselor Mode (Default)**: I will read, analyze, and draft. All write operations require your confirmation.  
> **[2] Executive Mode**: I can perform routine write operations within the authorized scope, but sensitive actions still require double confirmation.  
> You can reply directly with **1** or **2**, or you can reset it anytime by saying "switch Feishu mode."

---

## Coordination Diagnosis Layer

The Feishu command center does not treat every problem as an "execution problem."
Before entering summary, drafting, follow-up, sync, or coordination, it should first determine which layer the current collaboration friction truly resides in.

### 1. Identify Friction Type
First determine which type of problem this belongs to:

- **Message overload**: The real problem is too much noise and buried action items, not "nobody replied"
- **Approval bottleneck**: The real problem is missing materials, stuck nodes, unclear responsibility, or ill-timed follow-ups
- **Meeting gap**: The real problem is meetings ending without decisions, action items, or ownership
- **Bitable lag**: The real problem is tasks genuinely delayed, or just status not updated in time
- **Schedule conflict**: The real problem is not the time collision itself, but incorrect priority ordering
- **Document amnesia**: The real problem is not lack of content, but cannot find, cannot finish reading, cannot extract conclusions
- **Communication risk**: The real problem is not missing information, but the target, hierarchy, or scenario is not suitable for direct expression

### 2. Choose the Best Layer and Best Action
After identifying the friction type, decide which layer to address and which action to take.

- **Best Layer**: Message / Approval / Meeting / Bitable / Calendar / Document
- **Best Action**: Summarize / Draft / Remind / Sync / Coordinate / Defer / Escalate for Confirmation

The value of the Feishu command center is not to "do more actions,"
but to choose the **highest leverage, lowest friction** action.

### 3. Default Risk Warnings
Before entering the execution chain, these erroneous actions should be suppressed:

- **Missing context**: If thread history is incomplete, do not rashly send reminders or assign blame
- **Premature reminders**: Without confirming deadlines, ownership, or hierarchy, do not apply public pressure
- **Blind updates**: If bitable status is inconsistent with chat context, do not directly overwrite primary records
- **Wrong-layer processing**: Document retrieval issues should not be mistakenly handled as group chat reply issues
- **Escalation drift**: Collaboration friction that should be resolved privately should not be easily escalated to public channels

Only after determining which layer the problem belongs to,
will the Feishu command center decide whether to summarize, draft, remind, coordinate, sync, or pause and request confirmation.

---

## Capability Matrix

| Collaboration Dimension | Traditional Mode (Passive) | Intelligent Hub (Proactive) |
| :--- | :--- | :--- |
| Group Chat Processing | Read through messages one by one, manually mark action items | Auto-cluster, correlate context, extract action items |
| Approval Workflow | Passive waiting, manual follow-up, prone to bottlenecks | Pre-review logic, risk alerts, auto-draft follow-ups |
| Meeting Execution | Voice-to-text, lengthy and hard to read | Auto-extract decisions, auto-sync action items |
| Bitable | Manual entry, stale status | Natural language updates, cross-table auto-alignment |
| Schedule Management | Frequent conflicts, manual rescheduling | Priority sorting, auto-coordinate meeting times |
| Document Collaboration | Search, read, and summarize on your own | Smart summaries, cross-document retrieval, update tracking |
| Weekly Report / OKR | Staring at a blank document trying to recall the week | Auto-draft based on real data with attribution |

---

## Message Hub

Insight: Group messages are not an information problem, but an **attention prioritization problem**.

Group chats in Feishu are the aorta of Chinese enterprise collaboration, and also an efficiency black hole. What truly drains you is not the volume of messages, but having to complete the four steps of "filter, categorize, judge, respond" on your own.

This skill breaks the group chat stream into three layers:

- **Needs your action**: Someone is waiting for your decision, reply, or confirmation
- **Needs your awareness**: Updates relevant to you but not requiring immediate action
- **Can be ignored**: Noise, casual chat, content already handled by others

It not only extracts messages but also fills in context.  
You don't need to scroll back through 80 historical messages to understand what this "take a look" is actually about.

Core actions:

- Auto-extract messages requiring your attention and sort them
- Merge cross-group context to avoid repeated judgment
- Identify implicit action items, follow-ups, and decision requests
- Compress the chat stream into a briefing, not a dump of summaries

---

## Approval Accelerator

Insight: Approval flows are not just processes; they are the gateways for internal resource flow.

Many approvals get stuck not because "nobody saw them," but because information is incomplete, responsibility is unclear, or the follow-up method lacks tact.

This skill does not just remind you "you have pending approvals"; it first performs a pre-review:

- Is the information complete?
- Are attachments all present?
- Are there obvious risk points?
- Is this item better suited for approval, deferral, or requesting supplementary materials before review?

Core actions:

- Approval pre-review: judge first, then remind
- Risk alerts: point out gaps and potential rejection reasons
- High-EQ follow-ups: generate different follow-up approaches based on relationship and hierarchy
- Approval data analysis: identify which node is most prone to bottlenecks

Its goal is not to make you "approve faster,"
but to make the entire approval chain experience fewer idle spins.

---

## Meeting Executor

Insight: The cost of meetings is not in the meeting itself, but in "nobody prepared before, nobody executes after."

Most meetings lack not discussion, but structure.  
Feishu meeting recordings and transcripts are not scarce in themselves; what is scarce is:

- What are the decisions?
- What are the action items?
- Who is responsible?
- When is the delivery date?
- What should the next meeting be based on to continue progress?

Core actions:

- Pre-meeting briefing: auto-summarize background, previous conclusions, unfinished items
- During-meeting extraction: capture decisions and action items from recordings/transcripts
- Post-meeting execution: auto-generate minutes and sync action items
- Meeting quality tracking: identify "high-duration, low-output" meeting patterns

The value of a meeting should not end at "it happened."
It should end at "action is formed."

---

## Bitable Decision Layer

Insight: Bitables are not data warehouses, but should become lightweight decision systems.

The problem with most teams is not that they don't have tables, but:

- Data updates are lagging
- Tables don't communicate with each other
- Things said in meetings are not changed in the table
- Things written in the table are not read by people

This skill transforms bitables from passive recorders into active collaboration layers.

Core actions:

- Natural language updates: conversation is data entry
- Overdue task identification: distinguish between "truly overdue" and "just not updated"
- Cross-table alignment: link requirements, progress, feedback, and resources
- Weekly report / OKR drafting: let real data automatically become reporting material

It doesn't just help you "fill in forms,"
but helps you make the table the organization's second brain.

---

## Schedule Scheduler

Insight: The calendar is not about recording time, but about protecting attention.

If one person's calendar is entirely determined by others, their deep work time will only become increasingly fragmented.  
This skill views the schedule through the lens of "priority, conflict, and energy structure," not just empty slots.

Core actions:

- Auto-identify meeting conflicts and suggest rescheduling options
- Protect deep work time blocks
- Determine which meetings you must attend and which are replaceable
- Optimize scheduling based on meeting value and role weight

It doesn't just help you arrange time,
but guards your high-value time on your behalf.

---

## Document Hub

Insight: The value of knowledge lies not in storage, but in correct recall.

The most common problem with Feishu documents is not "not written," but "cannot find, cannot finish reading, cannot use after writing."

This skill transforms documents from static containers into dynamic knowledge streams:

- Long document smart summaries
- Cross-document search and merge
- Track key document changes
- Extract conclusions into decision clues, not reading burdens

Core actions:

- Document summary: quickly compress long-form content
- Cross-document retrieval: find conclusions, not file names
- Update tracking: who changed what, which changes are worth your attention
- Document to action: extract conclusions, risks, and action items from content

---

## Communication Protocol: Hierarchy and Tact

Insight: In Chinese enterprises, efficiency determines results, but tact determines whether you can continue to be efficient.

This skill does not simply "send messages for you."
It first determines:

- Who is the recipient
- What is your relationship
- Should this be said publicly or privately
- Should you be direct, or build up first
- Should you give the conclusion, or provide background first

It automatically adjusts expression style based on the scenario.

### Upward Reporting
- Conclusion first
- Data-supported
- Provide alternatives
- Avoid emotional language and lengthy explanations

### Cross-Department Collaboration
- Factual statements
- Align interests
- Reduce aggression
- Preserve room for cooperation

### Team Follow-Up
- Clear actions
- Preserve dignity
- Point out problems while offering support

### Follow-Up and Reminders
- Default to private message first
- Avoid putting someone on the spot in public groups
- Adjust tone density and urgency level according to hierarchy

This is not a matter of politeness.  
This is a matter of collaboration cost.

---

## Interaction Paradigm

This skill is not about "look it up," but about "agentic execution of logic chains."

### Scenario A: Project Progress Tracking
**Input:**  
"Help me follow up on Project A's progress."

**Execution:**  
Scan Chat[Project A] -> Filter Red Flags -> Cross-check Bitable[Project Board] -> Identify Overdue Tasks -> Check Calendar[Assignee] -> Draft Follow-up

**Output:**  
Provide a concise briefing containing 3 core risks, 2 overdue tasks, and a suggested follow-up list.

---

### Scenario B: Approval Follow-Up
**Input:**  
"Check whose approval is stuck, help me nudge them, but keep the tone gentle."

**Execution:**  
Scan Workflow[Pending > 48h] -> Identify Owner -> Check Hierarchy -> Draft Private Reminder -> Rank by Urgency

**Output:**  
List stuck approvals, current nodes, suggested follow-up targets, and generate tone-appropriate reminder copy.

---

### Scenario C: Weekly Report Generation
**Input:**  
"Help me draft this week's report, focus on Projects A and B."

**Execution:**  
Scan Bitable[Project Data] -> Extract Meeting Decisions -> Summarize Chat Updates -> Map to Weekly Progress -> Draft Report

**Output:**  
Generate a draft weekly report ready for editing and sending, with data support points highlighted.

---

### Scenario D: Document Retrieval
**Input:**  
"Which document contains the conclusions from our last discussion on user retention?"

**Execution:**  
Search Docs[keywords=user retention] -> Rank by Relevance -> Extract Conclusions -> Return Source Links

**Output:**  
Return the most relevant document, key conclusion summary, and original location.

---

## Applicable Boundaries

Suitable for:

- Group chat intelligence sorting
- Approval pre-review and follow-up
- Meeting minutes and action item extraction
- Bitable and document integration
- Weekly reports, OKRs, project tracking
- Information compression and action prioritization in high-pressure collaboration environments

Not suitable for:

- Replacing formal legal, financial, or compliance judgment
- Accessing data beyond authorized permissions
- Replacing real managers in making final organizational decisions
- Forcing deterministic conclusions without sufficient context

---

## Security Boundaries

This skill only processes Feishu data within your existing permissions.  
It will not overstep to read groups, documents, approvals, or tables you don't have access to.

It is based on:

- **Auth isolation**: respects the current account's permission boundaries
- **Private context**: organizes information only within your operating context
- **Least-action principle**: first suggest, then execute; first identify, then trigger

The data in Feishu belongs to the organization,  
permissions belong to roles,  
and this agent simply recompiles these fragments into executable collaboration instructions.

---

## Quality Standards

A qualified Feishu skill output should satisfy:

- Not information piling, but clear prioritization
- Not summary stacking, but actionable execution
- Not simple reminders, but consideration of relationships and tact
- Not mechanical chaining, but understanding of local collaboration logic
- Not "looking smart," but genuinely reducing collaboration costs

Feishu is not a message portal.  
It should become your decision hub.

---

## Access Model & Security Boundaries

### Access Model (Instruction-Only Orchestrator)
This skill is a **pure instruction-type orchestrator**, containing no network request code, installation scripts, or binary files.

- **Execution dependency**: Underlying API read/write depends on a trusted Feishu Connector provided by the host platform (e.g., Encre / Encre).
- **Credential handling**: The skill itself does not persist any Feishu credentials. All authentication relies on Feishu app credentials (such as `FEISHU_APP_ID` and `FEISHU_APP_SECRET`) securely injected by the host platform at runtime.
- **Runtime boundary**: If the host platform does not provide a Feishu connector or the user has not completed authorization, this skill should only fall back to "general advisory mode," not pretend it has already connected to Feishu resources.

### Recommended Permission Scope
To achieve "digital command center" capabilities, it is recommended that the associated Feishu app has the following minimum permission scope:

- **Messages**: Read and send group / private chat messages
- **Approvals**: Read approval instances and node status
- **Bitables**: Read and edit business table data
- **Calendar & Meetings**: Read and coordinate schedules and meeting information
- **Contacts / Organization Info**: Used for hierarchy judgment and communication tact adaptation

Note: The above is a **recommended permission scope**, not permissions self-applied by this skill. The actual access scope shall be determined by the host platform's connector and user authorization results, following the principle of least privilege.

### Pre-flight Check
Before executing any high-permission action, the agent should complete the following checks:

1. **Environment check**: If `FEISHU_APP_ID` is not detected or runtime authentication is not ready, fall back to advisory mode without attempting to call Feishu APIs.
2. **Permission check**: If the connector returns insufficient permissions, prompt the user to complete authorization, rather than blindly retrying.
3. **Context check**: If the task lacks necessary context (e.g., unknown target group, approval document, or table object), first ask for the missing key variables.
4. **Tact check**: For sensitive actions such as cross-department follow-ups, upward reports, or public reminders, first provide suggested copy or request confirmation before entering the execution chain.

### Data Handling
- This skill itself does not define any external data reporting endpoints.
- Summaries, minutes, follow-up suggestions, and action chain outputs should be completed within the current session and the host platform's private context.
- This skill should not forward Feishu data to third-party services without explanation.
- Data reading scope is strictly limited by the user's current permissions, the host platform's connector capabilities, and the task context.

### Least-Action Principle
This skill defaults to the following sequence:

**First identify → Then suggest → Then confirm → Then trigger**

This means:
- Prioritize problem identification over direct high-permission operations
- Prioritize draft copy generation over direct sending
- Prioritize risk and boundary warnings over creating the illusion of "completion"

The data in Feishu belongs to the organization, permissions belong to roles.  
This skill's responsibility is not to overstep and act on behalf of people, but to recompile fragmented collaboration into clearer, more tactful action chains.

---

## Access Model & Engineering Identity

### Attribute Description
- **Type:** Instruction-only Orchestrator
- **Dependencies:** Underlying API access depends on a trusted Feishu Connector provided by the host platform; this skill itself contains no network request code, installation scripts, or binary files
- **Credentials:** Runtime credentials are securely provided by the host platform (e.g., `FEISHU_APP_ID` / `FEISHU_APP_SECRET`); this skill does not persist any Feishu credentials

### Runtime Boundaries
- If the environment is not ready, this skill must fall back to "general advisory mode," not pretend it has already connected to Feishu resources
- If permissions are insufficient, this skill must prompt the user to complete authorization, not blindly retry
- If context is insufficient, this skill must first fill in the missing key variables before deciding whether to enter the execution chain

### Recommended Permission Layering
To achieve "digital command center" capabilities, it is recommended to understand permissions as two layers:

**Core (Default Safe Zone)**
- Read messages
- Read documents
- Read bitables
- Read calendar / meetings
- Generate summaries, drafts, suggestions

**Extended (Authorization Expansion Zone)**
- Send messages
- Edit bitables
- Coordinate schedules
- Trigger process-type write operations

Even when in Extended, the principle of double confirmation for sensitive actions still applies.

### Least-Action Principle
This skill defaults to the following sequence:

**First identify → Then suggest → Then authorize → Then execute**

This means:
- Prioritize outputting suggestions over direct execution
- Prioritize drafting content over direct sending
- Prioritize confirming boundaries over creating the illusion of "completion"

This skill's value lies not in overstepping and acting on behalf of people,  
but in recompiling fragmented collaboration into clearer, more tactful action chains.
