from pydantic import BaseModel

from app.models.correction import Correction


class TutorReply(BaseModel):
    spoken_reply: str
    corrections: list[Correction]
