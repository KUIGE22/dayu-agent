# Cross-Platform Continuation Guide

Use this guide when continuing the dual-model workflow from another computer, operating system, or GitHub account.

## GitHub Continuation

Clone the fork and switch to the workflow branch:

```bash
git clone https://github.com/KUIGE22/dayu-agent.git
cd dayu-agent
git checkout codex/dual-model-research-mvp
git log -1 --oneline
```

If the operator uses another GitHub account without write access to `KUIGE22/dayu-agent`, fork the repository under that account and keep the upstream remote available for comparison:

```bash
git remote rename origin upstream
git remote add origin https://github.com/<account>/dayu-agent.git
git push -u origin codex/dual-model-research-mvp
```

## macOS / Linux Setup

Create a repository-local Python 3.11 environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[test,dev,browser,web]"
```

If the platform has a lock file, install with the matching constraint file before running workflow gates.

## Windows Setup

Create a repository-local Python 3.11 environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[test,dev,browser,web]"
```

Use the matching Windows constraint file when reproducing packaged dependency sets.

## Required Gate Commands

Run the machine-readable gates before assigning work to DeepSeek or asking Codex to continue a review:

```bash
python -m utils.validate_handoff_docs --json
python -m utils.codex_review_gate --allow-waiting --json
python -m utils.dual_model_pipeline_check --json
```

All three commands should report clean JSON before a new implementation task starts.

## Local Path Rules

Do not reuse absolute local paths from another computer.

Use repository-relative paths in task specs, required-reading lists, allowed scopes, forbidden scopes, changed-file evidence, and verification command path lists. Windows paths such as `F:\...` and macOS paths such as `/Users/...` belong in operator notes only, not in DeepSeek task contracts.

After cloning on a new machine, derive the active repository root with:

```bash
pwd
```

or on Windows:

```powershell
(Get-Location).Path
```

Then rerun the required gate commands from that root.
