from pydantic import BaseModel


class Correction(BaseModel):
    topic: str  # short grammar theme, e.g. "Articles", "Past Simple vs Present Perfect"
    you_said: str
    better: str
    note: str
