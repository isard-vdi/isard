# SPDX-License-Identifier: AGPL-3.0-or-later

"""The blocking-read invariant for this consumer's own reads.

Sibling of ``isardvdi_common/connections/tests/test_redis_blocking.py``, which
owns the policy itself. Here the question is only whether THIS module's reads
go through it: a client whose socket deadline does not outlast its own block
raises ``TimeoutError`` on every idle read, and this consumer answers that by
tearing the connection down, which restarts the reclaim and trim clocks.
"""

import ast
import inspect

import pytest
from isardvdi_change_handler.streams import task_results_consumer as consumer
from isardvdi_common.connections import redis_blocking

BLOCKING_READ_METHODS = frozenset(
    {
        "blmove",
        "blmpop",
        "blpop",
        "brpop",
        "bzpopmax",
        "bzpopmin",
        "xread",
        "xreadgroup",
    }
)


def effective_socket_timeout(client):
    return client.connection_pool.make_connection().socket_timeout


def blocking_reads():
    """``block=None`` and a missing ``block=`` are the non-blocking forms of the
    same commands, and they carry no deadline to outlast."""
    found = []
    for node in ast.walk(ast.parse(inspect.getsource(consumer))):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in BLOCKING_READ_METHODS:
            continue
        block = next((kw.value for kw in node.keywords if kw.arg == "block"), None)
        if block is None or (isinstance(block, ast.Constant) and block.value is None):
            continue
        found.append((node.lineno, block))
    return found


class TestTheClientItReads:
    def test_the_socket_outlasts_the_block(self):
        assert effective_socket_timeout(consumer._stream_client()) > (
            consumer.BLOCK_MS / 1000.0
        )

    def test_the_block_is_the_shared_one(self):
        assert consumer.BLOCK_MS == redis_blocking.STREAM_BLOCK_MS


class TestEveryBlockingReadIsCovered:
    def test_there_are_blocking_reads_to_protect(self):
        assert blocking_reads()

    def test_every_block_is_the_module_constant(self):
        for lineno, block in blocking_reads():
            assert isinstance(block, ast.Name), f"literal block= at line {lineno}"
            assert block.id == "BLOCK_MS", f"unknown block= at line {lineno}"


class TestTheSweepClocksSurviveAReconnect:
    """``last_reclaim``/``last_trim`` initialised inside the reconnect loop is
    the whole of the starvation: a stream idle for longer than the read's
    deadline reconnects before either timer can ever come due."""

    @staticmethod
    def _run_body():
        return ast.parse(inspect.getsource(consumer.run).lstrip()).body[0]

    def test_the_clocks_are_set_before_the_reconnect_loop(self):
        body = self._run_body().body
        loop_index = next(
            i for i, node in enumerate(body) if isinstance(node, ast.While)
        )
        assigned = {
            target.id
            for node in body[:loop_index]
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert {"last_reclaim", "last_trim"} <= assigned

    @pytest.mark.parametrize("name", ["last_reclaim", "last_trim"])
    def test_the_reconnect_loop_only_advances_them(self, name):
        """Inside the loop they may be moved forward after a sweep, never
        re-seeded from scratch alongside the other one."""
        loop = next(
            node for node in self._run_body().body if isinstance(node, ast.While)
        )
        for node in ast.walk(loop):
            if not isinstance(node, ast.Assign):
                continue
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if name in targets:
                assert targets == [name], f"{name} re-seeded with {targets}"
                assert isinstance(node.value, ast.Name) and node.value.id == "now"
