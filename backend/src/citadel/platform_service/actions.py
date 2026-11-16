# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from citadel.fw.action import BaseAction
from citadel.platform_service.base import PlatformService


@PlatformService.register_action("restart_service")
class RestartServiceAction(BaseAction):
    """Action to trigger a rolling restart of an active platform service."""

    async def available(self) -> bool:
        """Only available for active platform services."""
        state = await self.svc.platform_state(self.model)
        return state is not None and state.active

    async def __call__(self, **kwargs):
        """Trigger a rolling restart of the platform service workloads."""
        return await self.svc.restart_service(self.model)
