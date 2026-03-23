from fastapi import APIRouter

files_router = APIRouter(prefix="/files")

@files_router.get("/", status_code=200)
def get_files():
    ...

@files_router.get("/{user_id}/{file_id}", status_code=200)
def get_specific_file(user_id, file_id):
    ...
    
@files_router.delete("/{user_id}/{file_id}", status_code=204)
def delete_specific_file(user_id, file_id):
    ...

@files_router.post("/upload", status_code=201)
def create_file():
    ...