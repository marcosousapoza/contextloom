import csv
import io
import json
import zipfile

import pytest
from django.db import IntegrityError

from contextloom.knowledge.exceptions import ImportValidationError
from contextloom.knowledge.import_export import apply_import, build_export, parse_import
from contextloom.knowledge.models import Archive, Category, Memory
from contextloom.knowledge.services import archive_category


def zip_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def exported_bytes(user):
    stream = build_export(user)
    try:
        return stream.read()
    finally:
        stream.close()


def replace_zip_file(payload, filename, transform):
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    files[filename] = transform(files[filename])
    return zip_bytes(files)


def rewrite_categories(content, transform):
    source = io.StringIO(content.decode("utf-8"), newline="")
    reader = csv.DictReader(source)
    rows = transform(list(reader))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


@pytest.mark.django_db
def test_export_round_trip_preserves_nested_unicode_multiline_and_archive(user):
    root = Category.objects.create(owner=user, name="=Formulas", description="Grüße, world")
    child = Category.objects.create(owner=user, parent=root, name="Child, quoted")
    memory = Memory.objects.create(
        owner=user, category=child, content='第一行\n"quoted",second', priority=5
    )
    archived_root = Category.objects.create(owner=user, name="Archived")
    Memory.objects.create(owner=user, category=archived_root, content="Archive body", priority=2)
    archive_category(owner=user, category_id=archived_root.pk)

    payload = exported_bytes(user)
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        categories_csv = bundle.read("categories.csv").decode()
        assert "'=Formulas" in categories_csv
        assert set(bundle.namelist()) == {
            "categories.csv",
            "memories.csv",
            "archives.csv",
            "manifest.json",
        }
    data = parse_import(payload)
    Category.objects.filter(owner=user).delete()
    Archive.objects.filter(owner=user).delete()
    apply_import(user, data, "replace")

    imported_child = Category.objects.get(owner=user, name="Child, quoted")
    assert imported_child.parent.name == "=Formulas"
    assert imported_child.parent.description == "Grüße, world"
    imported_memory = Memory.objects.get(owner=user, content=memory.content)
    assert imported_memory.priority == 5
    restored_archive = Archive.objects.get(owner=user)
    assert restored_archive.snapshot["memories"][0]["content"] == "Archive body"


@pytest.mark.django_db
def test_merge_resolves_root_collision_without_overwrite(user):
    Category.objects.create(owner=user, name="Root", description="Existing")
    source = Category.objects.create(owner=user, name="Other")
    payload = exported_bytes(user)
    source.delete()
    data = parse_import(payload)
    apply_import(user, data, "merge")
    assert Category.objects.filter(owner=user, name="Root").count() == 1
    assert Category.objects.filter(owner=user, name="Root (2)").exists()


@pytest.mark.django_db
def test_import_rejects_path_traversal():
    payload = zip_bytes(
        {
            "manifest.json": "{}",
            "categories.csv": "",
            "memories.csv": "",
            "../archives.csv": "",
        }
    )
    with pytest.raises(ImportValidationError, match="inventory|unsafe"):
        parse_import(payload)


@pytest.mark.django_db
def test_import_rejects_unsupported_version(user):
    payload = exported_bytes(user)
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["format_version"] = 999
    files["manifest.json"] = json.dumps(manifest)
    with pytest.raises(ImportValidationError, match="version"):
        parse_import(zip_bytes(files))


@pytest.mark.django_db(transaction=True)
def test_replace_rolls_back_when_write_fails(user, monkeypatch):
    existing = Category.objects.create(owner=user, name="Keep me")
    source = Category.objects.create(owner=user, name="Import me")
    payload = exported_bytes(user)
    source.delete()
    data = parse_import(payload)

    def fail(*args, **kwargs):
        raise IntegrityError("simulated failure")

    monkeypatch.setattr(Memory.objects, "bulk_create", fail)
    with pytest.raises(IntegrityError):
        apply_import(user, data, "replace")
    assert Category.objects.filter(pk=existing.pk, name="Keep me").exists()


@pytest.mark.django_db
def test_malformed_csv_is_rejected(user):
    payload = exported_bytes(user)
    with zipfile.ZipFile(io.BytesIO(payload)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    files["categories.csv"] = (
        b'export_id,parent_export_id,name,description,created_at,updated_at\r\n"unterminated'
    )
    with pytest.raises(ImportValidationError, match="malformed"):
        parse_import(zip_bytes(files))


@pytest.mark.django_db
def test_import_rejects_cyclic_category_hierarchy(user):
    first = Category.objects.create(owner=user, name="First")
    Category.objects.create(owner=user, parent=first, name="Second")
    payload = exported_bytes(user)

    def make_cycle(rows):
        rows[0]["parent_export_id"] = rows[1]["export_id"]
        return rows

    payload = replace_zip_file(
        payload, "categories.csv", lambda content: rewrite_categories(content, make_cycle)
    )
    with pytest.raises(ImportValidationError, match="cycle"):
        parse_import(payload)


@pytest.mark.django_db
def test_import_rejects_duplicate_export_ids(user):
    Category.objects.create(owner=user, name="First")
    Category.objects.create(owner=user, name="Second")
    payload = exported_bytes(user)

    def duplicate_id(rows):
        rows[1]["export_id"] = rows[0]["export_id"]
        return rows

    payload = replace_zip_file(
        payload, "categories.csv", lambda content: rewrite_categories(content, duplicate_id)
    )
    with pytest.raises(ImportValidationError, match="duplicate export IDs"):
        parse_import(payload)


@pytest.mark.django_db
def test_import_enforces_row_field_and_expansion_limits(user, settings):
    category = Category.objects.create(owner=user, name="First", description="long value")
    Memory.objects.create(owner=user, category=category, content="body", priority=3)
    payload = exported_bytes(user)

    settings.CONTEXTLOOM_IMPORT_MAX_ROWS = 1
    with pytest.raises(ImportValidationError, match="too many rows"):
        parse_import(payload)

    settings.CONTEXTLOOM_IMPORT_MAX_ROWS = 50_000
    settings.CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH = 5
    with pytest.raises(ImportValidationError, match="too long"):
        parse_import(payload)

    settings.CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH = 1_000_000
    settings.CONTEXTLOOM_IMPORT_MAX_EXPANDED_BYTES = 1
    with pytest.raises(ImportValidationError, match="expanded archive"):
        parse_import(payload)


@pytest.mark.django_db
def test_replace_import_cannot_affect_another_user(user, other_user):
    source = Category.objects.create(owner=user, name="Imported")
    payload = exported_bytes(user)
    source.delete()
    foreign = Category.objects.create(owner=other_user, name="Other user's category")

    apply_import(user, parse_import(payload), "replace")

    assert Category.objects.filter(owner=user, name="Imported").exists()
    assert Category.objects.filter(pk=foreign.pk, owner=other_user).exists()
