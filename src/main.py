from fastapi import FastAPI
from endpoints.files import files_router

app = FastAPI()

app.include_router(files_router)

@app.get("/")
def info():
    return {"The API is RUNNING!!!"}