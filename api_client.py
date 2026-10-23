import requests

API_BASE_URL = "http://127.0.0.1:8000/api/v1"


def list_workflows():
    """Retrieve all workflows from the backend."""
    response = requests.get(
        f"{API_BASE_URL}/workflows",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def create_workflow(name, description=None):
    """Create a workflow through the backend."""
    response = requests.post(
        f"{API_BASE_URL}/workflows",
        json={
            "name": name,
            "description": description,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_workflow(workflow_id):
    """Retrieve one workflow, including its nodes and edges."""
    response = requests.get(
        f"{API_BASE_URL}/workflows/{workflow_id}",
        timeout=10,
    )
    response.raise_for_status()
    return response.json()

def save_workflow_graph(workflow_id, expected_version, nodes, edges):
    """Save workflow nodes and connections through the backend."""
    response = requests.put(
        f"{API_BASE_URL}/workflows/{workflow_id}/graph",
        json={
            "expected_version": expected_version,
            "nodes": nodes,
            "edges": edges,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()

def convert_workflow_for_ui(workflow):
    """Convert backend data to the frontend format while preserving the original graph."""

    tasks = []

    for node in workflow.get("nodes", []):
        tasks.append({
            "id": node["id"],
            "name": node["name"],
            "type": node["kind"],
            "settings": node.get("config", {}),
        })

    connections = []

    for edge in workflow.get("edges", []):
        connections.append({
            "source_id": edge["source_node_id"],
            "target_id": edge["target_node_id"],
        })

    return {
        "id": workflow["id"],
        "name": workflow["name"],
        "version": workflow["version"],
        "tasks": tasks,
        "connections": connections,

        # Preserve the complete backend graph for safe future saves.
        "backend_nodes": workflow.get("nodes", []),
        "backend_edges": workflow.get("edges", []),
    }
