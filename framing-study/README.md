# framing-study

This is a study on pinned RedlineBench, not an official reproduction.

The prior `framing-experiment/` directory is a different draft and is not this study.

Code pin: [crosbylegal/redline-bench](https://github.com/crosbylegal/redline-bench) at `b29d1113af5d98e2d577f4f17673ebb72834f107` (MIT). Dataset pin: `crosbylegal/RedlineBench` at `eee1b6790982ed1279e86bec7616b662a61993e6` (CC-BY-4.0). Harbor `0.25.0` runs the `terminus-2` agent.

## Conditions

The study has four conditions:

- `STOCK`
- `STOCK_PLUS_METAPHOR`
- `MATCHED_SOFTWARE_REPLACEMENT`
- `TASK_ONLY`

The primary comparison is matched software replacement vs stock (`MATCHED_SOFTWARE_REPLACEMENT` vs `STOCK`).

## Limits

Residual coaching and the uncontrolled Harbor system prompt are limits of this study.

Prices are user-supplied in `config/pilot.yaml`. The study does not invent prices.

## Credentials and spend

Live model calls are blocked until provider keys are in the environment and an explicit `--spend-limit` is passed.

Named environment variables:

- `OPENAI_API_KEY`, or `OPENROUTER_API_KEY` when the native `openai/gpt-5.4-mini` id is reached through OpenRouter
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_GENERATIVE_AI_API_KEY`

Set those variables in the environment yourself. Do not paste keys into chat. Do not set `OPENAI_API_BASE`: a global base also redirects Anthropic. The child process aliases only `openai/gpt-5.4-mini` to OpenRouter and leaves the other two providers on their own endpoints.

The task image also installs `tmux` and `asciinema`. Terminus-2 needs them after the network lock, so they cannot be fetched with apt inside the running container. That addition is the same for every condition.

This README has no results table. `results/not_executed.json` stays free of model scores until a run finishes.

## Install

Run these commands from `framing-study/`:

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pip install "harbor==0.25.0"
sudo apt-get update && sudo apt-get install -y docker.io
```

`harbor==0.25.0` is a separate install from the study package. `docker.io` installs the Docker engine and CLI that Harbor uses to run task containers.

The optional `benchmark` extra is a PEP 508 git pin of RedlineBench at the code SHA. Install it only when you need that package:

```bash
.venv/bin/pip install -e ".[benchmark]"
```

The same pin as a direct pip install:

```bash
.venv/bin/pip install "redlinebench @ git+https://github.com/crosbylegal/redline-bench.git@b29d1113af5d98e2d577f4f17673ebb72834f107"
```

Activate the virtualenv before the commands below:

```bash
source .venv/bin/activate
```

## Commands

Fetch the pinned dataset:

```bash
python -m framing_study fetch
```

Inspect instruction variants:

```bash
python -m framing_study instructions --out exports/instructions
```

Check endpoints:

```bash
python -m framing_study preflight
```

Preview cost from the prices in `config/pilot.yaml`:

```bash
python -m framing_study cost
```

Smoke (`s2-t1-g01` / `redline-s2-t1-g01a`):

```bash
python -m framing_study smoke --spend-limit 5
```

Pilot (six pinned groups):

```bash
python -m framing_study pilot --spend-limit 25
```

Resume is the same pilot command. The cache and the saved manifest supply completed work, so this continues a pilot:

```bash
python -m framing_study pilot --spend-limit 25
```

Reports:

```bash
python -m framing_study report
python -m framing_study blind
```

## What not to commit

Do not commit `.cache`, `runs`, or secrets (including `*.key.json`). Those paths are listed in `.gitignore`.
