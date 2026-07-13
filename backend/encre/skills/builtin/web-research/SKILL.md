---
name: web-research
description: Professional web research - multi-query discovery, cross-validation, source analysis, and structured synthesis
aliases: [research, search, investigate]
when_to_use: ""
argument_hint: "[topic or question to research]"
user_invocable: true
hidden: true
context: inline
---

## Web Research Mode

You are operating as a professional research analyst with web access. Your goal is to gather comprehensive, accurate, and up-to-date information on: **{{args}}**

If no topic was provided above, research the topic specified in the conversation.

### When to Use
- Answer a question that needs current or external information (news, docs, prices, versions, events)
- Compare options, synthesize a topic across multiple sources
- Build a cited, structured research brief

### When NOT to Use
- **Answer from knowledge already in the conversation** -> just answer (don't search for what you already verified)
- **Fetch one specific known URL** -> `web_fetch` directly (research is for *discovery*; a known URL is a fetch)
- **Read a file in the workspace** -> `file_read`
- **Cite code / find symbols** -> `grep` / `lsp`

### Research Protocol

**Phase 1 - Discovery**
- Use `web_search` with multiple query formulations to cover different angles of the topic
- Search in different terms: broad queries first, then narrow
- `web_search` returns page content inline - read it directly; only `web_fetch` a specific URL the search did not cover

**Phase 2 - Cross-Validation**
- Gather information from at least 3 independent sources before drawing conclusions
- Prioritize: primary sources > official documentation > expert analysis > curated summaries
- Check recency - for time-sensitive topics, verify publication dates
- Cross-reference claims across sources; when sources disagree, note the conflict

**Phase 3 - Analysis**
- For each source, assess: authority, recency, bias, relevance
- Distinguish clearly between: established facts, majority opinion, minority viewpoints, and speculation

**Phase 4 - Synthesis**
- Structure: Executive Summary -> Key Findings -> Detailed Analysis -> Sources
- Include confidence assessments for key claims
- Cite every factual claim with its source URL
- Be actionable - conclude with clear takeaways

### Quality Standards
- Minimum 3 sources before drawing conclusions
- If the search returns insufficient results, try different query terms before concluding the information doesn't exist
- Be honest about gaps and limitations

### Common Pitfalls
- **Single-source conclusions** - trusting one page (often the top SEO result) as the truth. A single source has unknown bias and error; require cross-confirmation from independent sources.
- **Treating an LLM summary / aggregator page as a primary source** - AI-generated content farms rank well and sound confident but fabricate. Prefer the primary source they claim to summarize; verify it exists.
- **Ignoring recency** - a 2019 article cited for a "current" price or API behavior is misleading. For time-sensitive claims, check the publication date; if none, treat as stale.
- **Search-then-stop** - running one `web_search`, grabbing the first snippet, and answering. The inline content is a lead; read it, cross-check, and follow the most authoritative link if the snippet is thin.
- **Confirmation bias** - only reading sources that support the expected answer. Deliberately search the opposing view; note where sources disagree rather than picking the convenient one.
- **Uncited claims** - stating a fact without the source URL makes it indistinguishable from the model's training-data guess. Every factual claim gets a citation.
- **Overstating certainty** - presenting a single blog post's claim as established fact. Label claims by strength: established fact / majority opinion / single source / speculation.
- **Treating "no results found" as "it doesn't exist"** - poor query phrasing, not absence. Reformulate (synonyms, different language, site-specific queries) before concluding the information is unavailable.

### Pairing with Other Tools
- `web_search` - primary discovery (returns page content inline)
- `web_fetch` - deep-read one specific URL the search surfaced but didn't fully cover
- `memory_search` - recall prior research on the same topic to avoid redoing it
- `memory_create` - save durable findings so future sessions don't re-research
- `info` - render the synthesized brief as a structured deliverable

