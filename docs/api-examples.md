# API examples

All routes are under `/api/v1`, except `/healthz`. Timestamps are ISO 8601 (UTC).
Status values: run = queued, running, succeeded, failed. Task = pending, running, retrying, succeeded, failed, skipped.

## GET /healthz
Response 200:
```json
{"status": "ok"}
```

## POST /api/v1/workflows
Request:
```json
{"name": "Demo workflow", "description": "Optional text"}
```
Response 201:
```json
{
  "id": "<workflow-uuid>",
  "name": "Demo workflow",
  "description": "Optional text",
  "version": 1,
  "created_at": "2026-10-20T12:00:00Z",
  "updated_at": "2026-10-20T12:00:00Z",
  "is_archived": false
}
```

## GET /api/v1/workflows
Response 200: a list of the workflow objects above (no nodes or edges).

## GET /api/v1/workflows/{workflow_id}
Response 200: the workflow object plus `nodes` and `edges` (same shape as the graph save request below). Response 404 if the id does not exist.

## PUT /api/v1/workflows/{workflow_id}/graph
Replaces the whole graph. `expected_version` must match the stored version.
Request:
```json
{
  "expected_version": 1,
  "nodes": [
    {
      "id": "node-a",
      "name": "Source A",
      "kind": "emit_json",
      "config": {"value": {"value": 3}},
      "position": {"x": 80, "y": 120},
      "sort_order": 0,
      "max_retries": 0,
      "retry_delay_seconds": 1,
      "timeout_seconds": 10
    },
    {
      "id": "node-b",
      "name": "Collect inputs",
      "kind": "combine_inputs",
      "config": {},
      "position": {"x": 360, "y": 120},
      "sort_order": 1,
      "max_retries": 1,
      "retry_delay_seconds": 1,
      "timeout_seconds": 10
    }
  ],
  "edges": [{"source_node_id": "node-a", "target_node_id": "node-b"}]
}
```
Response 200: the full workflow with `version` increased by 1.
Response 409 if `expected_version` is out of date (error code `VERSION_CONFLICT`).
Response 422 if a field is invalid.

## POST /api/v1/workflows/{workflow_id}/validate
Response 200, valid graph:
```json
{"valid": true, "errors": [], "warnings": [], "execution_order": ["node-a", "node-b"]}
```
Response 200, invalid graph:
```json
{
  "valid": false,
  "errors": [
    {
      "code": "GRAPH_CYCLE",
      "message": "The workflow contains a dependency cycle.",
      "node_ids": ["node-a", "node-b"],
      "edge_ids": []
    }
  ],
  "warnings": [],
  "execution_order": []
}
```

## POST /api/v1/workflows/{workflow_id}/runs
Response 202:
```json
{
  "id": "<run-uuid>",
  "workflow_id": "<workflow-uuid>",
  "workflow_version": 3,
  "status": "queued",
  "created_at": "2026-10-20T12:00:00Z"
}
```
Response 409 if the saved graph is invalid.

## GET /api/v1/workflows/{workflow_id}/runs?limit=20
Response 200: a list of run objects (the shape above), newest first.

## GET /api/v1/runs/{run_id}
Response 200:
```json
{
  "id": "<run-uuid>",
  "workflow_id": "<workflow-uuid>",
  "workflow_version": 3,
  "status": "failed",
  "created_at": "2026-10-20T12:00:00Z",
  "started_at": "2026-10-20T12:00:01Z",
  "finished_at": "2026-10-20T12:00:09Z",
  "error_summary": "Task 'Collect inputs' failed after 2 attempts.",
  "tasks": [
    {
      "id": "<task-run-uuid>",
      "node_id": "node-a",
      "node_name": "Source A",
      "node_kind": "emit_json",
      "status": "succeeded",
      "attempt_count": 1,
      "output": {"value": 3},
      "error_message": null,
      "started_at": "2026-10-20T12:00:01Z",
      "finished_at": "2026-10-20T12:00:02Z",
      "attempts": [
        {
          "attempt_number": 1,
          "status": "succeeded",
          "error_type": null,
          "error_message": null,
          "started_at": "2026-10-20T12:00:01Z",
          "finished_at": "2026-10-20T12:00:02Z"
        }
      ]
    }
  ]
}
```
Response 404 if the id does not exist.

## Error format (all 4xx and 5xx responses)
```json
{
  "error": {
    "code": "GRAPH_CYCLE",
    "message": "The workflow contains a dependency cycle.",
    "details": [{"node_ids": ["node-a", "node-b", "node-a"]}]
  }
}
```
Statuses: 404 missing resource, 409 version or graph conflict, 422 invalid request, 500 unexpected error only.