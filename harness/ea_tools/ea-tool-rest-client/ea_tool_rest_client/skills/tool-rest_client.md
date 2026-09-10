---
name: tool-rest_client
description: "Make an HTTP request to a REST or GraphQL API endpoint and return the status code, headers, and parsed body."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# rest_client

Make an HTTP request to a REST or GraphQL API endpoint and return the status code, headers, and parsed body.

WHEN to use: call a documented REST/GraphQL API by its URL, integrate with a third-party service, or fetch a JSON resource that is not a human-readable web page.
WHEN NOT to use: for fetching a web page to read, use web_fetch (renders JS, strips boilerplate); for browser interactions (clicks, form fills, logins) use the browser tool.
TIPS: pass the body as a JSON string for JSON APIs and set the Content-Type header accordingly; JSON responses are auto-parsed and returned as a structured {status, headers, body} object.
PITFALLS: response bodies over 50K chars are truncated; non-GET methods (POST/PUT/PATCH/DELETE) are flagged as destructive -- make sure the user actually wants the side effect.
