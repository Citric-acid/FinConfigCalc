---
name: release-fin-config-calc
description: Automate a FinConfigCalc release by setting a new version, validating changes, committing and pushing, then building the Windows EXE.
---

# Release FinConfigCalc

Use this skill when the user asks to release, publish, bump the version, or package a
new FinConfigCalc iteration.

## Required input

Obtain an explicit stable version in `X.Y.Z` format. If the user did not provide one,
read the current version from `src/fin_config_calc/__init__.py` (`__version__`) and
ask for the new version with `ask_user`. Do not infer whether the change is major,
minor, or patch.

## Procedure

1. Run `git status --short`, `git diff --stat`, and `git diff --cached --stat`.
2. Review the paths that will be committed. The release script stages all tracked and
   untracked iteration changes. Stop and ask the user if unrelated files, likely
   secrets, unresolved conflicts, or generated artifacts are present.
3. Based on the reviewed changes, generate a concise Conventional Commit-style summary,
   such as `feat: add allocation preview`, `fix: handle empty mappings`, or
   `style: clarify release documentation`. Show the proposed summary to the user and
   wait for explicit confirmation. Revise and reconfirm if requested; do not start the
   release script before confirmation.
4. From the repository root, run with the exact confirmed summary:

   ```powershell
   .\.venv\python.exe scripts\release.py <version> --summary "<confirmed summary>"
   ```

5. Do not separately edit the version file, commit, push, or invoke PyInstaller. The
   script owns the ordered workflow and stops on the first failure.
6. Report the released version, pushed commit and branch, and the complete
   `dist\FinConfigCalc-<version>` directory that must be distributed.

## Workflow guarantees

The script:

- requires the repository-local `.venv\python.exe`;
- accepts only a version greater than the current package version in `__init__.py`;
- updates `src\fin_config_calc\__init__.py`, the single version source;
- refreshes editable package metadata and build dependencies;
- runs pytest when tests exist, then Ruff lint/format checks and Pyright;
- creates a `release v<version>: <confirmed summary>` commit containing the current
   iteration;
- pushes the current branch, setting its `origin` upstream when needed;
- builds only after the push succeeds;
- verifies `dist\FinConfigCalc-<version>\FinConfigCalc.exe` exists.

If any command fails, surface the exact failed phase. Never claim the release
completed unless the release command exits successfully and the expected versioned
EXE exists. The `发布完成` line is informative, not required when terminal output is
truncated. Do not infer success from file existence alone because it could be a stale
artifact from an earlier attempt.

## Important behavior

- This process does not create a Git tag or GitHub Release.
- A failure before commit leaves the version edit in the working tree for diagnosis.
- A failure after commit or push does not rewrite Git history. Fix the build cause,
  then rerun the documented PyInstaller command from that pushed commit; use a new
  version only when the fix requires another commit.
- Distribute the whole versioned directory, not only `FinConfigCalc.exe`.
