"""Return a local directory path without uploading repository files to a browser."""

import json
from pathlib import Path
import subprocess
import sys

from repolens.errors import RepoLensError


# Arguments carry paths separately from executable code, including quotes/spaces.
_MAC_CHOOSER = """
on run argv
    if (count of argv) > 0 then
        set chosenFolder to choose folder ¬
            with prompt "Choose a repository folder for RepoLens" ¬
            default location (POSIX file (item 1 of argv))
    else
        set chosenFolder to choose folder ¬
            with prompt "Choose a repository folder for RepoLens"
    end if
    return POSIX path of chosenFolder
end run
"""

# Tk must own its main thread. A child process avoids creating GUI objects on
# Streamlit's script thread and releases the desktop toolkit after each choice.
_TK_CHOOSER = """
import json
import sys
import tkinter as tk
from tkinter import filedialog

window = tk.Tk()
window.withdraw()
try:
    options = {"title": "Choose a repository folder for RepoLens", "mustexist": True}
    if len(sys.argv) > 1:
        options["initialdir"] = sys.argv[1]
    folder = filedialog.askdirectory(parent=window, **options)
    print(json.dumps(folder))
finally:
    window.destroy()
"""


def choose_repository_folder(initial: Path | None = None) -> Path | None:
    """Open the server computer's chooser; cancellation leaves selection unchanged."""
    failure = (
        "The desktop folder chooser is unavailable or could not finish. "
        "Use Folder options to enter the path manually, then try again."
    )
    try:
        is_mac = sys.platform == "darwin"
        command = (
            ["/usr/bin/osascript", "-e", _MAC_CHOOSER]
            if is_mac
            else [sys.executable, "-c", _TK_CHOOSER]
        )
        if initial is not None and initial.is_dir():
            command.append(str(initial.resolve()))
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=120, check=False
        )
        if is_mac and result.returncode != 0 and "(-128)" in result.stderr:
            return None
        if result.returncode != 0:
            raise RepoLensError("folder_picker_unavailable", failure)
        selected = result.stdout.rstrip("\r\n") if is_mac else json.loads(result.stdout)
        if not isinstance(selected, str):
            raise ValueError("Invalid directory selection")
        if not selected:
            return None
        folder = Path(selected).expanduser().resolve()
        if not folder.is_dir():
            raise ValueError("Selected directory no longer exists")
        return folder
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise RepoLensError("folder_picker_unavailable", failure) from exc
