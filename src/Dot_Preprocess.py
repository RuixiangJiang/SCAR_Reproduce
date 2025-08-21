import re
from collections import defaultdict
import pydot


def read_dot_file(dot_file, key_register_name):
    graphs = pydot.graph_from_dot_file(dot_file)
    g = graphs[0]

    node_attrs = {}
    for node in g.get_nodes():
        name = node.get_name().strip('"')
        if name.lower() == "node":
            continue
        attrs = {k: v.strip('"') for k, v in node.get_attributes().items()}
        node_attrs[name] = attrs

    key_nodes = set()
    for node, attrs in node_attrs.items():
        label = attrs.get("label", "")
        if label and key_register_name in label:
            key_nodes.add(node)

    indegree = defaultdict(int)
    outdegree = defaultdict(int)
    graph = {}
    children = set()
    parents = set()
    nodes = set()

    for edge in g.get_edges():
        src = edge.get_source().strip('"')
        dst = edge.get_destination().strip('"')
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
    return graph, roots, nodes, node_attrs, indegree, outdegree, key_nodes

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
        counts = {"and": 0, "or": 0, "xor": 0, "mux": 0}

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

    def count_paths_to_targets(graph, key_nodes, u):
        memo = {}
        onstack = set()

        def dfs(u):
            if u in memo:
                return memo[u]
            if u in onstack:
                return 0

            onstack.add(u)

            total = 1 if u in key_nodes else 0

            for v in graph.get(u, []):
                total += dfs(v)

            onstack.remove(u)
            memo[u] = total
            return total

        return dfs(u)

    Features = {}
    for node in nodes:
        label = node_attrs.get(node, {}).get("label", "")
        Features[node] = {
            "id": node,
            "label": label,
            "degree": indegree[node] + outdegree[node],
            **count_ops_in_label(label),
            "paths_to_keys": count_paths_to_targets(graph, key_nodes, node),
        }

    return Features