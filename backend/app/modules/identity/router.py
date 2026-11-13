from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app.modules.identity import email as mail
from app.modules.identity.cookies import (
    REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from app.modules.identity.deps import (
    CurrentUser,
    Session,
    SettingsDep,
    client_ip,
    csrf_guard,
    limiter_dep,
    no_store,
    origin_guard,
)
from app.modules.identity.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    SignInRequest,
    SignUpRequest,
    UpdateMeRequest,
    UserOut,
)
from app.modules.identity.service import IdentityService, IssuedSession

router = APIRouter(
    prefix="/auth", tags=["auth"], dependencies=[Depends(no_store), Depends(origin_guard)]
)


def service_dep(
    request: Request,
    db: Session,
    settings: SettingsDep,
) -> IdentityService:
    return IdentityService(
        db=db,
        settings=settings,
        passwords=request.app.state.passwords,
        limiter=limiter_dep(request),
    )


Svc = Annotated[IdentityService, Depends(service_dep)]


def _respond(response: Response, settings: SettingsDep, issued: IssuedSession) -> UserOut:
    set_session_cookies(
        response,
        settings,
        access=issued.access,
        refresh=issued.refresh,
        csrf=issued.csrf,
        refresh_expires=issued.refresh_expires,
        now=issued.now,
    )
    return UserOut.model_validate(issued.user)


@router.post("/sign-up", status_code=201, response_model=UserOut)
async def sign_up(
    body: SignUpRequest, request: Request, response: Response, svc: Svc, settings: SettingsDep
) -> UserOut:
    issued = await svc.sign_up(
        email=body.email,
        password=body.password,
        display_name=body.display_name,
        locale=body.locale,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _respond(response, settings, issued)


@router.post("/sign-in", response_model=UserOut)
async def sign_in(
    body: SignInRequest, request: Request, response: Response, svc: Svc, settings: SettingsDep
) -> UserOut:
    issued = await svc.sign_in(
        email=body.email,
        password=body.password,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return _respond(response, settings, issued)


@router.post("/refresh", response_model=UserOut, dependencies=[Depends(csrf_guard)])
async def refresh(request: Request, response: Response, svc: Svc, settings: SettingsDep) -> UserOut:
    from app.core.errors import AppError

    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AppError(401, "SESSION_INVALID", "Session is no longer valid")
    issued = await svc.refresh(
        token=token, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    return _respond(response, settings, issued)


@router.post("/sign-out", status_code=204)
async def sign_out(request: Request, response: Response, svc: Svc, settings: SettingsDep) -> None:
    # Origin-checked only: forcing someone's sign-out is a nuisance, not a takeover, and the
    # client may be signing out with an expired access cookie.
    from app.modules.identity.cookies import ACCESS_COOKIE
    from app.modules.identity.tokens import TokenError, decode_access_token

    session_id = None
    access = request.cookies.get(ACCESS_COOKIE)
    if access:
        try:
            session_id = decode_access_token(settings, access).session_id
        except TokenError:
            session_id = None
    await svc.sign_out(refresh_token=request.cookies.get(REFRESH_COOKIE), session_id=session_id)
    clear_session_cookies(response, settings)


@router.post("/password/forgot", status_code=202)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    svc: Svc,
    settings: SettingsDep,
) -> dict[str, str]:
    result = await svc.request_reset(email=body.email, ip=client_ip(request))
    if result is not None:
        user, raw = result
        # Token travels in the URL fragment: it is never sent to servers, logs or referrers.
        link = f"{settings.app_origin}/{user.locale}/reset-password#token={raw}"
        subject, text = mail.reset_email(user.locale, link, settings.reset_ttl_minutes)
        background.add_task(
            mail.safe_send,
            request.app.state.email_sender,
            to=user.email,
            subject=subject,
            body=text,
        )
    return {"status": "accepted"}


@router.post("/password/reset", status_code=204)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    svc: Svc,
    settings: SettingsDep,
) -> None:
    await svc.reset_password(token=body.token, new_password=body.password, ip=client_ip(request))
    clear_session_cookies(response, settings)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut, dependencies=[Depends(csrf_guard)])
async def update_me(body: UpdateMeRequest, user: CurrentUser, db: Session) -> UserOut:
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in data.items():
        setattr(user, key, value)
    await db.commit()
    return UserOut.model_validate(user)
