from pymongo import MongoClient
from config import Config

if not Config.MONGO_URI:
    raise RuntimeError("MONGO_URI is missing. Create a .env file using .env.example.")

client = MongoClient(Config.MONGO_URI)
db = client[Config.DB_NAME]

users_collection = db["users"]
projects_collection = db["projects"]
tasks_collection = db["tasks"]
comments_collection = db["comments"]
notifications_collection = db["notifications"]
activity_logs_collection = db["activity_logs"]
organizations_collection = db["organizations"]
login_sessions_collection = db["login_sessions"]

attachments_collection = db["attachments"]

subtasks_collection = db["subtasks"]

user_org_memberships_collection = db["user_org_memberships"]


milestones_collection = db["milestones"]
