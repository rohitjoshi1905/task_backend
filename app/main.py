from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import router
from .logger import logger
from .db import db # Initialize DB connection

app = FastAPI()

# CORS
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Task Planner Backend is running!"}


@app.on_event("startup")
async def startup_event():
    logger.info("Server started")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
