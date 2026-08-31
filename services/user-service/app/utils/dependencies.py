from fastapi import HTTPException, Request, status


def get_current_user_id(request: Request) -> str:
    """Return the user id put on the request by the `jwt_auth` middleware.

    Raises 401 when there was no valid access token on the request.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return str(user_id)
