#!/usr/bin/env python3
import hashlib
import json
import os
import re
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
MAX_PACKAGE_SIZE = 128 * 1024 * 1024
MAX_FILES = 4096
ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(url, limit=None):
    request = urllib.request.Request(url, headers={"User-Agent": "shanten-lens-marketplace/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if limit is not None and int(response.headers.get("Content-Length", 0)) > limit:
            raise ValueError("package exceeds 128 MiB")
        data = response.read(None if limit is None else limit + 1)
    if limit is not None and len(data) > limit:
        raise ValueError("package exceeds 128 MiB")
    return data


def require(condition, message):
    if not condition:
        raise ValueError(message)


def repository_parts(url):
    parsed = urlparse(url)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    require(parsed.scheme == "https" and parsed.netloc == "github.com" and len(parts) == 2, "invalid GitHub repository URL")
    return parts


def validate_source(source):
    require(source.get("schemaVersion") == 1, "unsupported source schemaVersion")
    require(ID_RE.fullmatch(source.get("id", "")), "invalid plugin id")
    repository_parts(source.get("repository", ""))
    parsed = urlparse(source.get("updateManifestUrl", ""))
    require(parsed.scheme == "https" and parsed.netloc == "raw.githubusercontent.com", "updateManifestUrl must use GitHub Raw")
    require(source.get("status") in {"active", "deprecated", "blocked"}, "invalid plugin status")


def validate_update(source, update):
    require(update.get("schemaVersion") == 1, "unsupported update schemaVersion")
    require(update.get("id") == source["id"], "update id does not match source id")
    require(VERSION_RE.fullmatch(update.get("version", "")), "invalid plugin version")
    require(re.fullmatch(r"[0-9a-fA-F]{64}", update.get("sha256", "")), "invalid SHA-256")
    require(isinstance(update.get("size"), int) and 0 < update["size"] <= MAX_PACKAGE_SIZE, "invalid package size")
    owner, repository = repository_parts(source["repository"])
    parsed = urlparse(update.get("downloadUrl", ""))
    prefix = f"/{owner}/{repository}/releases/download/"
    require(parsed.scheme == "https" and parsed.netloc == "github.com" and parsed.path.startswith(prefix), "downloadUrl must be a Release asset from the registered repository")


def read_manifest(archive_bytes):
    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        infos = archive.infolist()
        require(len(infos) <= MAX_FILES, "package contains too many files")
        for info in infos:
            path = PurePosixPath(info.filename.replace("\\", "/"))
            require(not path.is_absolute() and ".." not in path.parts, f"unsafe ZIP path: {info.filename}")
            require((info.external_attr >> 16) & 0o170000 != 0o120000, f"symbolic link is not allowed: {info.filename}")
        require("plugin.json" in archive.namelist(), "plugin.json must be at the ZIP root")
        return json.loads(archive.read("plugin.json"))


def registry_entry(source):
    update = json.loads(fetch(source["updateManifestUrl"]))
    validate_update(source, update)
    archive = fetch(update["downloadUrl"], MAX_PACKAGE_SIZE)
    require(len(archive) == update["size"], "package size does not match update manifest")
    require(hashlib.sha256(archive).hexdigest().lower() == update["sha256"].lower(), "package SHA-256 does not match update manifest")
    manifest = read_manifest(archive)
    require(manifest.get("id") == source["id"], "plugin.json id does not match source id")
    require(manifest.get("version") == update["version"], "plugin.json version does not match update manifest")
    require(isinstance(manifest.get("name"), str) and manifest["name"].strip(), "plugin.json name is required")
    require(isinstance(manifest.get("apiVersion"), int) and manifest["apiVersion"] > 0, "plugin.json apiVersion is invalid")

    entry = {
        "id": source["id"],
        "name": manifest["name"],
        "version": manifest["version"],
        "apiVersion": manifest["apiVersion"],
        "repository": source["repository"],
        "package": {"downloadUrl": update["downloadUrl"], "sha256": update["sha256"].lower(), "size": update["size"]},
        "publishedAt": update["publishedAt"],
        "status": source["status"],
    }
    for key in ("description", "author", "homepage", "source", "issues", "license", "categories", "minimumAppVersion"):
        if key in manifest:
            entry[key] = manifest[key]
    for key in ("releaseNotes", "releaseNotesUrl"):
        if key in update:
            entry[key] = update[key]
    return entry


def main():
    marketplace = read_json(ROOT / "marketplace.json")
    output_path = ROOT / "public" / "registry.json"
    previous = read_json(output_path) if output_path.exists() else {"plugins": []}
    previous_by_id = {plugin["id"]: plugin for plugin in previous.get("plugins", [])}
    plugins = []

    for path in sorted((ROOT / "plugins").glob("*.json")):
        source = {}
        try:
            source = read_json(path)
            validate_source(source)
            plugins.append(registry_entry(source))
        except Exception as error:
            plugin_id = source.get("id")
            print(f"::warning file={path.relative_to(ROOT)}::{error}", file=sys.stderr)
            if plugin_id in previous_by_id:
                plugins.append(previous_by_id[plugin_id])

    plugins.sort(key=lambda plugin: plugin["id"])
    stable = {
        "schemaVersion": 1,
        "marketplace": {"id": marketplace["id"], "name": marketplace["name"]},
        "plugins": plugins,
    }
    previous_stable = {key: previous.get(key) for key in stable}
    if stable == previous_stable:
        return

    canonical = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    registry = {
        "schemaVersion": 1,
        "marketplace": stable["marketplace"],
        "revision": hashlib.sha256(canonical.encode()).hexdigest()[:16],
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plugins": plugins,
    }
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
