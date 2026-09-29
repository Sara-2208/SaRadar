from fastapi import FastAPI

app = FastAPI(title="SaRadar API")


@app.get("/health")
def health_check():
    """Health check endpoint.

    Returns:
        dict: Status indicating the API is running.
    """
    # TODO: Add more comprehensive health checks (DB connection, LLM connectivity)
    return {"status": "ok"}
