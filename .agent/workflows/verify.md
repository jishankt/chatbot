---
description: Run pytest suite and the CX-02 evaluation benchmark
---

# Verify Workflow

This workflow runs all unit tests and executes the full evaluation benchmark suite.

```bash
# 1. Run pytest test suite
venv/bin/pytest tests/ -v

# 2. Run CX-02 evaluation benchmark
venv/bin/python eval/run_eval.py
```
