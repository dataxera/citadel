# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from pydantic_settings import BaseSettings, SettingsConfigDict


class ReleaserSettings(BaseSettings):
    """Configuration settings for Citadel Releaser."""

    registry: str = "ghcr.io/dataxera/citadel"
    chart_registry: str = "oci://ghcr.io/dataxera/citadel/charts"

    model_config = SettingsConfigDict(
        env_prefix="DXC_",
        case_sensitive=False,
    )


settings = ReleaserSettings()
