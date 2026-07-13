---
name: tool-notebook
description: Jupyter notebook skill. action/code/cell_id/cell_type/kernel_name, execute and edit notebooks
hidden: true
context: inline
---

## When to Use
- Execute Jupyter notebook cells
- Read/insert/delete notebook cells
- Run notebook-based data analysis or experiments

## When NOT to Use
- **Run a Python script** -> `bash` (python script.py)
- **Run tests** -> `test_run`
- **Read a regular file** -> `file_read`

## Key Parameters
- `action` (required): the notebook action (run, read, insert, delete, etc.)
- `code`: cell code for run/insert
- `cell_id`: target an existing cell
- `cell_type`: code or markdown
- `timeout`: execution timeout
- `kernel_name`: kernel to use (e.g. python3)

## Best Practices
- Set a `timeout` for long-running cells
- Use `cell_id` to target specific cells rather than relying on position

## Common Pitfalls / Anti-patterns
- **No timeout on long cells**: a long-running or hung cell blocks the whole turn. Always set `timeout` on execute actions
- **Running a script via notebook**: a plain `.py` script is simpler and faster; use `bash python script.py`. Notebooks are for iterative, cell-based work
- **Hidden state across cells**: variables set in an earlier cell persist in the kernel; a cell that "works" depends on prior state. Re-run from the top to confirm the notebook is self-contained
- **Inserting by position instead of cell_id**: positions shift as cells are added/deleted. Use `cell_id` to target reliably

## Pairing with Other Tools
- `file_read`/`file_write`: for non-notebook files
- `bash`: run scripts outside notebooks
