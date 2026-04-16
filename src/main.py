from fastapi import FastAPI
from endpoints.files import files_router
from endpoints.buckets import buckets_router
import uvicorn

app = FastAPI()

app.include_router(files_router)
app.include_router(buckets_router)


@app.get("/")
def info():
    return {"The API is RUNNING!!!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
