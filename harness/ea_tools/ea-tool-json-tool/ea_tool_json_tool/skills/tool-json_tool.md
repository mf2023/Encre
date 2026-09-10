---
name: tool-json_tool
description: "Validate, format, minify, transform, infer a schema from, or query JSON documents. Accepts input either as an inline 'data' string or via 'file_path'. Use this instead of piping through jq/python in bash -- it returns structured output and supports a dot-notation query language (e.g. 'data.items[0].name') and JSON-Schema-style type inference. Actions: 'validate' checks well-formedness; 'format' pretty-prints (and rewrites the file when given file_path); 'minify' removes whitespace (and rewrites the file); 'transform' renders a dict as key:value lines or a list as newline-delimited JSON; 'schema' infers a JSON-Schema-style type tree; 'query' resolves a dot-notation path. TIP: For format/minify on a file, the file is rewritten in place; pass 'data' instead to get the result without touching the file. AVOID: Querying huge JSON with deep paths -- extract the slice you need first."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# json_tool

Validate, format, minify, transform, infer a schema from, or query JSON documents. Accepts input either as an inline 'data' string or via 'file_path'. Use this instead of piping through jq/python in bash -- it returns structured output and supports a dot-notation query language (e.g. 'data.items[0].name') and JSON-Schema-style type inference. Actions: 'validate' checks well-formedness; 'format' pretty-prints (and rewrites the file when given file_path); 'minify' removes whitespace (and rewrites the file); 'transform' renders a dict as key:value lines or a list as newline-delimited JSON; 'schema' infers a JSON-Schema-style type tree; 'query' resolves a dot-notation path. TIP: For format/minify on a file, the file is rewritten in place; pass 'data' instead to get the result without touching the file. AVOID: Querying huge JSON with deep paths -- extract the slice you need first.
