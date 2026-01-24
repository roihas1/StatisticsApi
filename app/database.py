import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
load_dotenv(r'C:\Users\roiha\Desktop\PlayoffApp\StatsService\app\.env')
# In production, move these to a .env file!
# mongoUri = f"mongodb+srv://{os.getenv('mongo_username')}:{os.getenv('mongo_password')}@cluster0.lrc86d4.mongodb.net/?appName=Cluster0"
mongoUri = "mongodb://localhost:27017/"

dbName = "nbaStatsDb"

class MongoDB:
    client: AsyncIOMotorClient = None

dbInstance = MongoDB()

async def connectToMongo():
    """Initializes the connection pool on startup."""
    dbInstance.client = AsyncIOMotorClient(mongoUri)
    print("Connected to MongoDB cluster")

async def closeMongoConnection():
    """Closes the connection pool on shutdown."""
    if dbInstance.client:
        dbInstance.client.close()
        print("MongoDB connection closed")

def getDb():
    """Returns the database instance for use in routers."""
    return dbInstance.client[dbName]