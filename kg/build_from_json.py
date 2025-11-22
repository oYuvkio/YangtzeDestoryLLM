import json
import networkx as nx
from .schema import RELATIONS

def load_events(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def build_graph(path: str) -> nx.DiGraph:
    g = nx.DiGraph()
    for row in load_events(path):
        event_id = row["id"]
        g.add_node(event_id, label="event", props=row)
        for key, rel in RELATIONS.items():
            if key in row and row[key]:
                val = row[key]
                node_id = f"{key}_{val}"
                g.add_node(node_id, label=key, props={"text": val})
                g.add_edge(event_id, node_id, rel=rel)
    return g

def save_graphml(g: nx.DiGraph, out_path: str):
    nx.write_graphml(g, out_path)

if __name__ == "__main__":
    g = build_graph("data/processed/sample_events.jsonl")
    save_graphml(g, "data/processed/sample.graphml")
    print(f"nodes={g.number_of_nodes()}, edges={g.number_of_edges()}")
