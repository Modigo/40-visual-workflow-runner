from fastapi import FastAPI

app = FastAPI(title="Visual Workflow Runner")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}