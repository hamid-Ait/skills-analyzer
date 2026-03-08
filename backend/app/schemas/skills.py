from pydantic import BaseModel


class CategoryCount(BaseModel):
    name: str
    count: int
    percentage: float


class ExpertiseCount(BaseModel):
    name: str
    count: int


class SkillsMatrix(BaseModel):
    total_people: int
    total_analyzed: int
    categories: list[CategoryCount]
    top_expertise: list[ExpertiseCount]
    sectors: list[ExpertiseCount]
    geographies: list[ExpertiseCount]
