from pydantic import BaseModel
from typing import Literal, Optional

Quadrant = Literal[0, 1, 2, 3]
# 0 = Models & Providers
# 1 = Infrastructure & Cloud
# 2 = Frameworks & Libraries
# 3 = Techniques & Patterns

Ring = Literal[0, 1, 2, 3]
# 0 = ADOPT, 1 = TRIAL, 2 = ASSESS, 3 = HOLD

Moved = Literal[-1, 0, 1]


class Technology(BaseModel):
    id: str
    label: str
    quadrant: Quadrant
    link: Optional[str] = None


class Team(BaseModel):
    id: str
    name: str
    date: str


class Assignment(BaseModel):
    tech: str
    ring: Ring
    moved: Moved


class Radar(BaseModel):
    date: str
    default_team: str
    teams: list[Team]
    technologies: list[Technology]
    assignments: dict[str, list[Assignment]]
