# Encre Benchmarks

This directory contains a minimal benchmark harness for measuring real-agent task execution quality over time.

## Files

- `runner.py`: executes a JSON task suite against an `EncreAgent`
- `sample_tasks.json`: small starter suite for local validation

## Usage

```powershell
python backend/benchmarks/runner.py `
  --tasks backend/benchmarks/sample_tasks.json `
  --output backend/benchmarks/results.json `
  --model your-model-id `
  --backend openai `
  --workspace D:\encre
```

## Output

The runner writes a JSON report with:

- per-task duration
- finish reason
- final assistant text
- tool call count
- turn count
- final task stage
- stuck event count
- delegation count
- artifact count
- basic pass/fail heuristics

This is intentionally lightweight so we can iterate on evaluation logic before building a larger benchmark system.
