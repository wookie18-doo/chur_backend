from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.base.base import RequestUser
from app.api.dependencies.auth import require_auth
from app.api.dependencies.users import get_user_service
from app.api.v1.users.schema import (
    ForgotPasswordRequest,
    LoginRequest,
    RequestOtpRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserRead,
    UserUpdate,
    VerifyEmailRequest,
    VerifyOtpRequest,
)
from app.config.settings import settings
from app.db.sql.models.users import User
from app.services.auth_service import InvalidTokenError
from app.services.user_service import (
    InvalidCredentialsError,
    InvalidOtpError,
    UserConflictError,
    UserService,
)

router = APIRouter()


def _issue_session(
    user: User, response: Response, user_service: UserService
) -> TokenResponse | None:
    """
    Issue an access token for ``user`` and set the session cookie.

    Shared by :func:`login` and :func:`verify_otp` -- both end the same way,
    once a user has been confirmed by whatever means.

    :param user: the user to start a session for.
    :param response: current response, used to set the auth cookie.
    :param user_service: user service.
    :return: the issued token, if JWT
        auth is also enabled -- otherwise the session cookie alone carries it.
    """
    token = user_service.issue_access_token(user)
    response.set_cookie(
        key=settings.users_cookie_name,
        value=token,
        httponly=True,
        # "pytest" runs the app over plain http (see broker.py's own
        # environment check) -- a Secure cookie would never come back.
        secure=settings.environment.lower() not in ("dev", "pytest"),
        samesite="lax",
        max_age=settings.users_access_token_lifetime_seconds,
    )
    return TokenResponse(access_token=token)


@router.post(
    "/auth/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    tags=["auth"],
)
async def register(
    user_create: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> User:
    """
    Register a new user and kick off email verification.

    :param user_create: registration payload.
    :param user_service: user service.
    :return: the newly created user.
    """
    return await user_service.register(
        email=user_create.email,
        password=user_create.password,
        phone=user_create.phone,
        username=user_create.username,
        first_name=user_create.first_name,
        last_name=user_create.last_name,
    )


@router.post("/auth/login", tags=["auth"])
async def login(
    credentials: LoginRequest,
    response: Response,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse | None:
    """
    Authenticate a user and issue an access token.

    :param credentials: email/password payload.
    :param response: current response, used to set the auth cookie.
    :param user_service: user service.
    :raises HTTPException: 401, if the credentials are invalid.
    :return: see :func:`_issue_session`.
    """
    try:
        user = await user_service.authenticate(credentials.email, credentials.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc

    return _issue_session(user, response, user_service)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def logout(response: Response) -> None:
    """
    Clear the session cookie.

    JWT bearer tokens aren't tracked server-side, so there's nothing to
    revoke for API clients using the ``Authorization`` header -- they just
    discard the token.

    :param response: current response, used to clear the auth cookie.
    """
    response.delete_cookie(settings.users_cookie_name)


@router.post(
    "/auth/forgot-password", status_code=status.HTTP_202_ACCEPTED, tags=["auth"]
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    user_service: UserService = Depends(get_user_service),
) -> None:
    """
    Request a password reset email.

    Always responds 202, whether or not the email is registered, so callers
    can't use this endpoint to enumerate accounts.

    :param payload: email to send the reset link to.
    :param user_service: user service.
    """
    await user_service.request_password_reset(payload.email)


@router.post(
    "/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"]
)
async def reset_password(
    payload: ResetPasswordRequest,
    user_service: UserService = Depends(get_user_service),
) -> None:
    """
    Consume a password-reset token and set a new password.

    :param payload: reset token and new password.
    :param user_service: user service.
    :raises HTTPException: 400, if the token is invalid or expired.
    """
    try:
        await user_service.reset_password(payload.token, payload.new_password)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        ) from exc


@router.post("/auth/verify", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def verify_email(
    payload: VerifyEmailRequest,
    user_service: UserService = Depends(get_user_service),
) -> None:
    """
    Consume an email-verification token.

    :param payload: verification token.
    :param user_service: user service.
    :raises HTTPException: 400, if the token is invalid or expired.
    """
    try:
        await user_service.verify_email(payload.token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        ) from exc


@router.post("/auth/otp/request", status_code=status.HTTP_202_ACCEPTED, tags=["auth"])
async def request_otp(
    payload: RequestOtpRequest,
    user_service: UserService = Depends(get_user_service),
) -> None:
    """
    Send a one-time-password for passwordless login.

    Always responds 202, whether or not the email is registered, so callers
    can't use this endpoint to enumerate accounts.

    :param payload: email to send the OTP to.
    :param user_service: user service.
    """
    await user_service.send_otp(payload.email)


@router.post("/auth/otp/verify", tags=["auth"])
async def verify_otp(
    payload: VerifyOtpRequest,
    response: Response,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse | None:
    """
    Consume an OTP code and issue an access token, like :func:`login`.

    :param payload: email and OTP code.
    :param response: current response, used to set the auth cookie.
    :param user_service: user service.
    :raises HTTPException: 401, if the OTP is missing, expired, or wrong.
    :return: see :func:`_issue_session`.
    """
    try:
        user = await user_service.verify_otp(payload.email, payload.code)
    except InvalidOtpError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        ) from exc

    return _issue_session(user, response, user_service)


@router.get("/users/me", response_model=UserRead, tags=["users"])
async def read_current_user(user: RequestUser = Depends(require_auth)) -> User:
    """
    Return the currently authenticated user.

    :param user: the authenticated user proxy.
    :return: the user.
    """
    # require_auth already guarantees unwrap() isn't None here.
    return cast(User, user.unwrap())


@router.patch("/users/me", response_model=UserRead, tags=["users"])
async def update_current_user(
    payload: UserUpdate,
    user: RequestUser = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
) -> User:
    """
    Update the authenticated user's profile.

    :param payload: fields to change; omitted ones stay as they are.
    :param user: the authenticated user proxy.
    :param user_service: user service.
    :raises HTTPException: 409, if the phone or username is already taken.
    :return: the updated user.
    """
    try:
        return await user_service.update_profile(
            cast(User, user.unwrap()), **payload.model_dump(exclude_unset=True)
        )
    except UserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone or username is already taken.",
        ) from exc


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT, tags=["users"])
async def delete_current_user(
    response: Response,
    user: RequestUser = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
) -> None:
    """
    Permanently delete the authenticated user and all of their data.

    :param response: current response, used to clear the auth cookie.
    :param user: the authenticated user proxy.
    :param user_service: user service.
    """
    await user_service.delete_account(cast(User, user.unwrap()))
    response.delete_cookie(settings.users_cookie_name)
