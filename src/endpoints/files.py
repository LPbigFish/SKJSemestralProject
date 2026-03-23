from fastapi import APIRouter

files_router = APIRouter(prefix="/files")

@files_router.get("/")
def get_files():
    ...

@files_router.get("/{file_id}")
def get_specific_file():
    ...
    
@files_router.delete("/{file_id}")
def delete_specific_file():
    ...

@files_router.post("/upload")
def create_file():
    ...