"""Tests for the optimization runner."""

from typing import Any

import pytest

from doin_core.plugins.base import OptimizationPlugin
from doin_optimizer.runner import OptimizationRunner, OptimizerConfig


class MockOptimizer(OptimizationPlugin):
    """A simple mock optimizer that increments performance each step."""

    def __init__(self) -> None:
        self._step = 0
        self._configured = False

    def configure(self, config: dict[str, Any]) -> None:
        self._configured = True

    def optimize(
        self,
        current_best_params: dict[str, Any] | None,
        current_best_performance: float | None,
    ) -> tuple[dict[str, Any], float]:
        self._step += 1
        performance = 0.5 + self._step * 0.05
        params = {"w": self._step, "bias": 0.1 * self._step}
        return params, performance

    def get_domain_metadata(self) -> dict[str, Any]:
        return {"performance_metric": "accuracy", "higher_is_better": True}


class MockNoImprovementOptimizer(OptimizationPlugin):
    """A mock optimizer that always returns the same performance."""

    def configure(self, config: dict[str, Any]) -> None:
        pass

    def optimize(
        self,
        current_best_params: dict[str, Any] | None,
        current_best_performance: float | None,
    ) -> tuple[dict[str, Any], float]:
        return {"w": 1}, 0.5

    def get_domain_metadata(self) -> dict[str, Any]:
        return {"performance_metric": "accuracy", "higher_is_better": True}


class TestOptimizationRunner:
    def _make_runner(self) -> OptimizationRunner:
        config = OptimizerConfig(
            domain_id="test-domain",
            plugin_name="mock",
            node_endpoint="localhost:9999",
        )
        runner = OptimizationRunner(config)
        runner.set_plugin(MockOptimizer())
        return runner

    @pytest.mark.asyncio
    async def test_single_step_first_improvement(self) -> None:
        runner = self._make_runner()
        result = await runner.run_single_step()
        assert result is not None
        assert result.domain_id == "test-domain"
        assert result.reported_performance == 0.55
        assert result.parameters == {"w": 1, "bias": 0.1}

    @pytest.mark.asyncio
    async def test_multiple_steps_track_improvements(self) -> None:
        runner = self._make_runner()

        r1 = await runner.run_single_step()
        assert r1 is not None
        assert r1.reported_performance == 0.55

        r2 = await runner.run_single_step()
        assert r2 is not None
        assert r2.reported_performance == 0.60
        assert r2.performance_increment == pytest.approx(0.05, abs=1e-6)

    @pytest.mark.asyncio
    async def test_no_improvement_returns_none(self) -> None:
        config = OptimizerConfig(
            domain_id="test-domain",
            plugin_name="mock",
        )
        runner = OptimizationRunner(config)
        runner.set_plugin(MockNoImprovementOptimizer())

        # First step — initial result, counts as improvement
        r1 = await runner.run_single_step()
        assert r1 is not None

        # Second step — same performance, no improvement
        r2 = await runner.run_single_step()
        assert r2 is None

    @pytest.mark.asyncio
    async def test_stats(self) -> None:
        runner = self._make_runner()
        await runner.run_single_step()
        await runner.run_single_step()

        stats = runner.stats
        assert stats["domain_id"] == "test-domain"
        assert stats["improvements_found"] == 2
        assert stats["current_best_performance"] == 0.60

    @pytest.mark.asyncio
    async def test_plugin_not_loaded_raises(self) -> None:
        config = OptimizerConfig(domain_id="d1", plugin_name="x")
        runner = OptimizationRunner(config)
        with pytest.raises(RuntimeError, match="Plugin not loaded"):
            await runner.run_single_step()
