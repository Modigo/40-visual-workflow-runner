import sqlite3
from contextlib import contextmanager
from pathlib import Path


# Store the database beside this Python file.
DB_PATH = Path(__file__).resolve().parent / "workflows.db"


@contextmanager
def get_connection():
    """
    Open a database connection.

    Automatically commits successful operations,
    rolls back failed operations, and closes the connection.
    """
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    # Make SQLite enforce foreign-key relationships.
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def init_db():
    """
    Create the database tables if they do not already exist.
    """

    with get_connection() as connection:

        # Table 1: Workflows
        connection.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table 2: Tasks or nodes
        connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                settings TEXT DEFAULT '',

                FOREIGN KEY (workflow_id)
                    REFERENCES workflows(id)
                    ON DELETE CASCADE
            )
        """)

        # Table 3: Connections between tasks
        connection.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,

                FOREIGN KEY (workflow_id)
                    REFERENCES workflows(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (source_id)
                    REFERENCES tasks(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (target_id)
                    REFERENCES tasks(id)
                    ON DELETE CASCADE,

                UNIQUE (workflow_id, source_id, target_id)
            )
        """)

        # Table 4: Workflow execution history
        connection.execute("""
            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (workflow_id)
                    REFERENCES workflows(id)
                    ON DELETE CASCADE
            )
        """)


def create_workflow(name):
    """
    Create a workflow and return its database ID.
    """

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO workflows (name)
            VALUES (?)
            """,
            (name.strip(),)
        )

        return cursor.lastrowid


def list_workflows():
    """
    Return all workflows, newest first.
    """

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT id, name, created_at
            FROM workflows
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def add_task(workflow_id, name, task_type, settings=""):
    """
    Save a task in a workflow and return its database ID.
    """

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO tasks (
                workflow_id,
                name,
                type,
                settings
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                workflow_id,
                name.strip(),
                task_type,
                settings.strip()
            )
        )

        return cursor.lastrowid


def add_connection(workflow_id, source_id, target_id):
    """
    Save a connection between two tasks.

    Both tasks must belong to the specified workflow.
    Duplicate connections are rejected.
    """

    if source_id == target_id:
        raise ValueError(
            "A task cannot connect to itself."
        )

    with get_connection() as connection:

        # Confirm that the source belongs to this workflow.
        source = connection.execute(
            """
            SELECT id
            FROM tasks
            WHERE id = ? AND workflow_id = ?
            """,
            (source_id, workflow_id)
        ).fetchone()

        # Confirm that the target belongs to this workflow.
        target = connection.execute(
            """
            SELECT id
            FROM tasks
            WHERE id = ? AND workflow_id = ?
            """,
            (target_id, workflow_id)
        ).fetchone()

        if source is None or target is None:
            raise ValueError(
                "Both tasks must belong to the selected workflow."
            )

        cursor = connection.execute(
            """
            INSERT INTO connections (
                workflow_id,
                source_id,
                target_id
            )
            VALUES (?, ?, ?)
            """,
            (workflow_id, source_id, target_id)
        )

        return cursor.lastrowid


def load_workflow(workflow_id):
    """
    Load a workflow, its tasks, and its connections.

    Returns a dictionary compatible with the graph editor.
    Returns None if the workflow does not exist.
    """

    with get_connection() as connection:

        workflow = connection.execute(
            """
            SELECT id, name, created_at
            FROM workflows
            WHERE id = ?
            """,
            (workflow_id,)
        ).fetchone()

        if workflow is None:
            return None

        tasks = connection.execute(
            """
            SELECT id, name, type, settings
            FROM tasks
            WHERE workflow_id = ?
            ORDER BY id
            """,
            (workflow_id,)
        ).fetchall()

        connections = connection.execute(
            """
            SELECT id, source_id, target_id
            FROM connections
            WHERE workflow_id = ?
            ORDER BY id
            """,
            (workflow_id,)
        ).fetchall()

        return {
            "id": workflow["id"],
            "name": workflow["name"],
            "created_at": workflow["created_at"],
            "tasks": [dict(row) for row in tasks],
            "connections": [
                dict(row) for row in connections
            ]
        }


def record_history(workflow_id, status, message=""):
    """
    Save a workflow execution result.

    Person 5 can call this function after running a workflow.
    """

    with get_connection() as connection:

        cursor = connection.execute(
            """
            INSERT INTO execution_history (
                workflow_id,
                status,
                message
            )
            VALUES (?, ?, ?)
            """,
            (workflow_id, status, message)
        )

        return cursor.lastrowid


def get_history(workflow_id):
    """
    Retrieve execution history for one workflow.
    """

    with get_connection() as connection:

        rows = connection.execute(
            """
            SELECT id, status, message, created_at
            FROM execution_history
            WHERE workflow_id = ?
            ORDER BY id DESC
            """,
            (workflow_id,)
        ).fetchall()

        return [dict(row) for row in rows]