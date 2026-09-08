# FinConfigCalc Project Guidelines

## Python Environment

This repository uses the Conda-style Python environment located at `.venv`.

On Windows, always run Python through:

```powershell
.\.venv\python.exe
```

Run tests with:

```powershell
.\.venv\python.exe -m pytest
```

Do not use the system `python`, a globally installed `pytest`, or
`.\.venv\Scripts\python.exe`. The interpreter for this repository is located
directly at `.venv\python.exe`.

## Project Conventions

Follow the project coding standards in `docs/coding-standards.md` and the
project overview in `README.md`.
