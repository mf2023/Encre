---
name: tool-database
description: Database query skill. sql/database_url/limit, run SQL without bare sqlite3/psql
hidden: true
context: inline
---

## When to Use
- Run SQL queries against a database (SQLite, Postgres, MySQL, etc.)
- Inspect or modify data during debugging or data tasks

## When NOT to Use
- **Run bare `sqlite3`/`psql`/`mysql` in bash** -> use this tool
- **Call a REST API** -> `rest_client`
- **Read a CSV/file** -> `file_read`/`spreadsheet`

## Key Parameters
- `sql` (required): the SQL statement
- `database_url`: connection string; defaults to the configured database
- `limit`: max rows returned (prevents huge result sets)

## Best Practices
- Always set `limit` for SELECT queries to avoid pulling huge result sets
- Read-only first to inspect; write only when confirmed
- Prefer parameterized queries when the tool supports them to avoid injection

## Common Pitfalls / Anti-patterns
- **SELECT without limit**: can return enormous results; set `limit`
- **Using bash for DB queries**: use this tool for connection handling and result parsing
- **Trusting user input in SQL**: SQL injection risk; sanitize/parameterize
- **Forgetting WHERE clause on DELETE/UPDATE** - an UPDATE or DELETE without WHERE hits every row. Double-check the query before executing destructive operations.
- **Assuming results are in insertion order** - without ORDER BY, row order is undefined. Always specify ORDER BY if the order matters to your logic.

## Pairing with Other Tools
- `spreadsheet`: export/import tabular data
- `rest_client`: if the data lives behind an API
