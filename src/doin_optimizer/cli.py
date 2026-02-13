"""CLI entry point for running a DON optimizer."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

from doin_core.crypto.identity import PeerIdentity

from doin_optimizer.runner import OptimizationRunner, OptimizerConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a DON optimizer for a specific domain",
    )
    parser.add_argument("--domain-id", required=True, help="Domain ID to optimize")
    parser.add_argument("--plugin", required=True, help="Optimization plugin name")
    parser.add_argument("--plugin-config", default=None, help="Plugin config JSON file")
    parser.add_argument("--node", default="localhost:8470", help="Node endpoint")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between steps")
    parser.add_argument("--max-steps", type=int, default=None, help="Max optimization steps")
    parser.add_argument("--key-file", default=None, help="PEM private key file")
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


async def run_optimizer(args: argparse.Namespace) -> None:
    plugin_config = {}
    if args.plugin_config:
        plugin_config = json.loads(Path(args.plugin_config).read_text())

    identity = None
    if args.key_file:
        identity = PeerIdentity.from_file(args.key_file)

    config = OptimizerConfig(
        domain_id=args.domain_id,
        plugin_name=args.plugin,
        plugin_config=plugin_config,
        node_endpoint=args.node,
        optimization_interval=args.interval,
        max_steps=args.max_steps,
    )

    runner = OptimizationRunner(config, identity)
    runner.load_plugin()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(runner.stop()))

    await runner.start()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_optimizer(args))


if __name__ == "__main__":
    main()
