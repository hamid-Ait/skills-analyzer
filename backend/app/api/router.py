from fastapi import APIRouter

from app.api import upload, jobs, companies, people, skills, export, image_proxy

api_router = APIRouter()
api_router.include_router(upload.router, tags=["Upload"])
api_router.include_router(jobs.router, tags=["Jobs"])
api_router.include_router(companies.router, tags=["Companies"])
api_router.include_router(people.router, tags=["People"])
api_router.include_router(skills.router, tags=["Skills"])
api_router.include_router(export.router, tags=["Export"])
api_router.include_router(image_proxy.router, tags=["Images"])
