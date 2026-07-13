---
name: tool-rest-client
description: REST/GraphQL client skill. method/url/headers/body/timeout, call APIs without bare curl
hidden: true
context: inline
---

## When to Use
- Call a REST or GraphQL API with a specific method, headers, and body
- Interact with an authenticated API endpoint
- Test an API you're building

## When NOT to Use
- **Fetch a URL to read content** -> `web_fetch` (simpler, no method/headers needed)
- **Search the web** -> `web_search`
- **Run a local command** -> `bash`

## Key Parameters
- `method` (required): HTTP method (GET, POST, PUT, PATCH, DELETE)
- `url` (required): full endpoint URL
- `headers`: request headers (auth, content-type)
- `body`: request body (JSON or other)
- `timeout`: seconds before abort

## Best Practices
- Set the right `Content-Type`/`Accept` headers
- Put auth in headers, not the URL
- Set a `timeout`; network calls can hang

## Common Pitfalls / Anti-patterns
- **Using curl in bash**: this tool handles method/headers/body parsing and safety; bare curl in bash bypasses it
- **No timeout**: a hung network call blocks the turn forever. Always set `timeout`
- **Leaking secrets in the URL**: auth tokens in the URL get logged and cached. Put auth in `headers` (Authorization header), never the URL
- **Wrong Content-Type**: a JSON body sent without `Content-Type: application/json` is rejected or misparsed by most APIs. Match the header to the body
- **Ignoring the response status**: a 200 with an error body, or a 4xx you treated as success. Always check the status code, not just that a response came back

## Pairing with Other Tools
- `web_fetch`: simple content fetch without API semantics
- `web_search`: discover API endpoints/docs
