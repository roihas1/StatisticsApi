from fastapi import FastAPI
from app.PlayerStat.router import router as playerRouter
from app.TeamStat.router import router as teamRouter
# Import more routers as your application grows...
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.database import connectToMongo, closeMongoConnection

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs when the EC2 server starts
    await connectToMongo()
    yield
    # This runs when the EC2 server stops
    await closeMongoConnection()


# 1. Initialize the Main Application
app = FastAPI(
    title="Service Orchestrator",
    version="0.1.0",
    description="Main entry point for API routes and core configuration.",
    debug=True,
    lifespan=lifespan
)


app.include_router(
   playerRouter,
    prefix="/api/player",
    tags=["Player Stats Data"] # Optional: Override or confirm the tag for documentation
)
app.include_router(
    teamRouter,
    prefix='/api/team',
    tags=["Team Stats Data"]
)



@app.get("/")
async def root():
    return {"message": "Service operational. Access documentation at /docs"}
