"""
Various system-level checks such as whether packages exist, architecture, etc.
"""

import os
import platform
import rich_click as click
import shutil

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from rich.markdown import Markdown

from harpy.common.printing import HarpyPrint

def is_conda_package_installed(package_name: str) -> bool:
    """Exact-name match against conda-meta/. Works for conda, mamba and pixi, no `conda` module needed."""
    prefix = os.environ.get("CONDA_PREFIX")
    if not prefix:
        return False
    # records are named <name>-<version>-<build>.json
    return any(
        p.name.rsplit("-", 2)[0] == package_name
        for p in Path(prefix, "conda-meta").glob(f"{package_name}-*.json")
    )


def is_pip_package_installed(package_name: str) -> bool:
    try:
        version(package_name)
        return True
    except PackageNotFoundError:
        return False


def is_installed(pkg: str) -> bool:
    return is_conda_package_installed(pkg) or is_pip_package_installed(pkg)


def is_pixi_shell() -> bool:
    return any(v in os.environ for v in (
        "PIXI_PROJECT_ROOT", "PIXI_PROJECT_NAME", "PIXI_PROJECT_MANIFEST", "PIXI_ENVIRONMENT_NAME"
    ))


def install_cmd(pkg: str) -> str:
    if is_pixi_shell():
        return f"pixi add {pkg}"
    if "CONDA_PREFIX" in os.environ:
        tool = "mamba" if shutil.which("mamba") else "conda" if shutil.which("conda") else None
        if tool:
            return f"{tool} install -c bioconda {pkg}"
    return f"pip install {pkg}"


def check_snakemake_hpc(plugin: str) -> str:
    """Returns "" if installed, otherwise the install command for the detected environment."""
    return "" if is_installed(plugin) else install_cmd(plugin)

def package_absent(pkg: str, executor: bool = True) -> bool:
    """True (and prints install instructions) if `pkg` is missing from the active environment."""
    if is_installed(pkg):
        return False
    intro = ""
    if executor:
        intro = "Using this scheduler requires installing a Snakemake plugin which wasn't detected in this environment."

    text = Markdown(f"{intro} It can be installed with:\n\n```bash\n{install_cmd(pkg)}\n```")
    if executor:
        HarpyPrint().notice(text)
    else:
        HarpyPrint().error("missing required package", text)
    return True

def container_ok(ctx, param, value) -> bool:
    """
    Check if the system is linux or has apptainer installed
    """
    if value:
        if shutil.which("apptainer"):
            return value

        if platform.system().lower() != 'linux':
            raise click.BadParameter(
                "Snakemake uses Apptainer (formerly Singularity) to manage containers, which is only available for Linux systems.", ctx, param
            )
        else:
            raise click.BadParameter(
                "Container software management requires apptainer, which wasn't detected in this environment.", ctx, param
            )
    return value

def is_arm(allowed: bool) -> None:
    """
    Check if the system uses ARM architecture, for which some workflows or their deps might not work.
    """
    arch = platform.machine().lower()
    # Common ARM identifiers across Linux/macOS: armv7l, armv8l, arm64, aarch64
    _arm = arch.startswith(("arm", "aarch64")) or "arm64" in arch
    if not _arm or allowed:
        return
    else:
        HarpyPrint().error(
            "incompatible architecture",
            "Your system was detected to use an ARM-based processor, for which not all of the software required by this workflow is compatible with and therefore conda will be unable to install. If possible, please try this command again on an x86-based machine (i.e. [blue]Intel[/] or [red]AMD[/] processors)."
        )
