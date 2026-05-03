from fastapi import FastAPI
from endpoints.files import files_router
from endpoints.buckets import buckets_router
from endpoints.broker import broker_router
from endpoints.process import process_router
import uvicorn

app = FastAPI()

app.include_router(files_router)
app.include_router(buckets_router)
app.include_router(broker_router)
app.include_router(process_router)


@app.get("/")
def info():
    return {"The API is RUNNING!!!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, ws_ping_interval=None, ws_ping_timeout=None)
