from fastapi import APIRouter

files_router = APIRouter()

@files_router.get("/files")
def get_files():
    ...