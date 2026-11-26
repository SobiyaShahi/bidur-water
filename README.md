# Post-flood water-quality monitoring, Bidur (ITS67404 Task 3)
Group No.: __   Members: Sobiya Shahi (ID __), Riddhishree Khanal (ID __),
Liza Shrestha (ID __), Ritik Budhathoki (ID __)

## Install
Python 3.10+.
    python -m venv .venv
    (Windows) .venv\Scripts\activate    (macOS/Linux) source .venv/bin/activate
    pip install -r requirements.txt
    copy config/nodes.example.json config/nodes.json
    copy .env.example .env

Put each ThingsBoard device token in the matching variable in `.env`. Keep the
tokens out of `config/nodes.json`; its `token_env` entries identify which
environment variable supplies each node's token. `.env` is ignored by Git.

## Run
    python main.py --help
    python main.py --dry-run                       # models + scenario only
    python main.py --log-file logs/run.log         # full system
Keys: e rain event, 1/2/3 rain on one node, i supply interruption, o toggle outage,
s status, q quit. Scripted events: scenarios/demo_scenario.json.

## Checks
    python tests/test_model.py
    python tools/plot_model.py --save event_curves.png