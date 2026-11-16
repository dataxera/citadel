# SPDX-FileCopyrightText: Copyright © 2025 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from .service import ProjectService
from .model import Project
import citadel.service.project.state
import citadel.service.project.actions
from . import views


router = ProjectService.router()

__all__ = ["ProjectService", "Project", "router"]
