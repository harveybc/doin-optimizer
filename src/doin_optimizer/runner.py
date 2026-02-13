"""Optimization runner — loads plugins and runs the optimization loop.

The runner:
1. Loads the optimization plugin for a domain
2. Fetches current best parameters from the network
3. Runs optimization steps in a loop
4. When improvement is found, submits optimae to a node
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from doin_core.crypto.identity import PeerIdentity
from doin_core.models.optimae import Optimae
from doin_core.plugins.base import OptimizationPlugin
from doin_core.plugins.loader import load_optimization_plugin
from doin_core.protocol.messages import Message, MessageType, OptimaeAnnouncement

logger = logging.getLogger(__name__)


class NoImprovementError(Exception):
    """Raised when an optimization step produces no improvement."""


@dataclass
class OptimizerConfig:
    """Configuration for the optimizer."""

    domain_id: str
    plugin_name: str
    plugin_config: dict[str, Any] = field(default_factory=dict)
    node_endpoint: str = "localhost:8470"
    optimization_interval: float = 1.0  # seconds between optimization steps
    max_steps: int | None = None  # None = run forever


class OptimizationRunner:
    """Runs the optimization loop for a single domain.

    Loads the configured optimization plugin, repeatedly runs optimization
    steps, and submits improvements to the network via a connected node.
    """

    def __init__(
        self,
        config: OptimizerConfig,
        identity: PeerIdentity | None = None,
    ) -> None:
        self.config = config
        self.identity = identity or PeerIdentity.generate()
        self._plugin: OptimizationPlugin | None = None
        self._session: ClientSession | None = None
        self._running = False
        self._steps_completed = 0
        self._improvements_found = 0

        # Track current best
        self._current_best_params: dict[str, Any] | None = None
        self._current_best_performance: float | None = None

    @property
    def peer_id(self) -> str:
        return self.identity.peer_id

    def load_plugin(self) -> None:
        """Load and configure the optimization plugin."""
        plugin_cls = load_optimization_plugin(self.config.plugin_name)
        self._plugin = plugin_cls()
        self._plugin.configure(self.config.plugin_config)
        logger.info(
            "Loaded optimization plugin: %s for domain %s",
            self.config.plugin_name,
            self.config.domain_id,
        )

    def set_plugin(self, plugin: OptimizationPlugin) -> None:
        """Directly set an optimization plugin (for testing or manual setup)."""
        self._plugin = plugin

    async def start(self) -> None:
        """Start the optimization loop."""
        if self._plugin is None:
            raise RuntimeError("Plugin not loaded — call load_plugin() or set_plugin() first")

        self._session = ClientSession(timeout=ClientTimeout(total=30))
        self._running = True

        logger.info(
            "Optimizer starting: domain=%s, node=%s",
            self.config.domain_id,
            self.config.node_endpoint,
        )

        try:
            while self._running:
                if self.config.max_steps and self._steps_completed >= self.config.max_steps:
                    logger.info("Max steps reached (%d)", self.config.max_steps)
                    break

                await self._optimization_step()
                self._steps_completed += 1
                await asyncio.sleep(self.config.optimization_interval)
        finally:
            if self._session:
                await self._session.close()

    async def stop(self) -> None:
        """Stop the optimization loop."""
        self._running = False

    async def run_single_step(self) -> Optimae | None:
        """Run a single optimization step (for testing/manual use).

        Returns:
            Optimae if improvement found, None otherwise.
        """
        if self._plugin is None:
            raise RuntimeError("Plugin not loaded")

        return await self._optimization_step()

    async def _optimization_step(self) -> Optimae | None:
        """Execute one optimization step."""
        assert self._plugin is not None

        try:
            new_params, new_performance = self._plugin.optimize(
                self._current_best_params,
                self._current_best_performance,
            )
        except NoImprovementError:
            return None
        except Exception:
            logger.exception("Optimization step failed")
            return None

        # Check if this is actually an improvement
        if self._current_best_performance is not None:
            metadata = self._plugin.get_domain_metadata()
            higher_is_better = metadata.get("higher_is_better", True)
            if higher_is_better and new_performance <= self._current_best_performance:
                return None
            if not higher_is_better and new_performance >= self._current_best_performance:
                return None

        # Create optimae
        increment = 0.0
        if self._current_best_performance is not None:
            increment = abs(new_performance - self._current_best_performance)

        optimae = Optimae(
            domain_id=self.config.domain_id,
            optimizer_id=self.peer_id,
            parameters=new_params,
            reported_performance=new_performance,
            performance_increment=increment,
        )

        # Update local best
        self._current_best_params = new_params
        self._current_best_performance = new_performance
        self._improvements_found += 1

        # Submit to network
        await self._submit_optimae(optimae)

        logger.info(
            "Improvement found! domain=%s performance=%.6f increment=%.6f (step %d)",
            self.config.domain_id,
            new_performance,
            increment,
            self._steps_completed,
        )

        return optimae

    async def _submit_optimae(self, optimae: Optimae) -> bool:
        """Submit an optimae to the connected node."""
        if not self._session:
            logger.warning("No session — cannot submit optimae")
            return False

        announcement = OptimaeAnnouncement(
            domain_id=optimae.domain_id,
            optimae_id=optimae.id,
            parameters=optimae.parameters,
            reported_performance=optimae.reported_performance,
            previous_best_performance=self._current_best_performance,
        )

        message = Message(
            msg_type=MessageType.OPTIMAE_ANNOUNCEMENT,
            sender_id=self.peer_id,
            payload=json.loads(announcement.model_dump_json()),
        )

        url = f"http://{self.config.node_endpoint}/message"
        try:
            async with self._session.post(
                url,
                json=json.loads(message.model_dump_json()),
            ) as resp:
                success = resp.status == 200
                if not success:
                    logger.warning("Failed to submit optimae: HTTP %d", resp.status)
                return success
        except Exception:
            logger.debug("Failed to submit optimae to %s", url, exc_info=True)
            return False

    @property
    def stats(self) -> dict[str, Any]:
        """Current optimizer statistics."""
        return {
            "domain_id": self.config.domain_id,
            "peer_id": self.peer_id[:12],
            "steps_completed": self._steps_completed,
            "improvements_found": self._improvements_found,
            "current_best_performance": self._current_best_performance,
        }
