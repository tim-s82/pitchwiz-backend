"""
Version and build information for PitchWiz Backend.
"""

import functools
import os
import subprocess

VERSION = "1.0.1"
DEFAULT_BUILD_DATE = "2026-10-17"


@functools.lru_cache(maxsize=1)
def get_build_info() -> dict:
    """
    Returns build and version metadata for the backend service.

    Checks environment variables first (useful for Docker, Render, CI/CD),
    then attempts git inspection as fallback for local dev, and finally
    defaults to static package version info.
    """
    version = os.environ.get("BACKEND_VERSION", VERSION)

    # 1. Check env vars for commit & date (e.g. Render, CI)
    commit = os.environ.get("RENDER_GIT_COMMIT", os.environ.get("GIT_COMMIT", ""))
    build_date = os.environ.get("BUILD_DATE", os.environ.get("RENDER_GIT_COMMIT_DATE", ""))

    # 2. Fallback to local git if available
    if not commit or not build_date:
        try:
            if not commit:
                commit = (
                    subprocess.check_output(
                        ["git", "rev-parse", "--short", "HEAD"],
                        stderr=subprocess.DEVNULL,
                        timeout=1,
                    )
                    .decode()
                    .strip()
                )
        except Exception:
            pass

        try:
            if not build_date:
                git_date = (
                    subprocess.check_output(
                        ["git", "log", "-1", "--format=%cs"],
                        stderr=subprocess.DEVNULL,
                        timeout=1,
                    )
                    .decode()
                    .strip()
                )
                if git_date:
                    build_date = git_date
        except Exception:
            pass

    # 3. Final fallback
    if not build_date:
        build_date = DEFAULT_BUILD_DATE

    return {
        "service": "pitchwiz-backend",
        "version": version,
        "build_date": build_date,
        "commit": commit[:7] if commit else None,
    }
