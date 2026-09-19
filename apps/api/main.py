from fastapi import FastAPI
from routers.pins import router as pins_router

app = FastAPI(title="Curb Sense API")

app.include_router(pins_router)

@app.get("/health")
def health_check():
    return {"status": "healthy"}