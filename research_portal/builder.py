"""Build from a small, revision-pinned source export; never run the legacy CLI."""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

from .domain import BuildOptions, PortalError, canonical, digest, reference, scrub
from .providers import isolated_env
from .storage import uid

SOURCE_FILES = ("tools/generate_mean_teacher_notebook.py", "tools/kaggle/resume.py",
                "core/config_parser.py", "utils/wandb_manager.py", "configs/kaggle/notebooks.json")


def git(checkout, *args):
    result = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, timeout=20)
    if result.returncode:
        raise PortalError("Cannot read the configured BHSD revision")
    return result.stdout


def source_inventory(settings):
    if not re.fullmatch(r"[0-9a-f]{40}", settings.revision):
        raise PortalError("BHSD revision must be a full commit SHA")
    head = git(settings.bhsd, "rev-parse", "HEAD").decode().strip()
    if head != settings.revision:
        raise PortalError("BHSD HEAD differs from configured revision")
    names = git(settings.bhsd, "ls-tree", "-r", "--name-only", settings.revision, "configs").decode().splitlines()
    paths = list(SOURCE_FILES) + [p for p in names if p.endswith((".yaml", ".yml"))]
    result = {}
    for name in paths:
        content = git(settings.bhsd, "show", f"{settings.revision}:{name}")
        path = settings.bhsd / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
            raise PortalError("Relevant BHSD source differs from committed revision: " + name)
        result[name] = content
    return result


def inventory_digest(settings):
    return digest({name: hashlib.sha256(content).hexdigest() for name, content in source_inventory(settings).items()})


def file_digests(path):
    expected = ("kernel-metadata.json", "notebook.ipynb")
    return {name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in expected}


def build(settings, store, account, options):
    options = BuildOptions(**options).validate()
    if account["provider"] != "kaggle" or not account["enabled"] or account["archived"]:
        raise PortalError("Choose an enabled Kaggle account")
    preview_id = uid()
    workspace = store.root / "work" / preview_id
    workspace.mkdir(mode=0o700)
    bundle = store.root / "previews" / preview_id
    bundle.mkdir(mode=0o700)
    if settings.mode == "fixture":
        source_hash = "fixture"
        notebook = {"nbformat": 4, "nbformat_minor": 2, "metadata": {}, "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["Synthetic demo; this is not a training notebook."]},
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": [f"TASK = {options.task!r}\n", f"TRACKING = {options.tracking!r}\n", f"RESUME_RUN = {options.resume_run!r}\n"]}]}
        spec = {"slug": "research-portal-demo", "title": "Research Portal Demo", "dataset_sources": []}
        resolved = {"experiment": {"task": options.task}, "synthetic": True}
    else:
        inventory = source_inventory(settings)
        source_hash = digest({name: hashlib.sha256(content).hexdigest() for name, content in inventory.items()})
        for name, content in inventory.items():
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        spec = json.loads(inventory["configs/kaggle/notebooks.json"])["notebooks"]["mean_teacher"]
        request = {"workspace": str(workspace), "options": options.payload(), "revision": settings.revision}
        process = subprocess.run([sys.executable, "-m", "research_portal.build_child"], input=canonical(request),
                                 text=True, capture_output=True, timeout=60, env=isolated_env(workspace),
                                 cwd=Path(__file__).resolve().parents[1])
        if process.returncode:
            raise PortalError("BHSD generator/config compatibility failed; inspect offline contract tests")
        result = json.loads(process.stdout)
        notebook, resolved = result["notebook"], result["resolved_config"]
    slug = options.slug or spec["slug"]
    title = options.title or (slug if options.slug else spec.get("title", slug))
    if len(title) < 5:
        raise PortalError("Kaggle title must contain at least five characters")
    datasets = [options.dataset] if options.dataset else spec.get("dataset_sources", [])
    datasets = [reference(d.replace("{username}", account["principal"])) for d in datasets]
    kernel = reference(account["principal"] + "/" + slug)
    metadata = {"id": kernel, "title": title, "code_file": "notebook.ipynb", "language": "python",
                "kernel_type": "notebook", "is_private": True, "enable_gpu": options.gpu,
                "enable_tpu": False, "enable_internet": True, "dataset_sources": datasets,
                "kernel_sources": [], "competition_sources": [], "model_sources": []}
    text = canonical(notebook)
    # Generated cells must never contain credential values, including any configured profile.
    serialized = text + canonical(metadata) + canonical(resolved)
    for secret in store.redaction_values():
        if secret and (secret in serialized or (len(secret) >= 12 and secret[:12] in serialized)):
            raise PortalError("Generated bundle/config contains a credential or its prefix")
    (bundle / "notebook.ipynb").write_text(text)
    (bundle / "kernel-metadata.json").write_text(canonical(metadata))
    manifest = {"schema_version": 1, "mode": settings.mode, "kernel": kernel, "metadata": metadata,
                "source_revision": settings.revision if settings.mode == "live" else "fixture",
                "source_digest": source_hash, "resolved_config": scrub(resolved), "options_digest": digest(options.payload()),
                "files": file_digests(bundle), "warnings": ["Kaggle Secrets must be attached on Kaggle; portal cannot verify them."]
                if options.tracking == "kaggle_secrets" else []}
    manifest["bundle_digest"] = digest(manifest["files"])
    store.add_preview(preview_id, account, options.payload(), manifest)
    return {"preview_id": preview_id, "manifest": manifest}


def validated_bundle(store, preview):
    bundle = store.root / "previews" / preview["id"]
    if bundle.is_symlink() or any((bundle / name).is_symlink() for name in preview["manifest"]["files"]):
        raise PortalError("Unsafe preview path")
    if file_digests(bundle) != preview["manifest"]["files"]:
        raise PortalError("Preview bundle changed; build again")
    return bundle


def download_bundle(store, preview):
    bundle = validated_bundle(store, preview)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("notebook.ipynb", "kernel-metadata.json"):
            archive.writestr(name, (bundle / name).read_bytes())
        archive.writestr("portal-manifest.json", canonical(preview["manifest"]))
    return output.getvalue()
