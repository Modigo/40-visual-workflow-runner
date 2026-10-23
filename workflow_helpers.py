import json


def node_name(workflow, node_id):
    """
    Return a task's name using its ID.
    """

    for task in workflow["tasks"]:

        if task["id"] == node_id:
            return task["name"]

    return f"Unknown node ({node_id})"


def build_dot(workflow):
    """
    Convert a workflow into Graphviz DOT text.

    Person 5 can use this shared helper to visualize
    the workflow or inspect its structure.
    """

    lines = ["digraph Workflow {"]

    # Add every task as a graph node.
    for task in workflow["tasks"]:

        node_id = task["id"]
        label = json.dumps(task["name"])

        lines.append(
            f"    node_{node_id} [label={label}];"
        )

    # Add every connection as a directed arrow.
    for connection in workflow["connections"]:

        source_id = connection["source_id"]
        target_id = connection["target_id"]

        lines.append(
            f"    node_{source_id} -> node_{target_id};"
        )

    lines.append("}")

    return "\n".join(lines)


def would_create_cycle(workflow, source_id, target_id):
    """
    Return True if adding source_id -> target_id
    would create a circular path.

    Example:
        A -> B
        B -> C

    Adding C -> A would create a cycle.
    """

    # A direct connection from a task to itself is a cycle.
    if source_id == target_id:
        return True

    # Build an adjacency list from existing connections.
    adjacency = {}

    for task in workflow["tasks"]:
        adjacency[task["id"]] = []

    for connection in workflow["connections"]:

        source = connection["source_id"]
        target = connection["target_id"]

        adjacency.setdefault(source, []).append(target)

    # Adding source -> target creates a cycle if
    # target can already reach source.
    stack = [target_id]
    visited = set()

    while stack:

        current = stack.pop()

        if current == source_id:
            return True

        if current in visited:
            continue

        visited.add(current)

        for neighbor in adjacency.get(current, []):
            stack.append(neighbor)

    return False


def check_workflow(workflow):
    """
    Return a list of problems found in the workflow.

    An empty list means the basic structural checks passed.
    It does not guarantee that every task can execute.
    """

    errors = []

    tasks = workflow.get("tasks", [])
    connections = workflow.get("connections", [])

    if not tasks:
        errors.append(
            "Add at least one task to the workflow."
        )

    task_ids = {
        task["id"] for task in tasks
    }

    # Check every connection.
    for connection in connections:

        source_id = connection["source_id"]
        target_id = connection["target_id"]

        if source_id not in task_ids:
            errors.append(
                f"Connection references missing source task "
                f"{source_id}."
            )

        if target_id not in task_ids:
            errors.append(
                f"Connection references missing target task "
                f"{target_id}."
            )

        if source_id == target_id:
            errors.append(
                f"Task {source_id} cannot connect to itself."
            )

    # Check for cycles.
    if would_create_any_cycle(workflow):
        errors.append(
            "The workflow contains a circular connection."
        )

    return errors


def would_create_any_cycle(workflow):
    """
    Check whether the existing graph contains a cycle.
    """

    adjacency = {}

    for task in workflow["tasks"]:
        adjacency[task["id"]] = []

    for connection in workflow["connections"]:

        source_id = connection["source_id"]
        target_id = connection["target_id"]

        if (
            source_id in adjacency
            and target_id in adjacency
        ):
            adjacency[source_id].append(target_id)

    visiting = set()
    visited = set()

    def visit(node_id):

        if node_id in visiting:
            return True

        if node_id in visited:
            return False

        visiting.add(node_id)

        for neighbor in adjacency.get(node_id, []):

            if visit(neighbor):
                return True

        visiting.remove(node_id)
        visited.add(node_id)

        return False

    for node_id in adjacency:

        if visit(node_id):
            return True

    return False