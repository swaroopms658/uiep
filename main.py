from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import auth
import processing
import analytics
import models

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="UPI Tracker API")

# Setup CORS for mobile app and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(processing.router)
app.include_router(analytics.router)

@app.get("/")
def root():
    return {"message": "Welcome to the UPI Tracker API"}
