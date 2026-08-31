from pydantic import BaseModel

from app.models.correction import Correction


class Corrections(BaseModel):
    """Corrections-only structured output for the realtime pipeline (E4).

    The spoken reply is streamed as plain text separately; this second pass returns just
    the grammar notes, so the two concerns never share one response.
    """

    corrections: list[Correction]
