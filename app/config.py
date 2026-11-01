import os

# Defaults match docker-compose.yml + docker-compose.override.yml (local
# dev). Override with environment variables — the "api" service in
# docker-compose.yml does this, since "localhost" means something
# different inside a container.
MONGODB_URL = os.getenv(
    "MONGODB_URL", "mongodb://sensor:sensor@localhost:27018/?authSource=admin"
)
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "sensor_analytics")
