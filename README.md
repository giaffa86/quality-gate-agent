# Quality Gate Agent

Quality Gate Agent turns a failed quality gate into a small, reviewable AI remediation plan.

The first implementation focuses on SonarQube/SonarCloud:

- fetch issues from the Sonar Web API or read an exported JSON response
- classify issues as `safe`, `review`, or `risky`
- select a bounded set of low-risk candidates
- generate a Markdown report and prompt pack for coding agents such as Codex, Claude Code, Aider, or OpenHands

It does not try to replace SonarQube. It adds a workflow layer above it so an agent can work in small, controlled batches.

## Quick Start

Run against the bundled sample response:

```powershell
$env:PYTHONPATH = "src"
python -m quality_gate_agent plan `
  --issues-file examples/sample-sonar-response.json `
  --project-key my-service `
  --branch feature/orders `
  --severity MAJOR,CRITICAL `
  --language java `
  --max-issues 5 `
  --out reports/sample-plan.md
```

The generated report includes selected candidates, skipped issues, reviewer focus, and an agent prompt pack.

## Fetch From SonarQube

```powershell
$env:SONAR_TOKEN = "<token>"
$env:PYTHONPATH = "src"
python -m quality_gate_agent plan `
  --sonar-url https://sonarqube.example.com `
  --project-key my-service `
  --branch feature/orders `
  --severity MAJOR,CRITICAL `
  --language java `
  --max-issues 5 `
  --out reports/quality-gate-plan.md
```

For SonarCloud, pass `--organization` when your project requires it.

## CLI

```text
qga plan [source] [filters] [output]
```

Sources:

- `--issues-file PATH`: read a Sonar `/api/issues/search` JSON response
- `--sonar-url URL --project-key KEY`: fetch issues and quality gate status from Sonar

Filters:

- `--severity MAJOR,CRITICAL`
- `--type CODE_SMELL,BUG`
- `--rule java:S1192,java:S1854`
- `--language java`
- `--max-issues 5`
- `--include-review`: allow medium-risk review candidates in the selected batch

Output:

- `--out PATH`: write Markdown report
- `--json-out PATH`: write machine-readable plan JSON
- `--print`: also print the Markdown report to stdout

## Development

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests
python -m compileall src
```

