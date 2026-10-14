import uuid

import pytest
from masteryloop_common.db.dag import (
    DAGCycleError,
    assert_graph_is_acyclic,
    get_topological_skill_order,
    validate_dag_edge,
)


def test_acyclic_skill_dag_validates_successfully() -> None:
    """Verifies that a valid directed acyclic graph passes validation."""
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()
    s3 = uuid.uuid4()
    s4 = uuid.uuid4()

    # s1 -> s2 -> s3 -> s4; s1 -> s3
    edges = [
        (s1, s2),
        (s2, s3),
        (s3, s4),
        (s1, s3),
    ]

    assert_graph_is_acyclic(edges)

    order = get_topological_skill_order([s1, s2, s3, s4], edges)
    assert order.index(s1) < order.index(s2)
    assert order.index(s2) < order.index(s3)
    assert order.index(s3) < order.index(s4)
    assert order.index(s1) < order.index(s3)


def test_incremental_valid_edge_additions() -> None:
    """Verifies that validate_dag_edge allows adding non-cyclical prerequisite edges."""
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()
    s3 = uuid.uuid4()

    edges: list[tuple[uuid.UUID, uuid.UUID]] = []

    # Add s1 -> s2
    validate_dag_edge(edges, s1, s2)
    edges.append((s1, s2))

    # Add s2 -> s3
    validate_dag_edge(edges, s2, s3)
    edges.append((s2, s3))

    # Add diamond edge s1 -> s3
    validate_dag_edge(edges, s1, s3)
    edges.append((s1, s3))

    assert len(edges) == 3
    assert_graph_is_acyclic(edges)


def test_self_loop_rejected() -> None:
    """Asserts that self-prerequisites (A -> A) are strictly rejected."""
    s1 = uuid.uuid4()

    with pytest.raises(DAGCycleError) as exc_info:
        validate_dag_edge([], s1, s1)
    assert "Self-loop" in str(exc_info.value)

    with pytest.raises(DAGCycleError):
        assert_graph_is_acyclic([(s1, s1)])


def test_two_node_cycle_rejected() -> None:
    """Asserts that direct reciprocal edges (A -> B and B -> A) are rejected."""
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()

    existing_edges = [(s1, s2)]

    # Attempting to make s2 a prerequisite of s1
    with pytest.raises(DAGCycleError) as exc_info:
        validate_dag_edge(existing_edges, s2, s1)
    assert "creates a cycle" in str(exc_info.value)

    with pytest.raises(DAGCycleError):
        assert_graph_is_acyclic([(s1, s2), (s2, s1)])


def test_multi_node_cycle_rejected() -> None:
    """Asserts that multi-hop cycles (A -> B -> C -> D -> A) are rejected."""
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()
    s3 = uuid.uuid4()
    s4 = uuid.uuid4()

    existing_edges = [
        (s1, s2),
        (s2, s3),
        (s3, s4),
    ]

    # Adding (s4 -> s1) closes the loop
    with pytest.raises(DAGCycleError) as exc_info:
        validate_dag_edge(existing_edges, s4, s1)
    assert "creates a cycle" in str(exc_info.value)

    with pytest.raises(DAGCycleError):
        assert_graph_is_acyclic(existing_edges + [(s4, s1)])


def test_topological_sort_fails_on_cycle() -> None:
    """Asserts get_topological_skill_order raises DAGCycleError when a cycle is present."""
    s1 = uuid.uuid4()
    s2 = uuid.uuid4()

    edges = [(s1, s2), (s2, s1)]
    with pytest.raises(DAGCycleError):
        get_topological_skill_order([s1, s2], edges)
