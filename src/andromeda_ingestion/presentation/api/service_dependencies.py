from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_ingestion.application.container import ServiceBundle
from andromeda_ingestion.presentation.api.dependencies import get_session


async def get_services(request: Request, session: AsyncSession = Depends(get_session)) -> ServiceBundle:
    return request.app.state.adapters.services(session)
