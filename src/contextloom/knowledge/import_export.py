import csv
import io
import json
import tempfile
import uuid
import zipfile
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from contextloom.knowledge.exceptions import ImportValidationError
from contextloom.knowledge.forms import ImportConfirmForm, ImportUploadForm
from contextloom.knowledge.models import Archive, Category, ImportJob, Memory

FORMAT_VERSION = 1
EXPECTED_FILES = {"manifest.json", "categories.csv", "memories.csv", "archives.csv"}
CSV_FIELDS = {
    "categories.csv": [
        "export_id",
        "parent_export_id",
        "name",
        "description",
        "created_at",
        "updated_at",
    ],
    "memories.csv": [
        "export_id",
        "category_export_id",
        "content",
        "priority",
        "created_at",
        "updated_at",
    ],
    "archives.csv": ["export_id", "name", "created_at", "snapshot"],
}


def _safe_cell(value):
    value = str(value if value is not None else "")
    if value.startswith("'"):
        return f"'{value}"
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


def _restore_cell(value):
    if value.startswith("''"):
        return value[1:]
    if value.startswith("'") and value[1:].startswith(("=", "+", "-", "@")):
        return value[1:]
    return value


def _csv_bytes(fieldnames, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _safe_cell(row.get(key, "")) for key in fieldnames})
    return output.getvalue().encode("utf-8")


def _portable_snapshot(snapshot):
    key_map = {row["key"]: str(uuid.uuid4()) for row in snapshot.get("categories", [])}
    return {
        "version": 1,
        "categories": [
            {
                **row,
                "key": key_map[row["key"]],
                "parent_key": key_map.get(row.get("parent_key")),
            }
            for row in snapshot.get("categories", [])
        ],
        "memories": [
            {**row, "category_key": key_map[row["category_key"]]}
            for row in snapshot.get("memories", [])
        ],
    }


def build_export(owner):
    category_ids = {
        category.pk: str(uuid.uuid4()) for category in Category.objects.filter(owner=owner)
    }
    categories = [
        {
            "export_id": category_ids[category.pk],
            "parent_export_id": category_ids.get(category.parent_id, ""),
            "name": category.name,
            "description": category.description,
            "created_at": category.created_at.isoformat(),
            "updated_at": category.updated_at.isoformat(),
        }
        for category in Category.objects.filter(owner=owner).order_by("id")
    ]
    memories = [
        {
            "export_id": str(uuid.uuid4()),
            "category_export_id": category_ids[memory.category_id],
            "content": memory.content,
            "priority": memory.priority,
            "created_at": memory.created_at.isoformat(),
            "updated_at": memory.updated_at.isoformat(),
        }
        for memory in Memory.objects.filter(owner=owner).order_by("id")
    ]
    archives = [
        {
            "export_id": str(uuid.uuid4()),
            "name": archive.name,
            "created_at": archive.created_at.isoformat(),
            "snapshot": json.dumps(_portable_snapshot(archive.snapshot), ensure_ascii=False),
        }
        for archive in Archive.objects.filter(owner=owner).order_by("id")
    ]
    files = {
        "categories.csv": _csv_bytes(CSV_FIELDS["categories.csv"], categories),
        "memories.csv": _csv_bytes(CSV_FIELDS["memories.csv"], memories),
        "archives.csv": _csv_bytes(CSV_FIELDS["archives.csv"], archives),
    }
    manifest = {
        "format": "contextloom-export",
        "format_version": FORMAT_VERSION,
        "application_version": settings.CONTEXTLOOM_VERSION,
        "exported_at": timezone.now().isoformat(),
        "files": [
            {"name": name, "rows": len(rows)}
            for name, rows in (
                ("categories.csv", categories),
                ("memories.csv", memories),
                ("archives.csv", archives),
            )
        ],
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    spool = tempfile.SpooledTemporaryFile(max_size=settings.CONTEXTLOOM_EXPORT_SPOOL_LIMIT)
    with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    spool.seek(0)
    return spool


@login_required
def export_data(request):
    filename = f"contextloom-export-{timezone.localdate().isoformat()}.zip"
    return FileResponse(build_export(request.user), as_attachment=True, filename=filename)


def _parse_uuid(value, label, errors):
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        errors.append(f"{label} must be a UUID.")
        return value


def _parse_timestamp(value, label, errors):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or not 1970 <= parsed.year <= datetime.now().year + 1:
            raise ValueError
    except (ValueError, TypeError):
        errors.append(f"{label} is not a valid timestamp.")


def _check_fields(row, row_label, errors):
    for field, value in row.items():
        if value is None:
            errors.append(f"{row_label} has missing fields.")
        elif len(value) > settings.CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH:
            errors.append(f"{row_label} field {field} is too long.")


def _validate_hierarchy(rows, errors, label="category"):
    ids = {row["export_id"] for row in rows}
    parents = {row["export_id"]: row.get("parent_export_id") or None for row in rows}
    for export_id, parent in parents.items():
        if parent and parent not in ids:
            errors.append(f"{label} {export_id} references a missing parent.")
    for export_id in ids:
        seen = set()
        current = export_id
        depth = 0
        while current:
            if current in seen:
                errors.append(f"{label} hierarchy contains a cycle.")
                break
            seen.add(current)
            current = parents.get(current)
            depth += 1
            if depth > settings.CONTEXTLOOM_IMPORT_MAX_DEPTH:
                errors.append(f"{label} hierarchy exceeds the maximum depth.")
                break


def _validate_snapshot(value, label, errors):
    try:
        snapshot = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        errors.append(f"{label} snapshot is not valid JSON.")
        return None
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        errors.append(f"{label} snapshot has an unsupported version.")
        return None
    categories = snapshot.get("categories")
    memories = snapshot.get("memories")
    if not isinstance(categories, list) or not isinstance(memories, list):
        errors.append(f"{label} snapshot has invalid record lists.")
        return None
    if len(categories) + len(memories) > settings.CONTEXTLOOM_IMPORT_MAX_ROWS:
        errors.append(f"{label} snapshot has too many records.")
        return None
    normalized = []
    ids = set()
    for number, row in enumerate(categories, 1):
        if not isinstance(row, dict) or not {"key", "name"}.issubset(row):
            errors.append(f"{label} category row {number} is malformed.")
            continue
        export_id = _parse_uuid(row["key"], f"{label} category row {number} key", errors)
        if export_id in ids:
            errors.append(f"{label} has duplicate category export IDs.")
        ids.add(export_id)
        name = row["name"]
        description = row.get("description", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            errors.append(f"{label} category row {number} has an invalid name.")
        if (
            not isinstance(description, str)
            or len(description) > settings.CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH
        ):
            errors.append(f"{label} category row {number} has an invalid description.")
        for timestamp_name in ("created_at", "updated_at"):
            if timestamp_name not in row:
                errors.append(f"{label} category row {number} has a missing timestamp.")
            else:
                _parse_timestamp(
                    row[timestamp_name],
                    f"{label} category row {number} {timestamp_name}",
                    errors,
                )
        parent = row.get("parent_key")
        if parent:
            parent = _parse_uuid(parent, f"{label} category row {number} parent", errors)
        normalized.append({**row, "key": export_id, "parent_key": parent})
    hierarchy_rows = [
        {"export_id": row["key"], "parent_export_id": row.get("parent_key")} for row in normalized
    ]
    _validate_hierarchy(hierarchy_rows, errors, f"{label} category")
    clean_memories = []
    for number, row in enumerate(memories, 1):
        if not isinstance(row, dict) or not {"category_key", "content", "priority"}.issubset(row):
            errors.append(f"{label} memory row {number} is malformed.")
            continue
        category_key = _parse_uuid(
            row["category_key"], f"{label} memory row {number} category", errors
        )
        if category_key not in ids:
            errors.append(f"{label} memory row {number} references a missing category.")
        if (
            not isinstance(row["content"], str)
            or len(row["content"]) > settings.CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH
        ):
            errors.append(f"{label} memory row {number} has invalid content.")
        if not isinstance(row["priority"], int) or not 1 <= row["priority"] <= 5:
            errors.append(f"{label} memory row {number} has invalid priority.")
        for timestamp_name in ("created_at", "updated_at"):
            if timestamp_name not in row:
                errors.append(f"{label} memory row {number} has a missing timestamp.")
            else:
                _parse_timestamp(
                    row[timestamp_name],
                    f"{label} memory row {number} {timestamp_name}",
                    errors,
                )
        clean_memories.append({**row, "category_key": category_key})
    return {"version": 1, "categories": normalized, "memories": clean_memories}


def parse_import(payload):
    errors = []
    if len(payload) > settings.CONTEXTLOOM_IMPORT_MAX_BYTES:
        raise ImportValidationError("The uploaded archive is too large.")
    try:
        source = io.BytesIO(payload)
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            names = {item.filename for item in infos}
            if len(infos) != len(EXPECTED_FILES) or names != EXPECTED_FILES:
                errors.append("The ZIP file inventory is invalid or contains unexpected files.")
            if any(
                item.is_dir()
                or item.filename.startswith(("/", "\\"))
                or ".." in item.filename.replace("\\", "/").split("/")
                for item in infos
            ):
                errors.append("The ZIP contains an unsafe path.")
            if (
                sum(item.file_size for item in infos)
                > settings.CONTEXTLOOM_IMPORT_MAX_EXPANDED_BYTES
            ):
                errors.append("The expanded archive is too large.")
            if errors:
                raise ImportValidationError(errors)
            content = {name: archive.read(name) for name in EXPECTED_FILES}
    except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise ImportValidationError("The upload is not a valid ContextLoom ZIP archive.") from exc
    try:
        manifest = json.loads(content["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise ImportValidationError("manifest.json is malformed.") from exc
    if manifest.get("format") != "contextloom-export":
        errors.append("The manifest format is not ContextLoom export.")
    if manifest.get("format_version") != FORMAT_VERSION:
        errors.append("The export format version is not supported.")
    inventory = manifest.get("files")
    inventory_names = {item.get("name") for item in inventory or [] if isinstance(item, dict)}
    if not isinstance(inventory, list) or inventory_names != EXPECTED_FILES - {"manifest.json"}:
        errors.append("The manifest file inventory is invalid.")
    rows = {}
    for filename, fields in CSV_FIELDS.items():
        try:
            text = content[filename].decode("utf-8")
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            if reader.fieldnames != fields:
                errors.append(f"{filename} has an invalid header.")
                rows[filename] = []
                continue
            rows[filename] = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    errors.append(f"{filename} contains a malformed row.")
                    continue
                rows[filename].append({key: _restore_cell(value) for key, value in row.items()})
        except (UnicodeDecodeError, csv.Error) as exc:
            errors.append(f"{filename} is malformed: {exc}.")
            rows[filename] = []
    total_rows = sum(len(value) for value in rows.values())
    if total_rows > settings.CONTEXTLOOM_IMPORT_MAX_ROWS:
        errors.append("The import contains too many rows.")
    inventory_rows = {
        item["name"]: item.get("rows")
        for item in inventory or []
        if isinstance(item, dict) and "name" in item
    }
    for filename in CSV_FIELDS:
        if inventory_rows.get(filename) != len(rows[filename]):
            errors.append(f"The manifest row count for {filename} is invalid.")

    category_ids = set()
    for number, row in enumerate(rows["categories.csv"], 2):
        _check_fields(row, f"categories.csv row {number}", errors)
        export_id = _parse_uuid(row["export_id"], f"categories.csv row {number} export_id", errors)
        row["export_id"] = export_id
        if export_id in category_ids:
            errors.append("categories.csv contains duplicate export IDs.")
        category_ids.add(export_id)
        if row["parent_export_id"]:
            row["parent_export_id"] = _parse_uuid(
                row["parent_export_id"], f"categories.csv row {number} parent_export_id", errors
            )
        if not row["name"].strip() or len(row["name"]) > 200:
            errors.append(f"categories.csv row {number} has an invalid name.")
        _parse_timestamp(row["created_at"], f"categories.csv row {number} created_at", errors)
        _parse_timestamp(row["updated_at"], f"categories.csv row {number} updated_at", errors)
    _validate_hierarchy(rows["categories.csv"], errors)

    memory_ids = set()
    for number, row in enumerate(rows["memories.csv"], 2):
        _check_fields(row, f"memories.csv row {number}", errors)
        export_id = _parse_uuid(row["export_id"], f"memories.csv row {number} export_id", errors)
        if export_id in memory_ids:
            errors.append("memories.csv contains duplicate export IDs.")
        memory_ids.add(export_id)
        row["category_export_id"] = _parse_uuid(
            row["category_export_id"], f"memories.csv row {number} category_export_id", errors
        )
        if row["category_export_id"] not in category_ids:
            errors.append(f"memories.csv row {number} references a missing category.")
        try:
            row["priority"] = int(row["priority"])
            if not 1 <= row["priority"] <= 5:
                raise ValueError
        except ValueError:
            errors.append(f"memories.csv row {number} has an invalid priority.")
        _parse_timestamp(row["created_at"], f"memories.csv row {number} created_at", errors)
        _parse_timestamp(row["updated_at"], f"memories.csv row {number} updated_at", errors)

    archive_ids = set()
    for number, row in enumerate(rows["archives.csv"], 2):
        _check_fields(row, f"archives.csv row {number}", errors)
        export_id = _parse_uuid(row["export_id"], f"archives.csv row {number} export_id", errors)
        if export_id in archive_ids:
            errors.append("archives.csv contains duplicate export IDs.")
        archive_ids.add(export_id)
        if not row["name"].strip() or len(row["name"]) > 200:
            errors.append(f"archives.csv row {number} has an invalid name.")
        _parse_timestamp(row["created_at"], f"archives.csv row {number} created_at", errors)
        row["snapshot"] = _validate_snapshot(row["snapshot"], f"archives.csv row {number}", errors)
    if errors:
        raise ImportValidationError(errors[:100])
    return {
        "categories": rows["categories.csv"],
        "memories": rows["memories.csv"],
        "archives": rows["archives.csv"],
    }


def _available_name(owner, parent, original):
    name = original
    suffix = 2
    while Category.objects.filter(owner=owner, parent=parent, name=name).exists():
        tail = f" ({suffix})"
        name = f"{original[: 200 - len(tail)]}{tail}"
        suffix += 1
    return name


def summarize_import(owner, data, mode):
    conflicts = 0
    if mode == "merge":
        roots = [row for row in data["categories"] if not row["parent_export_id"]]
        conflicts = sum(
            Category.objects.filter(owner=owner, parent=None, name=row["name"]).exists()
            for row in roots
        )
    return {
        "categories": len(data["categories"]),
        "memories": len(data["memories"]),
        "archives": len(data["archives"]),
        "root_name_conflicts": conflicts,
        "mode": mode,
    }


@transaction.atomic
def apply_import(owner, data, mode):
    if mode == "replace":
        Category.objects.filter(owner=owner).delete()
        Archive.objects.filter(owner=owner).delete()
    created = {}
    pending = list(data["categories"])
    while pending:
        for row in pending[:]:
            parent_id = row["parent_export_id"]
            if parent_id and parent_id not in created:
                continue
            parent = created.get(parent_id)
            name = _available_name(owner, parent, row["name"])
            created[row["export_id"]] = Category.objects.create(
                owner=owner,
                parent=parent,
                name=name,
                description=row["description"],
            )
            Category.objects.filter(pk=created[row["export_id"]].pk).update(
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            pending.remove(row)
    imported_memories = Memory.objects.bulk_create(
        [
            Memory(
                owner=owner,
                category=created[row["category_export_id"]],
                content=row["content"],
                priority=row["priority"],
            )
            for row in data["memories"]
        ]
    )
    for memory, row in zip(imported_memories, data["memories"], strict=True):
        Memory.objects.filter(pk=memory.pk).update(
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
    imported_archives = Archive.objects.bulk_create(
        [
            Archive(owner=owner, name=row["name"], snapshot=row["snapshot"])
            for row in data["archives"]
        ]
    )
    for archive, row in zip(imported_archives, data["archives"], strict=True):
        Archive.objects.filter(pk=archive.pk).update(
            created_at=datetime.fromisoformat(row["created_at"])
        )


@login_required
@require_http_methods(["GET", "POST"])
def import_upload(request):
    form = ImportUploadForm(request.POST or None, request.FILES or None)
    errors = []
    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["archive"]
        if uploaded.size > settings.CONTEXTLOOM_IMPORT_MAX_BYTES:
            form.add_error("archive", "The uploaded archive is too large.")
        else:
            payload = uploaded.read(settings.CONTEXTLOOM_IMPORT_MAX_BYTES + 1)
            try:
                data = parse_import(payload)
            except ImportValidationError as exc:
                errors = exc.errors
            else:
                mode = form.cleaned_data["mode"]
                summary = summarize_import(request.user, data, mode)
                ImportJob.objects.filter(
                    owner=request.user,
                    created_at__lt=timezone.now() - timezone.timedelta(hours=1),
                ).delete()
                job = ImportJob.objects.create(
                    owner=request.user, payload=payload, mode=mode, summary=summary
                )
                return redirect("knowledge:import_confirm", job_id=job.pk)
    return render(request, "knowledge/import.html", {"form": form, "errors": errors})


@login_required
@require_http_methods(["GET", "POST"])
def import_confirm(request, job_id):
    job = ImportJob.objects.filter(owner=request.user, pk=job_id).first()
    if not job or job.created_at < timezone.now() - timezone.timedelta(hours=1):
        raise Http404
    form = ImportConfirmForm(request.POST or None, mode=job.mode)
    if request.method == "POST" and form.is_valid():
        try:
            data = parse_import(bytes(job.payload))
            with transaction.atomic():
                apply_import(request.user, data, job.mode)
                job.delete()
        except ImportValidationError as exc:
            return render(
                request,
                "knowledge/import_confirm.html",
                {"form": form, "job": job, "errors": exc.errors},
                status=400,
            )
        messages.success(request, "Import completed.")
        return redirect("knowledge:home")
    return render(
        request,
        "knowledge/import_confirm.html",
        {"form": form, "job": job, "errors": []},
    )
