from collections import defaultdict, deque
from collections.abc import Iterable
from uuid import UUID

import networkx as nx


class DAGCycleError(ValueError):
    """Raised when an operation would introduce a cycle into a directed acyclic graph."""

    def __init__(self, message: str, cycle: list[UUID] | None = None) -> None:
        super().__init__(message)
        self.cycle = cycle or []


def validate_dag_edge(
    existing_edges: Iterable[tuple[UUID, UUID]],
    prereq_id: UUID,
    skill_id: UUID,
) -> None:
    """
    Validates that adding a directed edge (prereq_id -> skill_id) will not introduce a cycle.

    A prerequisite edge means `prereq_id` must be mastered before `skill_id`.
    Thus, an edge exists from `prereq_id` to `skill_id`.
    Adding this edge creates a cycle if and only if:
      1. prereq_id == skill_id (self-loop).
      2. There is already a directed path from skill_id to prereq_id.

    Args:
        existing_edges: Collection of current (prereq_id, skill_id) tuples.
        prereq_id: Source node (prerequisite).
        skill_id: Target node (dependent skill).

    Raises:
        DAGCycleError: If the edge would create a self-loop or cycle.
    """
    if prereq_id == skill_id:
        raise DAGCycleError(
            f"Self-loop detected: Prerequisite cannot be the skill itself ({prereq_id}).",
            cycle=[prereq_id, prereq_id],
        )

    # Build adjacency list: node -> list of children
    graph: dict[UUID, list[UUID]] = defaultdict(list)
    for u, v in existing_edges:
        graph[u].append(v)

    # Check if prereq_id is reachable starting from skill_id
    visited: set[UUID] = set()
    parent: dict[UUID, UUID] = {}
    queue: deque[UUID] = deque([skill_id])
    visited.add(skill_id)

    path_found = False
    while queue:
        current = queue.popleft()
        if current == prereq_id:
            path_found = True
            break
        for neighbor in graph[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = current
                queue.append(neighbor)

    if path_found:
        # Reconstruct cycle: skill_id -> ... -> prereq_id -> skill_id
        cycle = [prereq_id]
        curr = prereq_id
        while curr in parent:
            curr = parent[curr]
            cycle.append(curr)
        cycle.reverse()
        cycle.append(skill_id)
        raise DAGCycleError(
            f"Adding edge ({prereq_id} -> {skill_id}) creates a cycle: "
            f"{' -> '.join(str(node) for node in cycle)}",
            cycle=cycle,
        )


def assert_graph_is_acyclic(edges: Iterable[tuple[UUID, UUID]]) -> None:
    """
    Asserts that the entire graph defined by edges is acyclic.

    Uses Kahn's algorithm (topological sort via indegree tracking).

    Args:
        edges: Iterable of (prereq_id, skill_id) tuples.

    Raises:
        DAGCycleError: If any directed cycle exists in the graph.
    """
    # Build NetworkX DiGraph for robust cycle finding
    G = nx.DiGraph()
    for u, v in edges:
        if u == v:
            raise DAGCycleError(
                f"Self-loop detected on node {u}",
                cycle=[u, u],
            )
        G.add_edge(u, v)

    try:
        cycle = nx.find_cycle(G, orientation="original")
        cycle_nodes = [edge[0] for edge in cycle] + [cycle[0][0]]
        raise DAGCycleError(
            f"Cycle detected in skill graph: {' -> '.join(str(n) for n in cycle_nodes)}",
            cycle=cycle_nodes,
        )
    except nx.NetworkXNoCycle:
        pass


def get_topological_skill_order(
    skills: Iterable[UUID],
    edges: Iterable[tuple[UUID, UUID]],
) -> list[UUID]:
    """
    Computes a valid topological ordering of skills where all prerequisites appear
    before their dependents.

    Args:
        skills: Iterable of all skill UUIDs.
        edges: Iterable of (prereq_id, skill_id) prerequisite tuples.

    Returns:
        List of skill UUIDs ordered topologically.

    Raises:
        DAGCycleError: If a cycle prevents topological sorting.
    """
    G = nx.DiGraph()
    for s in skills:
        G.add_node(s)
    for u, v in edges:
        G.add_edge(u, v)

    try:
        return list(nx.topological_sort(G))
    except nx.NetworkXUnfeasible as err:
        cycle = nx.find_cycle(G, orientation="original")
        cycle_nodes = [edge[0] for edge in cycle] + [cycle[0][0]]
        raise DAGCycleError(
            f"Cannot topologically sort cyclic graph: {' -> '.join(str(n) for n in cycle_nodes)}",
            cycle=cycle_nodes,
        ) from err
