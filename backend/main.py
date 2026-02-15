from fastapi import FastAPI
from backend.routers import health, tripadvisor_insights

app = FastAPI(title="Scenery API")

app.include_router(health.router) # health check endpoint (GET /health)
app.include_router(tripadvisor_insights.router) # tripadvisor insights endpoint (GET /tripadvisor/hotels/insights) that takes search parameters + user request and returns LLM-ranked hotel insights