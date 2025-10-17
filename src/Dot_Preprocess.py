import glob
import os
import random
import re
from collections import defaultdict
import pydot


def read_dot_file(dot_file, key_register_name, design_name):
    graphs = pydot.graph_from_dot_file(dot_file)
    g = graphs[0]

    node_attrs = {}
    node_files = f"../data/{design_name}/{design_name}_nodes.txt"
    for node in g.get_nodes():
        name = node.get_name().strip('"')
        if name.lower() == "node":
            continue
        attrs = {k: v.strip('"') for k, v in node.get_attributes().items()}
        node_attrs[name] = attrs

    key_nodes = set()
    with open(node_files, "w") as f:
        for node, attrs in node_attrs.items():
            label = attrs.get("label", "")
            f.write("@@" + label + "@@\n")
            if label and key_register_name in label:
                key_nodes.add(node)

    indegree = defaultdict(int)
    outdegree = defaultdict(int)
    graph = {}
    children = set()
    parents = set()
    nodes = set()
    edges = set()

    for edge in g.get_edges():
        src = edge.get_source().strip('"')
        dst = edge.get_destination().strip('"')
        edges.add((src, dst))
        graph.setdefault(src, []).append(dst)
        parents.add(src)
        children.add(dst)
        nodes.add(src)
        nodes.add(dst)

        outdegree[src] += 1
        indegree[dst] += 1
        if src not in indegree:
            indegree[src] = indegree[src]
        if dst not in outdegree:
            outdegree[dst] = outdegree[dst]

    roots = list(parents - children)
    if roots is None:
        roots = [g.get_nodes()[0]]
    # print(f"{len(nodes)}, {len(g.get_edges())}, {len(g.get_nodes())}")
    return graph, roots, nodes, node_attrs, indegree, outdegree, key_nodes, edges

def find_paths(graph, root):
    paths = []

    def dfs(node, path, visited):
        if node in visited:
            return
        visited.add(node)

        if node not in graph or not graph[node]:
            paths.append(path + [node])
        else:
            for child in graph[node]:
                dfs(child, path + [node], visited.copy())

    dfs(root, [], set())
    return paths

def extract_dot_features(graph, nodes, indegree, outdegree, node_attrs, key_nodes):
    def count_ops_in_label(label: str):
        counts = {"and": 0, "or": 0, "mux": 0, "xor": 0}

        # and: "and", "&", "&&"
        counts["and"] += len(re.findall(r"\band\b", label, flags=re.IGNORECASE))
        counts["and"] += len(re.findall(r"(?<!~)&{1,2}", label))

        # or: "or", "|", "||"
        counts["or"] += len(re.findall(r"\bor\b", label, flags=re.IGNORECASE))
        counts["or"] += len(re.findall(r"(?<!~)\|{1,2}", label))

        # xor: "xor", "^", "~^", "^~"
        counts["xor"] += len(re.findall(r"\bxor\b", label, flags=re.IGNORECASE))
        counts["xor"] += len(re.findall(r"\^~|~\^|\^", label))

        # mux: "mux", "?:", "[:]", "case"
        counts["mux"] += len(re.findall(r"\bmux\b", label, flags=re.IGNORECASE))
        counts["mux"] += len(re.findall(r"\?.*?:", label))
        counts["mux"] += len(re.findall(r"\[\s*\d+\s*:\s*\d+\s*\]", label))
        counts["mux"] += len(re.findall(r"\bcase\b.*?\bendcase\b", label,
                                    flags=re.IGNORECASE | re.DOTALL))

        for k in counts:
            counts[k] = int(counts[k] > 0)
        return counts

    def count_all_paths_from_starts(graph, key_nodes, nodes):
        """
        Calculates the number of simple paths from a list of key_nodes to every other node
        in the graph using dynamic programming and memoization.

        Args:
            graph (dict): The graph represented as an adjacency list.
                          Example: {'A': ['B', 'C'], 'B': ['D']}
            key_nodes (list or set): A list of starting nodes.

        Returns:
            dict: A dictionary mapping each node to the number of simple paths
                  originating from any of the key_nodes.
        """
        memo = {}  # Cache for storing results of computed nodes
        visiting = set()  # For detecting cycles in the current DFS path
        starts = set(key_nodes)  # Use a set for O(1) lookups

        def _count_paths_to(u):
            # If result is already cached, return it
            if u in memo:
                return memo[u]
            # If we are currently visiting this node in this path, we've found a cycle
            if u in visiting:
                return 0  # This path is invalid

            visiting.add(u)

            # A start node has one path to itself (of length 0)
            count = 1 if u in starts else 0

            # Sum the paths from all its predecessors
            for predecessor in graph.get(u, []):
                count += _count_paths_to(predecessor)

            visiting.remove(u)

            # Cache the result before returning
            memo[u] = count
            return count

        # Trigger the calculation for every node in the graph
        # The memoization ensures each node is only computed once
        path_counts = {node: _count_paths_to(node) for node in nodes}

        return path_counts

    all_path_counts = count_all_paths_from_starts(graph, key_nodes, nodes)
    # for node, count in all_path_counts.items():
    #     print(f"node: {node}, count: {count}")

    Features = {}
    cnt = 0
    for node in nodes:
        label = node_attrs.get(node, {}).get("label", "")
        # print(f"Node {cnt}: {label}")
        Features[node] = {
            "node_number": cnt,
            "Node": label,
            "Degree": indegree[node] + outdegree[node],
            **count_ops_in_label(label),
            "Paths": all_path_counts[node],
        }
        cnt += 1

    return Features