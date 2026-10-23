"""Claude Code hook: enroll actual local projects; native Engram handles replication.

Shares the lock file with the Codex hook so both agents never enroll concurrently.
Scratch workspaces (scratch-*) are never enrolled."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

MISSING = """
SELECT project FROM (
    SELECT project FROM observations WHERE deleted_at IS NULL
    UNION SELECT project FROM sessions
    UNION SELECT project FROM user_prompts
)
WHERE project IS NOT NULL AND project != '' AND project NOT LIKE 'scratch-%'
EXCEPT SELECT project FROM sync_enrolled_projects
"""


def try_lock(f):
    """Non-blocking exclusive lock; raises OSError while another session holds it."""
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)


def engram_command():
    # GUI-launched agents may run hooks without Homebrew on PATH.
    return [shutil.which('engram') or '/opt/homebrew/bin/engram']


def enroll_missing(data_dir, engram):
    data_dir = Path(data_dir).resolve()
    db = data_dir / 'engram.db'
    if not db.is_file():
        return 0
    # One enrollment pass per database, even with several simultaneous agent sessions.
    fd = os.open(data_dir / 'codex-auto-enroll.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        try:
            try_lock(lock)
        except OSError:
            return 0
        with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2) as conn:
            missing = [row[0] for row in conn.execute(MISSING)]
        if not missing:
            return 0
        env = {k: v for k, v in os.environ.items() if not k.startswith('ENGRAM_CLOUD_')}
        env.update(ENGRAM_DATA_DIR=str(data_dir), ENGRAM_CLOUD_AUTOSYNC='0')
        deadline = time.monotonic() + 90
        completed = 0
        failed = False
        for project in missing:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failed = True
                break
            try:
                subprocess.run(
                    [*engram, 'cloud', 'enroll', project],
                    env=env, cwd=str(data_dir), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=True, timeout=min(30, remaining),
                )
                # Native CLI help aliases can exit 0 without enrolling anything.
                with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2) as conn:
                    exists = conn.execute(
                        'SELECT 1 FROM sync_enrolled_projects WHERE project = ?', (project,)
                    ).fetchone()
                if not exists:
                    raise RuntimeError('Enrollment was not persisted')
                completed += 1
            except (OSError, subprocess.SubprocessError, sqlite3.Error, RuntimeError):
                failed = True
        if failed:
            raise RuntimeError('Some projects remain unenrolled')
        return completed


def main():
    try:
        enroll_missing(Path.home() / '.engram', engram_command())
    except Exception:
        # Fail visibly but never block a turn or expose subprocess output/secrets.
        print(json.dumps({'systemMessage':
            'Engram: no se pudo completar la inscripción automática. '
            'Las memorias siguen locales; se reintentará en el siguiente evento. '
            'Si se repite, revisa los proyectos pendientes de inscripción.'}))


if __name__ == '__main__':
    main()
