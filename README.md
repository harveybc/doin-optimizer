# doin-optimizer

Standalone optimizer client for DOIN (Decentralized Optimization and Inference Network).

## What It Does

`doin-optimizer` is a standalone optimization runner that connects to a DOIN node and submits improvements. It:

1. Loads an optimization plugin for a domain (via entry points)
2. Fetches current best parameters from the network
3. Runs optimization steps in a loop
4. When improvement is found, creates an optimae and submits it to a connected node
5. Tracks local best and only submits genuine improvements

This is the **headless optimizer** — useful when you want to run optimization separately from the node process, e.g., on a dedicated GPU machine.

## Install

```bash
pip install git+https://github.com/harveybc/doin-core.git
pip install git+https://github.com/harveybc/doin-optimizer.git
```

## Usage

```bash
doin-optimizer --domain quadratic --plugin quadratic --node localhost:8470
```

### Programmatic Usage

```python
from doin_optimizer.runner import OptimizationRunner, OptimizerConfig

config = OptimizerConfig(
    domain_id="quadratic",
    plugin_name="quadratic",
    node_endpoint="localhost:8470",
    optimization_interval=1.0,  # seconds between steps
    max_steps=100,              # None = run forever
)

runner = OptimizationRunner(config)
runner.load_plugin()
await runner.start()

# Or run a single step
optimae = await runner.run_single_step()
print(runner.stats)
```

### OptimizerConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `domain_id` | str | required | Domain to optimize |
| `plugin_name` | str | required | Entry point name of the optimization plugin |
| `plugin_config` | dict | `{}` | Plugin-specific configuration |
| `node_endpoint` | str | `localhost:8470` | Node to submit optimae to |
| `optimization_interval` | float | `1.0` | Seconds between optimization steps |
| `max_steps` | int \| None | `None` | Max steps before stopping (None = forever) |

## Three-Level Patience System

When using the predictor plugin, optimization involves three patience levels:

| Level | Name | Config Key | Controls | Default |
|-------|------|------------|----------|---------|
| **L1** | Candidate Training | `early_patience` | Epochs without val_loss improvement before stopping one candidate's training | 80–100 |
| **L2** | Stage Progression | `optimization_patience` | Generations without best-fitness improvement before advancing to next GA stage | 8–10 |
| **L3** | Meta-Optimizer | *(not yet implemented)* | Network-level predictor trained on (params→performance) from OLAP data | — |

## Architecture

The optimizer is stateless beyond its current best. It:
- Generates a `PeerIdentity` (ed25519 keypair) on startup
- Calls `plugin.optimize(current_best_params, current_best_performance)` each step
- Checks improvement direction via `plugin.get_domain_metadata()["higher_is_better"]`
- Wraps improvements as `Optimae` objects and POSTs them to the node's `/message` endpoint
- The node handles commit-reveal, quorum verification, and chain inclusion

## Tests

```bash
python -m pytest tests/ -v
# 5 tests passing
```

## Part of DOIN

- [doin-core](https://github.com/harveybc/doin-core) — Consensus, models, crypto
- [doin-node](https://github.com/harveybc/doin-node) — Unified node
- [doin-evaluator](https://github.com/harveybc/doin-evaluator) — Standalone evaluator
- [doin-plugins](https://github.com/harveybc/doin-plugins) — Domain plugins

## License

MIT
