from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, subqueryload

from app.database import get_db
from app.models import Job
from app.schemas.job import JobBrief, JobDetail

router = APIRouter()


@router.get("/jobs", response_model=list[JobBrief])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return [JobBrief.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    job = db.query(Job).options(subqueryload(Job.companies)).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail.model_validate(job)
