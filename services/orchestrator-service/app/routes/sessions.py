import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from starlette.responses import Response, StreamingResponse

from app.repositories import correction_repo, turn_repo
from app.schemas import (
    CorrectionRead,
    SessionDetail,
    SessionRead,
    TurnRead,
    TurnResult,
)
from app.services.session_service import SessionService
from app.utils import audio_storage
from app.utils.dependencies import get_current_user_id, get_session_service
from app.utils.exceptions import NotSessionOwner, SessionClosed, SessionNotFound

router = APIRouter(prefix="/sessions", tags=["sessions"])


def audio_url(session_id: uuid.UUID, turn_id: uuid.UUID) -> str:
    return f"/sessions/{session_id}/turns/{turn_id}/audio"


@router.get("", response_model=list[SessionRead])
async def list_sessions(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
) -> list[SessionRead]:
    sessions = await service.list_sessions(user_id)
    return [SessionRead.model_validate(s) for s in sessions]


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def start_session(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
) -> SessionRead:
    session_row = await service.start_session(user_id)
    return SessionRead.model_validate(session_row)


@router.post("/{session_id}/turns", response_model=TurnResult)
async def add_turn(
    session_id: uuid.UUID,
    audio: UploadFile,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
) -> TurnResult:
    data = await audio.read()
    try:
        (
            assistant_turn,
            transcript,
            language,
            spoken_reply,
            corrections,
        ) = await service.add_turn(session_id, user_id, data)
    except (SessionNotFound, NotSessionOwner) as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except SessionClosed as exc:
        raise HTTPException(status_code=409, detail="Session is closed") from exc

    return TurnResult(
        turn_id=assistant_turn.id,
        transcript=transcript,
        language=language,
        spoken_reply=spoken_reply,
        corrections=[CorrectionRead.model_validate(c) for c in corrections],
        audio_url=audio_url(session_id, assistant_turn.id),
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
) -> SessionDetail:
    try:
        session_row = await service.get_owned_session(session_id, user_id)
    except (SessionNotFound, NotSessionOwner) as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc

    turns = await turn_repo.list_turns_by_session(service.db, session_id)

    # Fetch every turn's corrections in one query, then group by turn_id (avoids N+1).
    all_corrections = await correction_repo.list_corrections_by_turns(
        service.db, [turn.id for turn in turns]
    )
    corrections_by_turn: dict[uuid.UUID, list[CorrectionRead]] = {}
    for correction in all_corrections:
        corrections_by_turn.setdefault(correction.turn_id, []).append(
            CorrectionRead.model_validate(correction)
        )

    turn_reads = []
    for turn in turns:
        turn_reads.append(
            TurnRead(
                id=turn.id,
                role=turn.role,
                text=turn.text,
                language=turn.language,
                corrections=corrections_by_turn.get(turn.id, []),
                created_at=turn.created_at,
                audio_url=audio_url(session_id, turn.id) if turn.audio_path else None,
            )
        )
    return SessionDetail(
        id=session_row.id,
        user_id=session_row.user_id,
        status=session_row.status,
        summary=session_row.summary,
        created_at=session_row.created_at,
        turns=turn_reads,
    )


@router.post("/{session_id}/close", response_model=SessionRead)
async def close_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
) -> SessionRead:
    try:
        session_row = await service.close_session(session_id, user_id)
    except (SessionNotFound, NotSessionOwner) as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    return SessionRead.model_validate(session_row)


@router.get("/{session_id}/turns/{turn_id}/audio")
async def get_turn_audio(
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SessionService = Depends(get_session_service),
) -> Response:
    """Stream a turn's audio, honouring HTTP Range so <audio> can play and seek."""
    try:
        await service.get_owned_session(session_id, user_id)
    except (SessionNotFound, NotSessionOwner) as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc

    path = audio_storage.audio_path(session_id, turn_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")

    file_size = path.stat().st_size
    start, end = 0, file_size - 1
    status_code = status.HTTP_200_OK
    headers = {"accept-ranges": "bytes"}

    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        spec = range_header.removeprefix("bytes=").split(",")[0]
        start_s, _, end_s = spec.partition("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        if start > end:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Range not satisfiable",
            )
        status_code = status.HTTP_206_PARTIAL_CONTENT
        headers["content-range"] = f"bytes {start}-{end}/{file_size}"

    headers["content-length"] = str(end - start + 1)
    return StreamingResponse(
        audio_storage.iter_audio(path, start, end),
        status_code=status_code,
        media_type="audio/wav",
        headers=headers,
    )
