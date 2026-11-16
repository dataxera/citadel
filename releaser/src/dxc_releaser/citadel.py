# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import os
from .base import BaseReleaser

# Configuration
VERSION_FILE = "VERSION.txt"
CHART_FILE = "charts/citadel/Chart.yaml"
IMAGE_NAME = "citadel"
CHANGELOG_FILE = "CHANGELOG.md"


class CitadelReleaser(BaseReleaser):
    def prep(self, version=None):
        """Prepare release: update versions, build docker, package helm."""
        current_app_version = self.get_version(VERSION_FILE)
        recommended_app_version = current_app_version.replace("-alpha", "")
        if not version:
            version = self.prompt(
                f"Enter app version to release [{recommended_app_version}]: ",
                default=recommended_app_version
            )

        current_chart_version = self.get_chart_version(CHART_FILE)
        recommended_chart_version = current_chart_version
        new_chart_version = self.prompt(
            f"Enter chart version to release [{recommended_chart_version}]: ",
            default=recommended_chart_version
        )

        print(
            f"Preparing Citadel release {version} (Chart: {new_chart_version}) ..."
        )
        self.set_version(VERSION_FILE, version)
        self.update_chart(CHART_FILE, version=new_chart_version, app_version=version)

        # Build Container Image
        image_tag = f"{self.registry}/{IMAGE_NAME}:{version}"
        latest_tag = f"{self.registry}/{IMAGE_NAME}:latest"
        print(f"Building container image {image_tag} ...")
        self.run_command(["docker", "build", "-t", image_tag, "-t", latest_tag, "."])

        # Build Helm Package
        if os.path.isdir("charts/citadel"):
            print("Updating Helm dependencies ...")
            self.run_command(["helm", "dependency", "update", "charts/citadel"])

            print("Packaging Helm chart ...")
            self.run_command(["helm", "package", "charts/citadel"])
        else:
            print(
                "Warning: charts/citadel directory not found, skipping helm packaging."
            )

        print(f"Successfully prepared release {version}")
        return version

    def push(self, version=None):
        """Push release: push docker images, push helm package."""
        if not version:
            version = self.get_version(VERSION_FILE)

        print(f"Pushing Citadel container images for version {version} ...")
        self.run_command(["docker", "push", f"{self.registry}/{IMAGE_NAME}:{version}"])
        self.run_command(["docker", "push", f"{self.registry}/{IMAGE_NAME}:latest"])

        chart_package = f"citadel-{version}.tgz"
        if os.path.exists(chart_package):
            print(f"Pushing Helm package {chart_package} to {self.chart_registry} ...")
            self.run_command(["helm", "push", chart_package, self.chart_registry])
        else:
            print(f"Warning: Helm package {chart_package} not found, skipping push.")

        print(f"Release {version} pushed successfully!")

    def post(self, version=None):
        """Post-release: git commit/tag/push current state, then bump version for next cycle."""
        if not version:
            version = self.get_version(VERSION_FILE)

        # 1. Commit and tag the release first
        # These files should have been updated in 'prep' to the release version
        self.git_ops(
            version_files=[VERSION_FILE, CHART_FILE, CHANGELOG_FILE],
            tag=f"v{version}",
            message=f"release {version}",
        )

        # 2. Bump versions for next development cycle
        recommended_next = self.bump_version_patch(version)
        if "-alpha" not in recommended_next:
            recommended_next = f"{recommended_next}-alpha"

        print(f"Current version released: {version}")
        next_version = self.prompt(
            f"Enter next development version [{recommended_next}]: ",
            default=recommended_next
        )

        print(f"Starting next development cycle {next_version} ...")
        self.set_version(VERSION_FILE, next_version)
        self.update_chart(CHART_FILE, app_version=next_version)
        self.update_changelog(CHANGELOG_FILE, next_version)

        # 3. Commit the bump
        confirm = self.confirm(
            f"Commit start of next development cycle {next_version}? [y/N]: ",
            default=False,
            is_git=True
        )
        if confirm:
            self.git_commit(
                files=[VERSION_FILE, CHART_FILE, CHANGELOG_FILE],
                message=f"bump version to {next_version}",
            )

    def full(self):
        """Run full release cycle."""
        version = self.prep()
        self.push(version)
        self.post(version)
