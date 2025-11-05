from pathlib import Path
from datetime import datetime
from shutil import move
from django.utils.timezone import now
from .models import AuditFile

def archive_files(audit_ids: list[int]):
    ts = datetime.utcnow().strftime("%Y-%m")
    archived = []
    for af in AuditFile.objects.filter(id__in=audit_ids):
        src = Path(af.file_path)
        if not src.exists():
            continue
        dst_dir = src.parent / "archive" / ts
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        move(str(src), str(dst))
        af.file_path = str(dst)
        af.archived_at = now()
        af.save(update_fields=["file_path", "archived_at"])
        archived.append(af.id)
    return {"archived_ids": archived}
