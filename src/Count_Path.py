from collections import defaultdict, deque

def _ensure_all_nodes(graph):
    nodes = set(graph.keys())
    for vs in graph.values():
        nodes.update(vs)
    return nodes

def tarjan_scc(graph):
    """Return (comp_id, comp_nodes). comp_id[u] = component index (0..c-1)"""
    nodes = list(_ensure_all_nodes(graph))
    idx = {u: -1 for u in nodes}
    low = {u: 0 for u in nodes}
    onstack = set()
    st = []
    time = 0
    comp_id = {}
    comps = []

    def dfs(u):
        nonlocal time
        idx[u] = low[u] = time; time += 1
        st.append(u); onstack.add(u)
        for v in graph.get(u, []):
            if idx[v] == -1:
                dfs(v)
                low[u] = min(low[u], low[v])
            elif v in onstack:
                low[u] = min(low[u], idx[v])
        if low[u] == idx[u]:
            comp = []
            while True:
                w = st.pop(); onstack.discard(w)
                comp_id[w] = len(comps)
                comp.append(w)
                if w == u:
                    break
            comps.append(comp)

    for u in nodes:
        if idx[u] == -1:
            dfs(u)
    return comp_id, comps  # comps[k] is list of original nodes in component k

def build_component_dag(graph, comp_id, ncomp):
    dag = defaultdict(list)
    for u, vs in graph.items():
        cu = comp_id[u]
        for v in vs:
            cv = comp_id[v]
            if cu != cv:
                dag[cu].append(cv)
    for c in list(dag.keys()):
        dag[c] = sorted(set(dag[c]))
    for c in range(ncomp):
        dag.setdefault(c, [])
    return dag

def topo_order_dag(dag):
    indeg = defaultdict(int)
    for u, vs in dag.items():
        indeg.setdefault(u, 0)
        for v in vs: indeg[v] += 1
    q = deque([u for u in dag if indeg[u] == 0])
    order = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in dag[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(order) != len(dag):
        raise ValueError("Component graph is not a DAG (unexpected).")
    return order

def count_paths_with_scc(graph, key_nodes):
    comp_id, comps = tarjan_scc(graph)
    ncomp = len(comps)
    dag = build_component_dag(graph, comp_id, ncomp)
    order = topo_order_dag(dag)

    start_comp_counts = defaultdict(int)
    for s in key_nodes:
        if s in comp_id:
            start_comp_counts[comp_id[s]] += 1

    comp_paths = defaultdict(int)
    for c, k in start_comp_counts.items():
        comp_paths[c] += k

    for u in order:
        for v in dag[u]:
            comp_paths[v] += comp_paths[u]

    node_paths = {}
    for c, members in enumerate(comps):
        val = comp_paths.get(c, 0)
        for u in members:
            node_paths[u] = val
    return node_paths
