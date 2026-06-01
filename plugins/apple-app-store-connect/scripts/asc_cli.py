#!/usr/bin/env python3
"""Command-line release helper for the Apple App Store Connect Codex plugin."""

from __future__ import annotations

import argparse
import base64
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from asc_api import (
    AppStoreConnectClient,
    AppStoreConnectError,
    Credentials,
    file_hash,
    json_api_body,
    print_json,
    relationship,
    upload_operations,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = PLUGIN_ROOT / "assets"
FIELD_MAP = ASSETS_DIR / "field-map.json"
SUBMISSION_TEMPLATE = ASSETS_DIR / "submission-template.json"
DEFAULT_ASC_DIR = Path.home() / ".appstoreconnect"
DEFAULT_KEY_DIR = DEFAULT_ASC_DIR / "private_keys"
DEFAULT_ENV_FILE = DEFAULT_ASC_DIR / "credentials.env"

TEXT_LIMITS = {
    "name": (2, 30),
    "subtitle": (0, 30),
    "keywords": (0, 100),
    "promotionalText": (0, 170),
    "description": (0, 4000),
    "whatsNew": (0, 4000),
}

SUBSCRIPTION_DESCRIPTION_MARKERS = {
    "section": "subscription information",
    "renewal": "automatically renew",
    "cancel": "cancel",
    "twenty_four_hours": "24 hours",
}
SUBSCRIPTION_PERIODS = {"ONE_WEEK", "ONE_MONTH", "TWO_MONTHS", "THREE_MONTHS", "SIX_MONTHS", "ONE_YEAR"}
SUBSCRIPTION_OFFER_MODES = {"PAY_AS_YOU_GO", "PAY_UP_FRONT", "FREE_TRIAL"}
SUBSCRIPTION_OFFER_DURATIONS = {
    "THREE_DAYS",
    "ONE_WEEK",
    "TWO_WEEKS",
    "ONE_MONTH",
    "TWO_MONTHS",
    "THREE_MONTHS",
    "SIX_MONTHS",
    "ONE_YEAR",
}
BLOCKED_REVIEW_CONTEXTS = {
    "launch",
    "first_launch",
    "onboarding",
    "paywall",
    "purchase",
    "purchase_flow",
    "subscription_cancel",
    "error",
    "crash",
    "offline",
    "permission_prompt",
    "notification_permission",
    "user_tapped_rate_us",
}

SCREENSHOT_MIN = 1
SCREENSHOT_MAX = 10
AUTH_KEY_RE = re.compile(r"^AuthKey_([A-Za-z0-9]+)\.p8$")
VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,2}$")
FULL_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
SKIPPED_PROJECT_DIRS = {
    ".git",
    ".build",
    "build",
    "DerivedData",
    "Pods",
    "Carthage",
    "node_modules",
    "vendor",
}


def load_json(path: str | Path) -> Any:
    with Path(path).expanduser().open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: str | Path, value: Any) -> None:
    with Path(path).expanduser().open("w", encoding="utf-8") as file:
        json.dump(value, file, indent=2)
        file.write("\n")


def shell_quote(value: str | Path) -> str:
    text = str(value)
    return "'" + text.replace("'", "'\"'\"'") + "'"


def derive_key_id_from_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    match = AUTH_KEY_RE.match(Path(path).name)
    return match.group(1) if match else None


def default_key_path(key_id: str, key_dir: str | Path | None = None) -> Path:
    directory = Path(key_dir).expanduser() if key_dir else DEFAULT_KEY_DIR
    return directory / f"AuthKey_{key_id}.p8"


def path_mode(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)


def credential_env_status() -> dict[str, Any]:
    key_path_text = os.environ.get("ASC_KEY_PATH", "").strip()
    key_path = Path(key_path_text).expanduser() if key_path_text else None
    key_type = os.environ.get("ASC_KEY_TYPE", "team").strip().lower()
    key_id_present = bool(os.environ.get("ASC_KEY_ID"))
    issuer_present = bool(os.environ.get("ASC_ISSUER_ID"))
    key_path_present = bool(key_path_text)
    ready = (
        key_id_present
        and key_path_present
        and bool(key_path and key_path.exists())
        and key_type in {"team", "individual"}
        and (key_type == "individual" or issuer_present)
    )
    return {
        "ASC_KEY_ID": key_id_present,
        "ASC_ISSUER_ID": issuer_present,
        "ASC_KEY_PATH": key_path_present,
        "ASC_KEY_TYPE": key_type,
        "keyPathExists": bool(key_path and key_path.exists()),
        "keyPathMode": path_mode(key_path),
        "ready": ready,
    }


def credential_export_lines(values: dict[str, str]) -> list[str]:
    ordered = ["ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_KEY_PATH", "ASC_KEY_TYPE"]
    return [f"export {key}={shell_quote(values[key])}" for key in ordered if values.get(key)]


def write_env_file(path: str | Path, values: dict[str, str]) -> Path:
    target = Path(path).expanduser()
    parent_existed = target.parent.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed or target.parent == DEFAULT_ASC_DIR:
        os.chmod(target.parent, 0o700)
    lines = [
        "# App Store Connect API credentials for local Codex/Xcode release workflows.",
        "# Do not commit this file.",
        *credential_export_lines(values),
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def credential_setup(args: argparse.Namespace) -> dict[str, Any]:
    key_type = (args.key_type or os.environ.get("ASC_KEY_TYPE", "team")).strip().lower()
    if key_type not in {"team", "individual"}:
        raise AppStoreConnectError("ASC_KEY_TYPE must be team or individual")

    import_key = Path(args.import_key).expanduser() if args.import_key else None
    explicit_key_path = Path(args.key_path).expanduser() if args.key_path else None
    key_id = (
        args.key_id
        or os.environ.get("ASC_KEY_ID", "").strip()
        or derive_key_id_from_path(import_key)
        or derive_key_id_from_path(explicit_key_path)
    )
    issuer_id = args.issuer_id or os.environ.get("ASC_ISSUER_ID", "").strip() or None
    key_path = explicit_key_path or (
        Path(os.environ["ASC_KEY_PATH"]).expanduser() if os.environ.get("ASC_KEY_PATH") else None
    )
    key_dir = Path(args.key_dir).expanduser() if args.key_dir else DEFAULT_KEY_DIR
    actions: list[dict[str, Any]] = []

    if import_key:
        if not import_key.exists():
            raise AppStoreConnectError(f"Import key does not exist: {import_key}")
        if not key_id:
            raise AppStoreConnectError("Pass --key-id or use an AuthKey_<KEY_ID>.p8 filename.")
        key_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(key_dir, 0o700)
        destination = default_key_path(key_id, key_dir)
        if import_key.resolve() != destination.resolve():
            shutil.copy2(import_key, destination)
            actions.append({"action": "copiedKey", "from": str(import_key), "to": str(destination)})
        else:
            actions.append({"action": "keyAlreadyInPlace", "path": str(destination)})
        os.chmod(destination, 0o600)
        key_path = destination
    elif not key_path and key_id:
        key_path = default_key_path(key_id, key_dir)

    values: dict[str, str] = {}
    if key_id:
        values["ASC_KEY_ID"] = key_id
    if issuer_id and key_type == "team":
        values["ASC_ISSUER_ID"] = issuer_id
    if key_path:
        values["ASC_KEY_PATH"] = str(key_path)
    values["ASC_KEY_TYPE"] = key_type

    missing = []
    if not key_id:
        missing.append("ASC_KEY_ID")
    if not key_path:
        missing.append("ASC_KEY_PATH")
    elif not key_path.exists():
        missing.append("ASC_KEY_PATH_FILE")
    if key_type == "team" and not issuer_id:
        missing.append("ASC_ISSUER_ID")

    written_env = None
    if args.write_env_file:
        if missing:
            raise AppStoreConnectError("Cannot write credential env file; missing " + ", ".join(missing))
        written_env = write_env_file(args.write_env_file, values)
        actions.append({"action": "wroteEnvFile", "path": str(written_env), "mode": path_mode(written_env)})

    verify: dict[str, Any] | None = None
    if args.verify:
        if missing:
            verify = {"ok": False, "error": "Missing " + ", ".join(missing)}
        elif not key_path or not key_path.exists():
            verify = {"ok": False, "error": f"ASC_KEY_PATH does not exist: {key_path}"}
        else:
            try:
                credentials = Credentials(key_id=key_id, issuer_id=issuer_id, key_path=key_path, key_type=key_type)
                client = AppStoreConnectClient(credentials=credentials)
                response = client.get("/v1/apps", {"limit": "1"})
                verify = {"ok": True, "visibleApps": len(response.get("data", []))}
            except Exception as exc:
                verify = {"ok": False, "error": str(exc)}

    source_command = f"source {shell_quote(written_env)}" if written_env else None
    return {
        "ok": not missing and (verify is None or bool(verify.get("ok"))),
        "missing": missing,
        "actions": actions,
        "credentials": {
            "ASC_KEY_ID": bool(key_id),
            "ASC_ISSUER_ID": bool(issuer_id),
            "ASC_KEY_PATH": bool(key_path),
            "ASC_KEY_TYPE": key_type,
            "keyPath": str(key_path) if key_path else None,
            "keyPathExists": bool(key_path and key_path.exists()),
            "keyPathMode": path_mode(key_path),
            "envFile": str(written_env) if written_env else None,
        },
        "shell": {"exports": credential_export_lines(values), "sourceCommand": source_command},
        "verify": verify,
        "nextSteps": [
            "Create an App Store Connect API key in Users and Access > Integrations.",
            "Download the AuthKey_<KEY_ID>.p8 file once and keep it outside git.",
            "Run credential-setup with --import-key and --write-env-file, then source the env file.",
            "Run doctor again to confirm credentials are ready.",
        ],
    }


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_version(value: str | int | None, default: tuple[int, int, int] = (0, 0, 0)) -> tuple[int, int, int]:
    if value is None:
        return default
    parts = [int(part) for part in str(value).strip().split(".") if part != ""]
    if not parts or len(parts) > 3:
        return default
    return tuple((parts + [0, 0, 0])[:3])


def format_version(parts: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in parts)


def increment_version(value: str | None, level: str) -> str:
    major, minor, patch = parse_version(value, default=(1, 0, 0))
    if level == "same":
        return format_version((major, minor, patch))
    if level == "major":
        return format_version((major + 1, 0, 0))
    if level == "minor":
        return format_version((major, minor + 1, 0))
    return format_version((major, minor, patch + 1))


def increment_build(value: str | int | None, amount: int = 1) -> str:
    amount = max(1, amount)
    parts = [int(part) for part in str(value or "0").strip().split(".") if part.isdigit()]
    if not parts:
        parts = [0]
    parts[-1] += amount
    return ".".join(str(part) for part in parts[:3])


def ensure_version_format(value: str, field: str) -> None:
    if not VERSION_RE.match(value):
        raise AppStoreConnectError(f"{field} must contain one to three period-separated integers.")


def ensure_app_store_version_format(value: str) -> None:
    if not FULL_VERSION_RE.match(value):
        raise AppStoreConnectError(
            "App Store version must use three period-separated integers, for example 1.2.3."
        )


def add_length_issue(
    issues: list[dict[str, str]], field: str, value: str | None, minimum: int, maximum: int
) -> None:
    if value is None:
        return
    count = len(value)
    if count < minimum:
        issues.append(
            {
                "severity": "error",
                "field": field,
                "message": f"{field} is {count} characters; minimum is {minimum}.",
            }
        )
    if count > maximum:
        issues.append(
            {
                "severity": "error",
                "field": field,
                "message": f"{field} is {count} characters; maximum is {maximum}.",
            }
        )


def validate_keywords(value: str | None, issues: list[dict[str, str]]) -> None:
    if not value:
        return
    add_length_issue(issues, "keywords", value, *TEXT_LIMITS["keywords"])
    if ", " in value:
        issues.append(
            {
                "severity": "warning",
                "field": "keywords",
                "message": "Apple recommends comma-separated keywords without spaces after commas.",
            }
        )
    terms = [term.strip().lower() for term in value.split(",") if term.strip()]
    duplicates = sorted({term for term in terms if terms.count(term) > 1})
    if duplicates:
        issues.append(
            {
                "severity": "warning",
                "field": "keywords",
                "message": "Duplicate keyword terms: " + ", ".join(duplicates),
            }
        )
    blocked = {"app", "apps"}
    if any(term in blocked for term in terms):
        issues.append(
            {
                "severity": "warning",
                "field": "keywords",
                "message": "Avoid generic category words such as app or apps.",
            }
        )


def validate_subscription_description(
    description: str,
    prefix: str,
    issues: list[dict[str, str]],
) -> None:
    if not description:
        issues.append(
            {
                "severity": "error",
                "field": prefix + ".description",
                "message": "Subscription apps must include a Terms of Use link, Privacy Policy link, and subscription information in the App Store description.",
            }
        )
        return

    normalized = description.lower()
    lines = normalized.splitlines()
    has_privacy_url = any(("http://" in line or "https://" in line) and "privacy" in line for line in lines)
    has_terms_url = any(
        ("http://" in line or "https://" in line) and ("terms" in line or "eula" in line)
        for line in lines
    )
    checks = [
        ("SUBSCRIPTION INFORMATION section", "section", "warning"),
        ("auto-renewal disclosure", "renewal", "warning"),
        ("cancellation instructions", "cancel", "warning"),
        ("24-hour renewal/cancellation disclosure", "twenty_four_hours", "warning"),
    ]
    for label, marker, severity in checks:
        if SUBSCRIPTION_DESCRIPTION_MARKERS[marker] not in normalized:
            issues.append(
                {
                    "severity": severity,
                    "field": prefix + ".description",
                    "message": f"Subscription apps should include a functional {label} in the App Store description.",
                }
            )

    if not has_privacy_url:
        issues.append(
            {
                "severity": "warning",
                "field": prefix + ".description",
                "message": "Subscription apps should include a labeled Privacy Policy URL in the App Store description.",
            }
        )
    if not has_terms_url:
        issues.append(
            {
                "severity": "error",
                "field": prefix + ".description",
                "message": "Subscription apps must include a labeled Terms of Use or EULA URL in the App Store description.",
            }
        )


def git_output(project_dir: Path, args: list[str]) -> str | None:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(project_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def git_iteration_count(project_dir: Path) -> tuple[int | None, str | None]:
    inside = git_output(project_dir, ["rev-parse", "--is-inside-work-tree"])
    if inside != "true":
        return None, None
    tag = git_output(project_dir, ["describe", "--tags", "--abbrev=0"])
    if tag:
        count_text = git_output(project_dir, ["rev-list", "--count", f"{tag}..HEAD"])
        if count_text and count_text.isdigit():
            count = int(count_text)
            return max(1, count), f"commits since tag {tag}"
    count_text = git_output(project_dir, ["rev-list", "--count", "HEAD"])
    if count_text and count_text.isdigit():
        return max(1, int(count_text)), "total git commits"
    return None, None


def git_recent_messages(project_dir: Path) -> list[str]:
    output = git_output(project_dir, ["log", "--format=%s", "-n", "50"])
    if not output:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def infer_release_level(project_dir: Path, requested: str, current_version: str | None) -> tuple[str, str]:
    if requested != "auto":
        return requested, f"release level explicitly set to {requested}"
    if not current_version:
        return "same", "no current version found; defaulting initial version to 1.0.0"
    messages = git_recent_messages(project_dir)
    joined = "\n".join(messages).lower()
    if "breaking change" in joined or re.search(r"^[a-z]+(?:\(.+\))?!:", joined, flags=re.MULTILINE):
        return "major", "recent git history contains a breaking-change marker"
    if re.search(r"^feat(?:\(.+\))?:", joined, flags=re.MULTILINE):
        return "minor", "recent git history contains feature commits"
    return "patch", "defaulting to a patch release for a release build"


def read_plist_values(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as file:
            value = plistlib.load(file)
        if isinstance(value, dict):
            return value
    except Exception:
        return None
    return None


def is_skipped_project_path(path: Path) -> bool:
    return any(part in SKIPPED_PROJECT_DIRS for part in path.parts)


def discover_version_sources(project_dir: Path) -> list[dict[str, Any]]:
    project_dir = project_dir.expanduser().resolve()
    sources: list[dict[str, Any]] = []
    for pbxproj in sorted(project_dir.rglob("project.pbxproj")):
        if is_skipped_project_path(pbxproj):
            continue
        text = pbxproj.read_text(encoding="utf-8", errors="replace")
        marketing = re.findall(r"\bMARKETING_VERSION\s*=\s*([^;]+);", text)
        current = re.findall(r"\bCURRENT_PROJECT_VERSION\s*=\s*([^;]+);", text)
        if marketing or current:
            sources.append(
                {
                    "type": "xcodeBuildSettings",
                    "path": str(pbxproj),
                    "version": marketing[-1].strip().strip('"') if marketing else None,
                    "build": current[-1].strip().strip('"') if current else None,
                    "versionKey": "MARKETING_VERSION" if marketing else None,
                    "buildKey": "CURRENT_PROJECT_VERSION" if current else None,
                }
            )
    for plist in sorted(project_dir.rglob("Info.plist")):
        if is_skipped_project_path(plist):
            continue
        value = read_plist_values(plist)
        if not value:
            continue
        version = value.get("CFBundleShortVersionString")
        build = value.get("CFBundleVersion")
        if version or build:
            sources.append(
                {
                    "type": "infoPlist",
                    "path": str(plist),
                    "version": version,
                    "build": build,
                    "versionKey": "CFBundleShortVersionString" if version else None,
                    "buildKey": "CFBundleVersion" if build else None,
                }
            )
    return sources


def first_literal(values: list[Any]) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip().strip('"')
        if text and "$(" not in text:
            return text
    return None


def resolve_current_version(sources: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    version = first_literal([source.get("version") for source in sources])
    build = first_literal([source.get("build") for source in sources])
    return version, build


def plan_versioning(
    project_dir: str | Path,
    release_level: str = "auto",
    iteration_count: int | None = None,
    current_version: str | None = None,
    current_build: str | None = None,
    use_git: bool = True,
) -> dict[str, Any]:
    project_path = Path(project_dir).expanduser().resolve()
    sources = discover_version_sources(project_path)
    detected_version, detected_build = resolve_current_version(sources)
    base_version = current_version or detected_version
    base_build = current_build or detected_build

    git_count = None
    git_basis = None
    if use_git and iteration_count is None:
        git_count, git_basis = git_iteration_count(project_path)
    increment = iteration_count or git_count or 1
    level, level_reason = infer_release_level(project_path, release_level, base_version)
    if not base_version:
        next_version = "1.0.0"
    else:
        next_version = increment_version(base_version, level)
    next_build = increment_build(base_build, increment)
    ensure_app_store_version_format(next_version)
    ensure_version_format(next_build, "Build number")
    return {
        "projectDir": str(project_path),
        "detected": {
            "versionString": detected_version,
            "buildNumber": detected_build,
            "sources": sources,
        },
        "inputs": {
            "currentVersion": current_version,
            "currentBuild": current_build,
            "releaseLevel": release_level,
            "iterationCount": iteration_count,
            "useGit": use_git,
        },
        "recommendation": {
            "versionString": next_version,
            "buildNumber": next_build,
            "releaseLevel": level,
            "buildIncrement": increment,
            "rationale": [
                level_reason,
                f"build number increments by {increment}"
                + (f" from {git_basis}" if git_basis and iteration_count is None else ""),
            ],
        },
        "appleRules": [
            "CFBundleShortVersionString is the user-visible App Store version and should match App Store Connect.",
            "CFBundleShortVersionString must be three period-separated integers.",
            "CFBundleVersion identifies the build iteration and must be one to three period-separated integers.",
            "Every uploaded build for an app version needs a unique build string.",
        ],
    }


def replace_build_setting(text: str, key: str, value: str) -> tuple[str, int]:
    pattern = re.compile(rf"(\b{re.escape(key)}\s*=\s*)([^;]+)(;)")
    updated, count = pattern.subn(rf"\g<1>{value}\g<3>", text)
    return updated, count


def update_pbxproj_versions(project_dir: Path, version: str, build: str) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for pbxproj in sorted(project_dir.rglob("project.pbxproj")):
        if is_skipped_project_path(pbxproj):
            continue
        text = pbxproj.read_text(encoding="utf-8", errors="replace")
        updated, version_count = replace_build_setting(text, "MARKETING_VERSION", version)
        updated, build_count = replace_build_setting(updated, "CURRENT_PROJECT_VERSION", build)
        if updated != text:
            pbxproj.write_text(updated, encoding="utf-8")
            changed.append(
                {
                    "path": str(pbxproj),
                    "updated": {
                        "MARKETING_VERSION": version_count,
                        "CURRENT_PROJECT_VERSION": build_count,
                    },
                }
            )
    return changed


def update_info_plist_versions(
    project_dir: Path, version: str, build: str, force_variable_plists: bool = False
) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for plist in sorted(project_dir.rglob("Info.plist")):
        if is_skipped_project_path(plist):
            continue
        value = read_plist_values(plist)
        if not value:
            continue
        touched: dict[str, str] = {}
        existing_version = str(value.get("CFBundleShortVersionString", ""))
        existing_build = str(value.get("CFBundleVersion", ""))
        if existing_version and (force_variable_plists or "$(" not in existing_version):
            value["CFBundleShortVersionString"] = version
            touched["CFBundleShortVersionString"] = version
        if existing_build and (force_variable_plists or "$(" not in existing_build):
            value["CFBundleVersion"] = build
            touched["CFBundleVersion"] = build
        if touched:
            with plist.open("wb") as file:
                plistlib.dump(value, file, fmt=plistlib.FMT_XML)
            changed.append({"path": str(plist), "updated": touched})
    return changed


def apply_versioning(args: argparse.Namespace) -> dict[str, Any]:
    plan = plan_versioning(
        args.project_dir,
        release_level=args.release_level,
        iteration_count=args.iteration_count,
        current_version=args.current_version,
        current_build=args.current_build,
        use_git=not args.no_git,
    )
    version = plan["recommendation"]["versionString"]
    build = plan["recommendation"]["buildNumber"]
    if not args.yes:
        return {"dryRun": True, **plan}

    project_dir = Path(args.project_dir).expanduser().resolve()
    results: dict[str, Any] = {
        "dryRun": False,
        "versionString": version,
        "buildNumber": build,
        "updatedProjectFiles": update_pbxproj_versions(project_dir, version, build),
        "updatedInfoPlists": update_info_plist_versions(project_dir, version, build, args.force_plist),
    }
    if args.config:
        config = load_json(args.config)
        config.setdefault("version", {})
        config["version"]["versionString"] = version
        config.setdefault("build", {})
        config["build"]["buildNumber"] = build
        write_json(args.config, config)
        results["updatedConfig"] = str(Path(args.config).expanduser())
    return results


def app_store_not_found(exc: Exception) -> bool:
    return " failed with 404:" in str(exc)


def app_id_from_args(args: argparse.Namespace) -> str:
    if getattr(args, "app_id", None):
        return args.app_id
    if getattr(args, "config", None):
        config = load_json(args.config)
        app_id = (config.get("app") or {}).get("id")
        if app_id:
            return app_id
    raise AppStoreConnectError("Provide --app-id or a --config containing app.id.")


def build_free_app_price_schedule_body(app_id: str, base_territory: str, app_price_point_id: str) -> dict[str, Any]:
    return {
        "data": {
            "type": "appPriceSchedules",
            "relationships": {
                "app": relationship("apps", app_id),
                "baseTerritory": relationship("territories", base_territory),
                "manualPrices": {"data": [{"type": "appPrices", "id": "${free-price-0}"}]},
            },
        },
        "included": [
            {
                "type": "appPrices",
                "id": "${free-price-0}",
                "relationships": {"appPricePoint": relationship("appPricePoints", app_price_point_id)},
            }
        ],
    }


def build_all_territory_availability_body(app_id: str, territory_ids: list[str]) -> dict[str, Any]:
    return {
        "data": {
            "type": "appAvailabilities",
            "attributes": {"availableInNewTerritories": True},
            "relationships": {"app": relationship("apps", app_id)},
        },
        "included": [
            {
                "type": "territoryAvailabilities",
                "id": f"${{availability-{territory_id}}}",
                "attributes": {"available": True},
                "relationships": {"territory": relationship("territories", territory_id)},
            }
            for territory_id in territory_ids
        ],
    }


def find_free_price_point(client: AppStoreConnectClient, app_id: str, base_territory: str) -> dict[str, Any]:
    response = client.get(
        f"/v1/apps/{app_id}/appPricePoints",
        {
            "filter[territory]": base_territory,
            "fields[appPricePoints]": "customerPrice,proceeds,territory",
            "include": "territory",
            "limit": "200",
        },
    )
    for item in response.get("data", []):
        price = str(item.get("attributes", {}).get("customerPrice", "")).strip()
        if price in {"0", "0.0", "0.00"}:
            return item
    raise AppStoreConnectError(f"Could not find a free app price point for territory {base_territory}.")


def list_territory_ids(client: AppStoreConnectClient) -> list[str]:
    response = client.get("/v1/territories", {"limit": "200"})
    territory_ids = [item["id"] for item in response.get("data", [])]
    if not territory_ids:
        raise AppStoreConnectError("No App Store territories were returned by App Store Connect.")
    return territory_ids


def set_all_territories_available(
    client: AppStoreConnectClient, app_id: str, territory_ids: list[str]
) -> dict[str, Any]:
    try:
        availability = client.get(f"/v1/apps/{app_id}/appAvailabilityV2")
    except AppStoreConnectError as exc:
        if not app_store_not_found(exc):
            raise
        body = build_all_territory_availability_body(app_id, territory_ids)
        created = client.post("/v2/appAvailabilities", body)
        return {
            "mode": "created",
            "availabilityId": created.get("data", {}).get("id"),
            "availableInNewTerritories": created.get("data", {})
            .get("attributes", {})
            .get("availableInNewTerritories"),
            "territoryCount": len(territory_ids),
            "patchedTerritoryCount": len(territory_ids),
        }

    availability_id = availability.get("data", {}).get("id") or app_id
    try:
        client.patch(
            f"/v2/appAvailabilities/{availability_id}",
            json_api_body("appAvailabilities", {"availableInNewTerritories": True}, resource_id=availability_id),
        )
        available_in_new_territories = True
    except AppStoreConnectError as exc:
        if "appAvailabilities' does not allow 'UPDATE'" not in str(exc):
            raise
        available_in_new_territories = availability.get("data", {}).get("attributes", {}).get(
            "availableInNewTerritories"
        )
    current = client.get(
        f"/v2/appAvailabilities/{availability_id}/territoryAvailabilities",
        {"limit": "200"},
    )
    patched = []
    for item in current.get("data", []):
        if item.get("attributes", {}).get("available") is True:
            continue
        client.patch(
            f"/v2/territoryAvailabilities/{item['id']}",
            json_api_body("territoryAvailabilities", {"available": True}, resource_id=item["id"]),
        )
        patched.append(item["id"])
    return {
        "mode": "updated",
        "availabilityId": availability_id,
        "availableInNewTerritories": available_in_new_territories,
        "territoryCount": len(current.get("data", [])),
        "patchedTerritoryCount": len(patched),
    }


def configure_free_download(args: argparse.Namespace, client: AppStoreConnectClient | None) -> dict[str, Any]:
    app_id = app_id_from_args(args)
    base_territory = args.base_territory
    if not args.yes:
        return {
            "dryRun": True,
            "appId": app_id,
            "baseTerritory": base_territory,
            "target": {
                "customerPrice": "0.00",
                "availability": "all App Store territories",
                "availableInNewTerritories": True,
            },
            "actions": [
                "Find the free app price point for the base territory.",
                "Create or replace the app price schedule with that free price point.",
                "Create or update app availability so every territory is marked available.",
                "Enable availability automatically for territories Apple adds later.",
            ],
        }
    if client is None:
        raise AppStoreConnectError("An App Store Connect client is required when configuring price and availability.")

    free_price_point = find_free_price_point(client, app_id, base_territory)
    price_schedule = client.post(
        "/v1/appPriceSchedules",
        build_free_app_price_schedule_body(app_id, base_territory, free_price_point["id"]),
    )
    territory_ids = list_territory_ids(client)
    availability = set_all_territories_available(client, app_id, territory_ids)
    verification = client.get(
        f"/v2/appAvailabilities/{app_id}/territoryAvailabilities",
        {"limit": "200"},
    )
    unavailable = [
        item["id"]
        for item in verification.get("data", [])
        if item.get("attributes", {}).get("available") is not True
    ]
    return {
        "dryRun": False,
        "appId": app_id,
        "priceScheduleId": price_schedule.get("data", {}).get("id"),
        "freePricePointId": free_price_point["id"],
        "baseTerritory": base_territory,
        "availability": availability,
        "verification": {
            "territoryCount": len(verification.get("data", [])),
            "availableCount": len(verification.get("data", [])) - len(unavailable),
            "unavailableCount": len(unavailable),
        },
    }


def subscription_pricing_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    pricing = config.get("subscriptionPricing") or {}
    entries: list[dict[str, Any]] = []
    for item in as_list(pricing.get("products")) + as_list(pricing.get("prices")):
        if item:
            entries.append(item)
    for sub in as_list(config.get("subscriptions")):
        for item in as_list(sub.get("prices")):
            merged = {**item}
            merged.setdefault("subscriptionId", sub.get("id"))
            merged.setdefault("productId", sub.get("productId"))
            merged.setdefault("period", sub.get("period") or sub.get("subscriptionPeriod"))
            if merged:
                entries.append(merged)
    return entries


def subscription_intro_offer_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    pricing = config.get("subscriptionPricing") or {}
    entries = [item for item in as_list(pricing.get("introductoryOffers")) if item]
    for sub in as_list(config.get("subscriptions")):
        for item in as_list(sub.get("introductoryOffers")):
            merged = {**item}
            merged.setdefault("subscriptionId", sub.get("id"))
            merged.setdefault("productId", sub.get("productId"))
            entries.append(merged)
    return entries


def subscription_id_by_product(config: dict[str, Any]) -> dict[str, str]:
    result = {}
    for sub in as_list(config.get("subscriptions")):
        if sub.get("productId") and sub.get("id"):
            result[sub["productId"]] = sub["id"]
    return result


def resolve_subscription_id(item: dict[str, Any], product_map: dict[str, str]) -> str | None:
    return item.get("subscriptionId") or item.get("id") or product_map.get(str(item.get("productId")))


def build_subscription_price_body(
    subscription_id: str,
    price_point_id: str,
    territory: str | None = None,
    start_date: str | None = None,
    preserve_current_price: bool | None = None,
) -> dict[str, Any]:
    relationships = {
        "subscription": relationship("subscriptions", subscription_id),
        "subscriptionPricePoint": relationship("subscriptionPricePoints", price_point_id),
    }
    if territory:
        relationships["territory"] = relationship("territories", territory)
    return json_api_body(
        "subscriptionPrices",
        {"startDate": start_date, "preserveCurrentPrice": preserve_current_price},
        relationships,
    )


def build_subscription_intro_offer_body(
    subscription_id: str,
    offer: dict[str, Any],
) -> dict[str, Any]:
    attrs = {
        "startDate": offer.get("startDate"),
        "endDate": offer.get("endDate"),
        "duration": offer.get("duration", "ONE_WEEK"),
        "offerMode": offer.get("offerMode", "FREE_TRIAL"),
        "numberOfPeriods": int(offer.get("numberOfPeriods", 1)),
    }
    relationships = {"subscription": relationship("subscriptions", subscription_id)}
    territory = offer.get("territory") or offer.get("territoryId")
    price_point_id = offer.get("pricePointId") or offer.get("subscriptionPricePointId")
    if territory:
        relationships["territory"] = relationship("territories", territory)
    if price_point_id:
        relationships["subscriptionPricePoint"] = relationship("subscriptionPricePoints", price_point_id)
    return json_api_body("subscriptionIntroductoryOffers", attrs, relationships)


def validate_subscription_pricing_strategy(
    config: dict[str, Any], issues: list[dict[str, str]]
) -> None:
    subscriptions = as_list(config.get("subscriptions"))
    pricing = config.get("subscriptionPricing") or {}
    if not subscriptions:
        return
    if not pricing:
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing",
                "message": "Subscription apps should include a subscriptionPricing plan with periods, price point IDs, trial/offer strategy, and territory assumptions.",
            }
        )
        return

    download_price = str((config.get("pricingAvailability") or {}).get("downloadPrice", "")).strip()
    if pricing.get("appDownloadModel", "freeWithSubscription") == "freeWithSubscription" and download_price not in {
        "0",
        "0.0",
        "0.00",
    }:
        issues.append(
            {
                "severity": "warning",
                "field": "pricingAvailability.downloadPrice",
                "message": "For a free-download app with paid subscriptions, plan the app download price as $0 separately from subscription prices.",
            }
        )
    if pricing.get("useSingleSubscriptionGroup") is not True:
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing.useSingleSubscriptionGroup",
                "message": "Most apps should use one subscription group so users cannot accidentally buy multiple active subscriptions.",
            }
        )

    entries = subscription_pricing_entries(config)
    if not entries:
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing.products",
                "message": "Add subscription price entries for the base territory before applying subscription pricing.",
            }
        )
    periods = {str(entry.get("period") or entry.get("subscriptionPeriod") or "").upper() for entry in entries}
    if periods and not periods.intersection(SUBSCRIPTION_PERIODS):
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing.products.period",
                "message": "Use App Store subscription period values such as ONE_MONTH or ONE_YEAR.",
            }
        )
    if entries and "ONE_YEAR" not in periods:
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing.products",
                "message": "Consider an annual option with a clear best-value label for higher-intent subscribers.",
            }
        )
    if entries and not any(entry.get("pricePointId") or entry.get("subscriptionPricePointId") for entry in entries):
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing.products.pricePointId",
                "message": "Applying subscription prices requires App Store Connect subscription price point IDs.",
            }
        )
    for index, entry in enumerate(entries):
        field = f"subscriptionPricing.products[{index}]"
        period = str(entry.get("period") or entry.get("subscriptionPeriod") or "").upper()
        if period and period not in SUBSCRIPTION_PERIODS:
            issues.append(
                {
                    "severity": "error",
                    "field": field + ".period",
                    "message": "Subscription period must be one of Apple's supported period constants.",
                }
            )
        if entry.get("changeType") == "increase" and entry.get("preserveCurrentPrice") is not True:
            issues.append(
                {
                    "severity": "warning",
                    "field": field + ".preserveCurrentPrice",
                    "message": "For price increases, decide whether to preserve existing subscriber prices and note that some increases may require subscriber consent.",
                }
            )

    offers = subscription_intro_offer_entries(config)
    if pricing.get("introOfferRecommended", True) and not offers:
        issues.append(
            {
                "severity": "warning",
                "field": "subscriptionPricing.introductoryOffers",
                "message": "Consider a first-time subscriber introductory offer, usually a short free trial after users see onboarding value.",
            }
        )
    for index, offer in enumerate(offers):
        field = f"subscriptionPricing.introductoryOffers[{index}]"
        if str(offer.get("offerMode", "FREE_TRIAL")).upper() not in SUBSCRIPTION_OFFER_MODES:
            issues.append(
                {"severity": "error", "field": field + ".offerMode", "message": "Unsupported subscription offer mode."}
            )
        if str(offer.get("duration", "ONE_WEEK")).upper() not in SUBSCRIPTION_OFFER_DURATIONS:
            issues.append(
                {"severity": "error", "field": field + ".duration", "message": "Unsupported subscription offer duration."}
            )


def validate_onboarding_strategy(config: dict[str, Any], issues: list[dict[str, str]]) -> None:
    subscriptions = as_list(config.get("subscriptions"))
    if not subscriptions:
        return
    onboarding = config.get("onboarding") or {}
    if not onboarding:
        issues.append(
            {
                "severity": "warning",
                "field": "onboarding",
                "message": "Subscription apps should define value-first onboarding before the paywall is shown.",
            }
        )
        return
    if onboarding.get("paywallTiming") in {"launch", "firstLaunch", "beforeValue", "before_onboarding"}:
        issues.append(
            {
                "severity": "warning",
                "field": "onboarding.paywallTiming",
                "message": "Show the paywall after users configure preferences or see useful content, not immediately at launch.",
            }
        )
    if onboarding.get("collectsPreferences") is not True:
        issues.append(
            {
                "severity": "warning",
                "field": "onboarding.collectsPreferences",
                "message": "Ask for lightweight preferences during onboarding so the first app session feels personalized.",
            }
        )
    if onboarding.get("restorePurchasesVisible") is not True:
        issues.append(
            {
                "severity": "warning",
                "field": "onboarding.restorePurchasesVisible",
                "message": "Make Restore Purchases visible wherever the paywall appears.",
            }
        )
    if onboarding.get("termsAndPrivacyVisibleOnPaywall") is not True:
        issues.append(
            {
                "severity": "warning",
                "field": "onboarding.termsAndPrivacyVisibleOnPaywall",
                "message": "Paywalls should expose Terms of Use and Privacy Policy links alongside subscription context.",
            }
        )


def normalize_context(value: Any) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_")


def validate_review_prompt_policy(config: dict[str, Any], issues: list[dict[str, str]]) -> None:
    policy = config.get("reviewPromptPolicy") or {}
    if not policy:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy",
                "message": "Add a StoreKit review prompt policy so requestReview is triggered only after positive, non-interruptive moments.",
            }
        )
        return
    if policy.get("usesStoreKitRequestReview") is not True:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy.usesStoreKitRequestReview",
                "message": "Use StoreKit's system review prompt for in-app rating requests; use an App Store write-review URL only for a user-initiated settings/help action.",
            }
        )
    if int(policy.get("minimumSessions", 0) or 0) < 2:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy.minimumSessions",
                "message": "Delay review prompts until at least a second or third session.",
            }
        )
    if int(policy.get("minimumDaysSinceInstall", 0) or 0) < 2:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy.minimumDaysSinceInstall",
                "message": "Avoid review prompts in the first day; wait until the user has experienced value.",
            }
        )
    if int(policy.get("localCooldownDays", 0) or 0) < 90:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy.localCooldownDays",
                "message": "Use a long local cooldown; Apple also limits system prompts to three displays in 365 days.",
            }
        )
    triggers = as_list(policy.get("positiveMomentTriggers"))
    if not triggers:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy.positiveMomentTriggers",
                "message": "Define positive completion triggers such as following a team, tracking a match, or successfully receiving a useful reminder.",
            }
        )
    for index, trigger in enumerate(triggers):
        field = f"reviewPromptPolicy.positiveMomentTriggers[{index}]"
        context = normalize_context(trigger.get("context") or trigger.get("event"))
        if context in BLOCKED_REVIEW_CONTEXTS:
            issues.append(
                {
                    "severity": "error",
                    "field": field,
                    "message": "Do not request a review from launch, onboarding, paywall, purchase, error, cancellation, or direct rate-us action contexts.",
                }
            )
        if trigger.get("afterSuccessfulUserOutcome") is not True:
            issues.append(
                {
                    "severity": "warning",
                    "field": field + ".afterSuccessfulUserOutcome",
                    "message": "Review prompts should follow a completed positive outcome, not merely screen views or button taps.",
                }
            )
    blocked = {normalize_context(item) for item in as_list(policy.get("blockedContexts"))}
    missing = BLOCKED_REVIEW_CONTEXTS.intersection({"launch", "onboarding", "paywall", "error"}) - blocked
    if missing:
        issues.append(
            {
                "severity": "warning",
                "field": "reviewPromptPolicy.blockedContexts",
                "message": "Explicitly block review prompts in these contexts: " + ", ".join(sorted(missing)),
            }
        )


def plan_growth_strategy(config: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    validate_subscription_pricing_strategy(config, issues)
    validate_onboarding_strategy(config, issues)
    validate_review_prompt_policy(config, issues)
    pricing_entries = subscription_pricing_entries(config)
    intro_offers = subscription_intro_offer_entries(config)
    return {
        "ok": not [issue for issue in issues if issue["severity"] == "error"],
        "issues": issues,
        "recommendations": [
            "Keep the app download free when monetizing with subscriptions, then price subscription products separately.",
            "Use one subscription group for most apps; offer clear monthly/yearly choices and label annual as best value when the discount is real.",
            "Introduce the paywall after value-first onboarding, not on launch.",
            "Use StoreKit review prompts only after completed positive moments, with local cooldowns and blocked contexts.",
        ],
        "plannedPricingActions": [
            {
                "resource": "subscriptionPrices",
                "subscriptionId": entry.get("subscriptionId") or entry.get("id"),
                "productId": entry.get("productId"),
                "period": entry.get("period") or entry.get("subscriptionPeriod"),
                "territory": entry.get("territory") or entry.get("territoryId"),
                "pricePointId": entry.get("pricePointId") or entry.get("subscriptionPricePointId"),
                "startDate": entry.get("startDate"),
                "preserveCurrentPrice": entry.get("preserveCurrentPrice"),
            }
            for entry in pricing_entries
        ],
        "plannedIntroOfferActions": [
            {
                "resource": "subscriptionIntroductoryOffers",
                "subscriptionId": offer.get("subscriptionId") or offer.get("id"),
                "productId": offer.get("productId"),
                "territory": offer.get("territory") or offer.get("territoryId"),
                "offerMode": offer.get("offerMode", "FREE_TRIAL"),
                "duration": offer.get("duration", "ONE_WEEK"),
                "numberOfPeriods": offer.get("numberOfPeriods", 1),
            }
            for offer in intro_offers
        ],
    }


def configure_subscription_pricing(
    config: dict[str, Any], client: AppStoreConnectClient | None, yes: bool
) -> dict[str, Any]:
    plan = plan_growth_strategy(config)
    if not yes:
        return {"dryRun": True, **plan}
    errors = [issue for issue in plan["issues"] if issue["severity"] == "error"]
    if errors:
        raise AppStoreConnectError("Growth strategy validation failed; fix errors before applying subscription pricing.")
    if client is None:
        raise AppStoreConnectError("An App Store Connect client is required when configuring subscription pricing.")

    product_map = subscription_id_by_product(config)
    results: list[dict[str, Any]] = []
    for index, entry in enumerate(subscription_pricing_entries(config)):
        subscription_id = resolve_subscription_id(entry, product_map)
        price_point_id = entry.get("pricePointId") or entry.get("subscriptionPricePointId")
        if not subscription_id or not price_point_id:
            raise AppStoreConnectError(
                f"subscriptionPricing.products[{index}] requires subscriptionId or productId plus pricePointId."
            )
        response = client.post(
            "/v1/subscriptionPrices",
            build_subscription_price_body(
                subscription_id,
                price_point_id,
                entry.get("territory") or entry.get("territoryId"),
                entry.get("startDate"),
                entry.get("preserveCurrentPrice"),
            ),
        )
        results.append({"resource": "subscriptionPrices", "id": response.get("data", {}).get("id")})

    for index, offer in enumerate(subscription_intro_offer_entries(config)):
        subscription_id = resolve_subscription_id(offer, product_map)
        if not subscription_id:
            raise AppStoreConnectError(
                f"subscriptionPricing.introductoryOffers[{index}] requires subscriptionId or productId."
            )
        response = client.post(
            "/v1/subscriptionIntroductoryOffers",
            build_subscription_intro_offer_body(subscription_id, offer),
        )
        results.append({"resource": "subscriptionIntroductoryOffers", "id": response.get("data", {}).get("id")})
    return {"dryRun": False, "results": results}


def validate_submission_config(config: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    subscriptions = as_list(config.get("subscriptions"))
    version_localizations = as_list(config.get("versionLocalizations"))

    app = config.get("app", {})
    platform = app.get("platform", "IOS")
    if platform not in {"IOS", "MAC_OS", "TV_OS", "VISION_OS"}:
        issues.append(
            {
                "severity": "warning",
                "field": "app.platform",
                "message": "Platform is unusual for App Store release metadata.",
            }
        )

    version = config.get("version", {})
    if version.get("versionString") and not FULL_VERSION_RE.match(str(version["versionString"])):
        issues.append(
            {
                "severity": "error",
                "field": "version.versionString",
                "message": "App Store version must use three period-separated integers, for example 1.2.3.",
            }
        )
    build = config.get("build", {})
    if build.get("buildNumber") and not VERSION_RE.match(str(build["buildNumber"])):
        issues.append(
            {
                "severity": "error",
                "field": "build.buildNumber",
                "message": "Build number must use one to three period-separated integers.",
            }
        )

    for loc in as_list(config.get("appInfoLocalizations")):
        prefix = f"appInfoLocalizations[{loc.get('locale', 'unknown')}]"
        add_length_issue(issues, prefix + ".name", loc.get("name"), *TEXT_LIMITS["name"])
        add_length_issue(issues, prefix + ".subtitle", loc.get("subtitle"), *TEXT_LIMITS["subtitle"])
        if platform in {"IOS", "MAC_OS"} and not loc.get("privacyPolicyUrl"):
            issues.append(
                {
                    "severity": "error",
                    "field": prefix + ".privacyPolicyUrl",
                    "message": "Privacy Policy URL is required for iOS and macOS apps.",
                }
            )

    for loc in version_localizations:
        prefix = f"versionLocalizations[{loc.get('locale', 'unknown')}]"
        for field in ("description", "promotionalText", "whatsNew"):
            add_length_issue(issues, prefix + "." + field, loc.get(field), *TEXT_LIMITS[field])
        validate_keywords(loc.get("keywords"), issues)
        if not loc.get("supportUrl"):
            issues.append(
                {
                    "severity": "error",
                    "field": prefix + ".supportUrl",
                    "message": "Support URL is required for App Store submissions.",
                }
            )
        description = loc.get("description") or ""
        if description and "\n" not in description and len(description) > 900:
            issues.append(
                {
                    "severity": "warning",
                    "field": prefix + ".description",
                    "message": "Description is long without scannable breaks.",
                }
            )
        if "$" in description or " USD" in description.upper():
            issues.append(
                {
                    "severity": "warning",
                    "field": prefix + ".description",
                    "message": "Avoid specific prices in App Store descriptions.",
                }
            )
        if subscriptions:
            validate_subscription_description(description, prefix, issues)

    review = config.get("reviewDetails", {})
    for field in ("contactFirstName", "contactLastName", "contactPhone", "contactEmail"):
        if review and not review.get(field):
            issues.append(
                {
                    "severity": "error",
                    "field": "reviewDetails." + field,
                    "message": "App Review contact information is required before submission.",
                }
            )
    if review.get("demoAccountRequired") and not (
        review.get("demoAccountName") and review.get("demoAccountPassword")
    ):
        issues.append(
            {
                "severity": "error",
                "field": "reviewDetails.demoAccount",
                "message": "A demo username and password are required when demoAccountRequired is true.",
            }
        )

    for group in as_list(config.get("screenshots")):
        files = as_list(group.get("files"))
        field = f"screenshots[{group.get('displayType', 'unknown')}].files"
        if files and not (SCREENSHOT_MIN <= len(files) <= SCREENSHOT_MAX):
            issues.append(
                {
                    "severity": "error",
                    "field": field,
                    "message": "Each screenshot display target must contain one to ten screenshots.",
                }
            )
        for item in files:
            suffix = Path(item).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg"}:
                issues.append(
                    {
                        "severity": "error",
                        "field": field,
                        "message": f"Unsupported screenshot format: {item}",
                    }
                )

    if subscriptions:
        paid_screenshot_seen = False
        for sub in subscriptions:
            if not sub.get("reviewScreenshot"):
                issues.append(
                    {
                        "severity": "warning",
                        "field": "subscriptions.reviewScreenshot",
                        "message": "Subscriptions need an App Review screenshot showing the paid offer.",
                    }
                )
            for loc in as_list(sub.get("localizations")):
                if len(loc.get("name", "")) > 30:
                    issues.append(
                        {
                            "severity": "error",
                            "field": "subscriptions.localizations.name",
                            "message": "Subscription localization names should stay within 30 characters.",
                        }
                    )
            paid_screenshot_seen = paid_screenshot_seen or bool(sub.get("paidFeatureScreenshot"))
        screenshot_groups = as_list(config.get("screenshots"))
        has_paid_label = any(
            "pro" in str(file).lower() or "paid" in str(file).lower()
            for group in screenshot_groups
            for file in as_list(group.get("files"))
        )
        if not paid_screenshot_seen and not has_paid_label:
            issues.append(
                {
                    "severity": "warning",
                    "field": "screenshots",
                    "message": "Subscription apps should clearly mark paid or Pro features in screenshot messaging.",
                }
            )

    validate_subscription_pricing_strategy(config, issues)
    validate_onboarding_strategy(config, issues)
    validate_review_prompt_policy(config, issues)

    ip_review = config.get("ipReview") or {}
    if ip_review:
        if ip_review.get("usesThirdPartyIP") and not ip_review.get("hasWrittenAuthorization"):
            issues.append(
                {
                    "severity": "warning",
                    "field": "ipReview.hasWrittenAuthorization",
                    "message": "If third-party IP appears in the app, screenshots, or metadata, provide written authorization or remove/replace it before App Review.",
                }
            )
        if not ip_review.get("checkedBinaryAndMetadataForOfficialMarks"):
            issues.append(
                {
                    "severity": "warning",
                    "field": "ipReview.checkedBinaryAndMetadataForOfficialMarks",
                    "message": "Review the app icon, bundled assets, screenshots, copy, keywords, and review notes for unlicensed logos, marks, characters, celebrities, event marks, media, or confusingly similar generated artwork.",
                }
            )
        if not ip_review.get("newBuildUploadedForBinaryAssetChanges"):
            issues.append(
                {
                    "severity": "warning",
                    "field": "ipReview.newBuildUploadedForBinaryAssetChanges",
                    "message": "When icon, asset catalog, bundled media, or binary content changes after App Review feedback, upload and select a new build; metadata-only updates are not enough.",
                }
            )
        if ip_review.get("isIndependentReferenceOrFanApp"):
            descriptions = [str(loc.get("description") or "").lower() for loc in version_localizations]
            notes = str(review.get("notes") or "").lower()
            has_description_disclaimer = any(
                ("not affiliated" in description or "independent" in description)
                for description in descriptions
            )
            has_notes_disclaimer = "not affiliated" in notes or "independent" in notes
            if not (ip_review.get("noAffiliationDisclaimerInDescription") and has_description_disclaimer):
                issues.append(
                    {
                        "severity": "warning",
                        "field": "ipReview.noAffiliationDisclaimerInDescription",
                        "message": "Independent reference or fan apps should put a clear no-affiliation disclaimer in the first paragraph of the App Store description.",
                    }
                )
            if not (ip_review.get("noAffiliationDisclaimerInReviewNotes") and has_notes_disclaimer):
                issues.append(
                    {
                        "severity": "warning",
                        "field": "ipReview.noAffiliationDisclaimerInReviewNotes",
                        "message": "Independent reference or fan apps should briefly explain their independence and IP cleanup in App Review notes.",
                    }
                )

    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    return {
        "ok": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "issues": issues,
    }


def clean_attributes(data: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: data[key] for key in allowed if key in data and data[key] is not None}


def plan_submission(config: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    app_info = config.get("appInfo", {})
    category_fields = [
        field
        for field in (
            "primaryCategoryId",
            "primarySubcategoryOneId",
            "primarySubcategoryTwoId",
            "secondaryCategoryId",
            "secondarySubcategoryOneId",
            "secondarySubcategoryTwoId",
        )
        if app_info.get(field)
    ]
    if category_fields:
        actions.append(
            {
                "action": "PATCH",
                "resource": "appInfos",
                "id": app_info.get("id"),
                "fields": category_fields,
            }
        )
    for loc in as_list(config.get("appInfoLocalizations")):
        action = "PATCH" if loc.get("id") else "POST"
        actions.append(
            {
                "action": action,
                "resource": "appInfoLocalizations",
                "locale": loc.get("locale"),
                "fields": sorted(
                    clean_attributes(
                        loc,
                        {"name", "subtitle", "privacyPolicyUrl", "privacyChoicesUrl", "privacyPolicyText"},
                    )
                ),
            }
        )
    version = config.get("version", {})
    if version:
        actions.append(
            {
                "action": "PATCH" if version.get("id") else "POST",
                "resource": "appStoreVersions",
                "versionString": version.get("versionString"),
                "fields": sorted(
                    clean_attributes(
                        version,
                        {
                            "versionString",
                            "copyright",
                            "reviewType",
                            "releaseType",
                            "earliestReleaseDate",
                            "downloadable",
                        },
                    )
                ),
                "buildId": version.get("buildId"),
            }
        )
    for loc in as_list(config.get("versionLocalizations")):
        actions.append(
            {
                "action": "PATCH" if loc.get("id") else "POST",
                "resource": "appStoreVersionLocalizations",
                "locale": loc.get("locale"),
                "fields": sorted(
                    clean_attributes(
                        loc,
                        {"description", "keywords", "marketingUrl", "promotionalText", "supportUrl", "whatsNew"},
                    )
                ),
            }
        )
    if config.get("reviewDetails"):
        actions.append(
            {
                "action": "PATCH" if config["reviewDetails"].get("id") else "POST",
                "resource": "appStoreReviewDetails",
                "fields": sorted(
                    clean_attributes(
                        config["reviewDetails"],
                        {
                            "contactFirstName",
                            "contactLastName",
                            "contactPhone",
                            "contactEmail",
                            "demoAccountName",
                            "demoAccountPassword",
                            "demoAccountRequired",
                            "notes",
                        },
                    )
                ),
            }
        )
    if config.get("ageRating"):
        actions.append(
            {
                "action": "PATCH",
                "resource": "ageRatingDeclarations",
                "fields": sorted((config["ageRating"].get("attributes") or {}).keys()),
            }
        )
    if config.get("pricingAvailability"):
        pricing = config["pricingAvailability"]
        actions.append(
            {
                "action": "POST/PATCH",
                "resource": "appPriceSchedules/appAvailabilities",
                "downloadPrice": pricing.get("downloadPrice"),
                "availability": pricing.get("availability"),
                "baseTerritory": pricing.get("baseTerritory", "USA"),
                "tool": "configure-free-download",
            }
        )
    if config.get("subscriptionPricing"):
        growth_plan = plan_growth_strategy(config)
        actions.append(
            {
                "action": "POST",
                "resource": "subscriptionPrices/subscriptionIntroductoryOffers",
                "priceActionCount": len(growth_plan["plannedPricingActions"]),
                "introOfferActionCount": len(growth_plan["plannedIntroOfferActions"]),
                "tool": "configure-subscription-pricing",
            }
        )
    for group in as_list(config.get("screenshots")):
        actions.append(
            {
                "action": "POST",
                "resource": "appScreenshotSets/appScreenshots",
                "displayType": group.get("displayType"),
                "fileCount": len(as_list(group.get("files"))),
                "replaceExisting": bool(group.get("replaceExisting")),
            }
        )
    if config.get("reviewSubmission", {}).get("createDraft"):
        actions.append(
            {
                "action": "POST",
                "resource": "reviewSubmissions",
                "submitForReview": bool(config.get("reviewSubmission", {}).get("submitForReview")),
            }
        )
    return {"validation": validate_submission_config(config), "actions": actions}


def apply_submission(
    config: dict[str, Any], client: AppStoreConnectClient | None, yes: bool
) -> dict[str, Any]:
    plan = plan_submission(config)
    if not yes:
        return {"dryRun": True, **plan}
    if not plan["validation"]["ok"]:
        raise AppStoreConnectError("Validation failed; fix errors before applying metadata.")
    if client is None:
        raise AppStoreConnectError("An App Store Connect client is required when applying changes.")

    results: list[dict[str, Any]] = []
    app = config.get("app", {})
    app_id = app.get("id")
    version_id = config.get("version", {}).get("id")

    for loc in as_list(config.get("appInfoLocalizations")):
        attrs = clean_attributes(
            loc,
            {"name", "subtitle", "privacyPolicyUrl", "privacyChoicesUrl", "privacyPolicyText"},
        )
        if not attrs:
            continue
        if loc.get("id"):
            body = json_api_body("appInfoLocalizations", attrs, resource_id=loc["id"])
            response = client.patch(f"/v1/appInfoLocalizations/{loc['id']}", body)
        else:
            app_info_id = config.get("appInfo", {}).get("id")
            if not app_info_id:
                raise AppStoreConnectError("appInfo.id is required to create app info localizations.")
            rels = {"appInfo": relationship("appInfos", app_info_id)}
            attrs["locale"] = loc["locale"]
            response = client.post("/v1/appInfoLocalizations", json_api_body("appInfoLocalizations", attrs, rels))
        results.append({"resource": "appInfoLocalizations", "id": response.get("data", {}).get("id")})

    app_info = config.get("appInfo", {})
    category_relationships = {
        "primaryCategoryId": "primaryCategory",
        "primarySubcategoryOneId": "primarySubcategoryOne",
        "primarySubcategoryTwoId": "primarySubcategoryTwo",
        "secondaryCategoryId": "secondaryCategory",
        "secondarySubcategoryOneId": "secondarySubcategoryOne",
        "secondarySubcategoryTwoId": "secondarySubcategoryTwo",
    }
    rels = {
        rel_name: relationship("appCategories", app_info[field_name])
        for field_name, rel_name in category_relationships.items()
        if app_info.get(field_name)
    }
    if rels:
        app_info_id = app_info.get("id")
        if not app_info_id:
            raise AppStoreConnectError("appInfo.id is required to update app categories.")
        response = client.patch(f"/v1/appInfos/{app_info_id}", json_api_body("appInfos", relationships=rels, resource_id=app_info_id))
        results.append({"resource": "appInfos", "id": response.get("data", {}).get("id")})

    version = config.get("version", {})
    if version:
        attrs = clean_attributes(
            version,
            {"versionString", "copyright", "reviewType", "releaseType", "earliestReleaseDate", "downloadable"},
        )
        rels = {}
        if version.get("buildId"):
            rels["build"] = relationship("builds", version["buildId"])
        if version_id:
            response = client.patch(
                f"/v1/appStoreVersions/{version_id}",
                json_api_body("appStoreVersions", attrs, rels or None, version_id),
            )
        else:
            if not app_id:
                raise AppStoreConnectError("app.id is required to create an app store version.")
            attrs["platform"] = app.get("platform", "IOS")
            rels["app"] = relationship("apps", app_id)
            response = client.post("/v1/appStoreVersions", json_api_body("appStoreVersions", attrs, rels))
            version_id = response.get("data", {}).get("id")
        results.append({"resource": "appStoreVersions", "id": response.get("data", {}).get("id")})

    for loc in as_list(config.get("versionLocalizations")):
        attrs = clean_attributes(
            loc,
            {"description", "keywords", "marketingUrl", "promotionalText", "supportUrl", "whatsNew"},
        )
        if not attrs:
            continue
        if loc.get("id"):
            response = client.patch(
                f"/v1/appStoreVersionLocalizations/{loc['id']}",
                json_api_body("appStoreVersionLocalizations", attrs, resource_id=loc["id"]),
            )
        else:
            if not version_id:
                raise AppStoreConnectError("version.id is required to create version localizations.")
            attrs["locale"] = loc["locale"]
            rels = {"appStoreVersion": relationship("appStoreVersions", version_id)}
            response = client.post(
                "/v1/appStoreVersionLocalizations",
                json_api_body("appStoreVersionLocalizations", attrs, rels),
            )
        results.append({"resource": "appStoreVersionLocalizations", "id": response.get("data", {}).get("id")})

    review = config.get("reviewDetails")
    if review:
        attrs = clean_attributes(
            review,
            {
                "contactFirstName",
                "contactLastName",
                "contactPhone",
                "contactEmail",
                "demoAccountName",
                "demoAccountPassword",
                "demoAccountRequired",
                "notes",
            },
        )
        if review.get("id"):
            response = client.patch(
                f"/v1/appStoreReviewDetails/{review['id']}",
                json_api_body("appStoreReviewDetails", attrs, resource_id=review["id"]),
            )
        else:
            if not version_id:
                raise AppStoreConnectError("version.id is required to create review details.")
            rels = {"appStoreVersion": relationship("appStoreVersions", version_id)}
            response = client.post("/v1/appStoreReviewDetails", json_api_body("appStoreReviewDetails", attrs, rels))
        results.append({"resource": "appStoreReviewDetails", "id": response.get("data", {}).get("id")})

    age = config.get("ageRating")
    if age:
        age_id = age.get("id")
        if not age_id:
            raise AppStoreConnectError("ageRating.id is required to update age rating declarations.")
        response = client.patch(
            f"/v1/ageRatingDeclarations/{age_id}",
            json_api_body("ageRatingDeclarations", age.get("attributes", {}), resource_id=age_id),
        )
        results.append({"resource": "ageRatingDeclarations", "id": response.get("data", {}).get("id")})

    review_submission = config.get("reviewSubmission", {})
    if review_submission.get("createDraft"):
        if not app_id:
            raise AppStoreConnectError("app.id is required to create a review submission.")
        if not version_id:
            raise AppStoreConnectError("version.id is required to add the app version to review submission.")
        submission = client.post(
            "/v1/reviewSubmissions",
            json_api_body(
                "reviewSubmissions",
                {"platform": app.get("platform", "IOS")},
                {"app": relationship("apps", app_id)},
            ),
        )
        submission_id = submission["data"]["id"]
        item = client.post(
            "/v1/reviewSubmissionItems",
            json_api_body(
                "reviewSubmissionItems",
                relationships={
                    "reviewSubmission": relationship("reviewSubmissions", submission_id),
                    "appStoreVersion": relationship("appStoreVersions", version_id),
                },
            ),
        )
        results.append(
            {
                "resource": "reviewSubmissions",
                "id": submission_id,
                "itemId": item.get("data", {}).get("id"),
            }
        )
        if review_submission.get("submitForReview"):
            response = client.patch(
                f"/v1/reviewSubmissions/{submission_id}",
                json_api_body(
                    "reviewSubmissions",
                    {"submitted": True},
                    resource_id=submission_id,
                ),
            )
            results.append({"resource": "reviewSubmissions.submitted", "id": response.get("data", {}).get("id")})

    return {"dryRun": False, "results": results}


def upload_screenshot_file(
    client: AppStoreConnectClient,
    screenshot_set_id: str,
    file_path: Path,
) -> dict[str, Any]:
    file_path = file_path.expanduser()
    size = file_path.stat().st_size
    reservation = client.post(
        "/v1/appScreenshots",
        json_api_body(
            "appScreenshots",
            {"fileSize": size, "fileName": file_path.name},
            {"appScreenshotSet": relationship("appScreenshotSets", screenshot_set_id)},
        ),
    )
    upload_operations(file_path, reservation["data"]["attributes"]["uploadOperations"])
    screenshot_id = reservation["data"]["id"]
    checksum = file_hash(file_path, "md5")
    return client.patch(
        f"/v1/appScreenshots/{screenshot_id}",
        json_api_body(
            "appScreenshots",
            {"uploaded": True, "sourceFileChecksum": checksum},
            resource_id=screenshot_id,
        ),
    )


def upload_screenshots(
    config: dict[str, Any], client: AppStoreConnectClient | None, yes: bool
) -> dict[str, Any]:
    groups = as_list(config.get("screenshots"))
    if not yes:
        return {
            "dryRun": True,
            "groups": [
                {
                    "displayType": group.get("displayType"),
                    "localizationId": group.get("localizationId"),
                    "fileCount": len(as_list(group.get("files"))),
                }
                for group in groups
            ],
        }
    if client is None:
        raise AppStoreConnectError("An App Store Connect client is required when uploading screenshots.")
    results = []
    for group in groups:
        localization_id = group.get("localizationId")
        display_type = group.get("displayType")
        if not localization_id or not display_type:
            raise AppStoreConnectError("Each screenshot group requires localizationId and displayType.")
        if group.get("replaceExisting"):
            existing = client.get(
                f"/v1/appStoreVersionLocalizations/{localization_id}/appScreenshotSets",
                {"fields[appScreenshotSets]": "screenshotDisplayType"},
            )
            for item in existing.get("data", []):
                if item.get("attributes", {}).get("screenshotDisplayType") == display_type:
                    client.delete(f"/v1/appScreenshotSets/{item['id']}")
        screenshot_set = client.post(
            "/v1/appScreenshotSets",
            json_api_body(
                "appScreenshotSets",
                {"screenshotDisplayType": display_type},
                {"appStoreVersionLocalization": relationship("appStoreVersionLocalizations", localization_id)},
            ),
        )
        set_id = screenshot_set["data"]["id"]
        uploaded = []
        for file_name in as_list(group.get("files")):
            response = upload_screenshot_file(client, set_id, Path(file_name))
            uploaded.append(response.get("data", {}).get("id"))
        results.append({"screenshotSetId": set_id, "uploadedScreenshotIds": uploaded})
    return {"dryRun": False, "results": results}


def upload_build_api(args: argparse.Namespace, client: AppStoreConnectClient | None) -> dict[str, Any]:
    file_path = Path(args.file).expanduser()
    version_plan = None
    version_string = args.version_string
    build_number = args.build_number
    if args.auto_version or not (version_string and build_number):
        version_plan = plan_versioning(
            args.project_dir,
            release_level=args.release_level,
            iteration_count=args.iteration_count,
            current_version=args.current_version,
            current_build=args.current_build,
            use_git=not args.no_git,
        )
        version_string = version_string or version_plan["recommendation"]["versionString"]
        build_number = build_number or version_plan["recommendation"]["buildNumber"]
    if not version_string or not build_number:
        raise AppStoreConnectError(
            "Provide --version-string and --build-number, or pass --auto-version to infer them."
        )
    ensure_app_store_version_format(version_string)
    ensure_version_format(build_number, "Build number")
    if not args.yes:
        return {
            "dryRun": True,
            "appId": args.app_id,
            "file": str(file_path),
            "fileExists": file_path.exists(),
            "versionString": version_string,
            "buildNumber": build_number,
            "platform": args.platform,
            "versionPlan": version_plan,
        }
    if not file_path.exists():
        raise AppStoreConnectError(f"Build file not found: {file_path}")
    if client is None:
        raise AppStoreConnectError("An App Store Connect client is required when uploading builds.")
    ext = file_path.suffix.lower()
    uti = "com.apple.ipa" if ext == ".ipa" else "com.apple.pkg" if ext == ".pkg" else None
    if not uti:
        raise AppStoreConnectError("Build upload API supports .ipa and .pkg files.")
    build_upload = client.post(
        "/v1/buildUploads",
        json_api_body(
            "buildUploads",
            {
                "cfBundleShortVersionString": version_string,
                "cfBundleVersion": build_number,
                "platform": args.platform,
            },
            {"app": relationship("apps", args.app_id)},
        ),
    )
    upload_id = build_upload["data"]["id"]
    file_reservation = client.post(
        "/v1/buildUploadFiles",
        json_api_body(
            "buildUploadFiles",
            {
                "assetType": "ASSET",
                "fileName": file_path.name,
                "fileSize": file_path.stat().st_size,
                "uti": uti,
            },
            {"buildUpload": relationship("buildUploads", upload_id)},
        ),
    )
    file_id = file_reservation["data"]["id"]
    upload_operations(file_path, file_reservation["data"]["attributes"]["uploadOperations"], timeout=900)
    client.patch(
        f"/v1/buildUploadFiles/{file_id}",
        json_api_body(
            "buildUploadFiles",
            {
                "uploaded": True,
                "sourceFileChecksums": {
                    "file": {
                        "hash": base64.b64encode(bytes.fromhex(file_hash(file_path, "sha_256"))).decode("ascii"),
                        "algorithm": "SHA_256",
                    }
                },
            },
            resource_id=file_id,
        ),
    )
    final = client.get(f"/v1/buildUploads/{upload_id}", {"include": "build,buildUploadFiles"})
    if args.wait:
        deadline = time.time() + args.wait
        while time.time() < deadline:
            state = final.get("data", {}).get("attributes", {}).get("state", {}).get("state")
            if state in {"COMPLETE", "FAILED"}:
                break
            time.sleep(20)
            final = client.get(f"/v1/buildUploads/{upload_id}", {"include": "build,buildUploadFiles"})
    return {"dryRun": False, "buildUploadId": upload_id, "buildUploadFileId": file_id, "response": final}


def transporter_command(args: argparse.Namespace, credentials: Credentials) -> list[str]:
    token = credentials.token(lifetime_seconds=10 * 60)
    binary = args.transporter or shutil.which("iTMSTransporter")
    if not binary:
        xcrun = shutil.which("xcrun")
        if xcrun:
            return [
                xcrun,
                "iTMSTransporter",
                "-m",
                "upload",
                "-jwt",
                token,
                "-v",
                args.verbosity,
                "-assetFile",
                args.file,
            ]
        raise AppStoreConnectError("Could not find iTMSTransporter or xcrun.")
    return [binary, "-m", "upload", "-jwt", token, "-v", args.verbosity, "-assetFile", args.file]


def run_transporter(args: argparse.Namespace) -> dict[str, Any]:
    if not args.yes:
        transporter = args.transporter or shutil.which("iTMSTransporter")
        if transporter:
            command = [transporter, "-m", "upload"]
        elif shutil.which("xcrun"):
            command = [shutil.which("xcrun"), "iTMSTransporter", "-m", "upload"]
        else:
            command = ["iTMSTransporter", "-m", "upload"]
        return {
            "dryRun": True,
            "command": command + ["-jwt", "<jwt>", "-v", args.verbosity, "-assetFile", args.file],
        }
    credentials = Credentials.from_env()
    command = transporter_command(args, credentials)
    redacted = ["<jwt>" if item.startswith("eyJ") else item for item in command]
    proc = subprocess.run(command, check=False)
    return {"dryRun": False, "returnCode": proc.returncode, "command": redacted}


def doctor() -> dict[str, Any]:
    checks = {
        "python": sys.version.split()[0],
        "openssl": bool(shutil.which("openssl")),
        "xcrun": bool(shutil.which("xcrun")),
        "iTMSTransporter": bool(shutil.which("iTMSTransporter")),
        "pillow": False,
        "credentials": credential_env_status(),
        "credentialSetup": {
            "recommendedKeyDirectory": str(DEFAULT_KEY_DIR),
            "recommendedEnvFile": str(DEFAULT_ENV_FILE),
            "command": (
                "doctor --fix --key-id <KEY_ID> --issuer-id <ISSUER_ID> "
                "--import-key ~/Downloads/AuthKey_<KEY_ID>.p8 --write-env-file"
            ),
        },
    }
    try:
        import PIL  # type: ignore

        checks["pillow"] = True
        checks["pillowVersion"] = getattr(PIL, "__version__", "installed")
    except Exception:
        checks["pillow"] = False
    return checks


def add_common_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="Path to an App Store submission JSON config.")


def add_versioning_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-dir", default=".", help="Apple project directory to inspect.")
    parser.add_argument(
        "--release-level",
        choices=["auto", "same", "patch", "minor", "major"],
        default="auto",
        help="How to bump CFBundleShortVersionString. auto uses git history.",
    )
    parser.add_argument("--iteration-count", type=int, help="Codex/build iterations to fold into the build number.")
    parser.add_argument("--current-version", help="Override detected CFBundleShortVersionString.")
    parser.add_argument("--current-build", help="Override detected CFBundleVersion.")
    parser.add_argument("--no-git", action="store_true", help="Do not use git commit history for iteration count.")


def add_credential_setup_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--key-id", help="App Store Connect API key ID.")
    parser.add_argument("--issuer-id", help="Issuer ID for team API keys.")
    parser.add_argument("--key-type", choices=["team", "individual"], default=None, help="API key type.")
    parser.add_argument("--key-path", help="Existing private key path to reference in exports.")
    parser.add_argument("--key-dir", help="Directory for imported AuthKey_<KEY_ID>.p8 files.")
    parser.add_argument("--import-key", help="Copy a downloaded AuthKey_<KEY_ID>.p8 into the local private key directory.")
    parser.add_argument(
        "--write-env-file",
        nargs="?",
        const=str(DEFAULT_ENV_FILE),
        help="Write export lines to a local env file. Defaults to ~/.appstoreconnect/credentials.env.",
    )
    parser.add_argument("--verify", action="store_true", help="Make a read-only API request to verify credentials.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--fix", action="store_true", help="Prepare secure local credential exports.")
    add_credential_setup_arguments(doctor_parser)
    setup = sub.add_parser("credential-setup", help="Prepare local App Store Connect credential exports.")
    add_credential_setup_arguments(setup)
    sub.add_parser("field-map")
    sub.add_parser("template")

    version_plan = sub.add_parser("plan-version", help="Infer the next App Store version and build number.")
    add_versioning_arguments(version_plan)

    version_apply = sub.add_parser(
        "apply-version",
        help="Update Xcode project version/build settings and optionally a submission config.",
    )
    add_versioning_arguments(version_apply)
    version_apply.add_argument("--config", help="Submission JSON to update with the recommended version/build.")
    version_apply.add_argument(
        "--force-plist",
        action="store_true",
        help="Also overwrite Info.plist values that reference build setting variables.",
    )
    version_apply.add_argument("--yes", action="store_true", help="Apply changes. Without this flag, prints a dry run.")

    validate = sub.add_parser("validate", help="Validate an App Store submission JSON config.")
    add_common_config_argument(validate)

    plan = sub.add_parser("plan", help="Show the API operations implied by a config.")
    add_common_config_argument(plan)

    growth = sub.add_parser(
        "plan-growth-strategy",
        help="Validate subscription pricing, onboarding, and StoreKit review trigger strategy.",
    )
    add_common_config_argument(growth)

    apply = sub.add_parser("apply-metadata", help="Apply app info, version, localization, review, and age fields.")
    add_common_config_argument(apply)
    apply.add_argument("--yes", action="store_true", help="Apply changes. Without this flag, prints a dry run.")

    free = sub.add_parser(
        "configure-free-download",
        help="Set the app to free download and make it available in all App Store territories.",
    )
    free.add_argument("--app-id", help="App Store Connect app id. Can also be read from --config app.id.")
    free.add_argument("--config", help="Submission JSON containing app.id.")
    free.add_argument("--base-territory", default="USA", help="Base territory for the free app price point.")
    free.add_argument("--yes", action="store_true", help="Apply changes. Without this flag, prints a dry run.")

    sub_price = sub.add_parser(
        "configure-subscription-pricing",
        help="Create subscription prices and introductory offers from a submission config.",
    )
    add_common_config_argument(sub_price)
    sub_price.add_argument("--yes", action="store_true", help="Apply changes. Without this flag, prints a dry run.")

    sub_points = sub.add_parser("list-subscription-price-points", help="List price points for a subscription.")
    sub_points.add_argument("--subscription-id", required=True)
    sub_points.add_argument("--territory", help="Optional App Store territory filter, such as USA.")

    shots = sub.add_parser("upload-screenshots", help="Upload screenshots from the config.")
    add_common_config_argument(shots)
    shots.add_argument("--yes", action="store_true", help="Upload screenshots. Without this flag, prints a dry run.")

    apps = sub.add_parser("list-apps", help="List App Store Connect apps visible to the API key.")
    apps.add_argument("--bundle-id")
    apps.add_argument("--name")

    versions = sub.add_parser("list-versions", help="List App Store versions for an app.")
    versions.add_argument("--app-id", required=True)
    versions.add_argument("--platform")

    raw = sub.add_parser("api", help="Make a raw API request for advanced workflows.")
    raw.add_argument("method", choices=["GET", "POST", "PATCH", "DELETE"])
    raw.add_argument("path")
    raw.add_argument("--body", help="Path to a JSON body for POST or PATCH.")

    upload = sub.add_parser("upload-build-api", help="Upload an .ipa or .pkg with Build Uploads API.")
    upload.add_argument("--app-id", required=True)
    upload.add_argument("--file", required=True)
    upload.add_argument("--version-string")
    upload.add_argument("--build-number")
    upload.add_argument("--platform", default="IOS")
    upload.add_argument("--auto-version", action="store_true", help="Infer missing version/build values from the project.")
    add_versioning_arguments(upload)
    upload.add_argument("--wait", type=int, default=0, help="Seconds to poll for processing state.")
    upload.add_argument("--yes", action="store_true", help="Upload the file. Without this flag, prints a dry run.")

    transporter = sub.add_parser("upload-build-transporter", help="Upload an .ipa or .pkg with Transporter.")
    transporter.add_argument("--file", required=True)
    transporter.add_argument("--transporter", help="Path to iTMSTransporter.")
    transporter.add_argument("--verbosity", default="eXtreme")
    transporter.add_argument("--yes", action="store_true", help="Run Transporter. Without this flag, prints a dry run.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            print_json(credential_setup(args) if args.fix else doctor())
        elif args.command == "credential-setup":
            print_json(credential_setup(args))
        elif args.command == "field-map":
            print_json(load_json(FIELD_MAP))
        elif args.command == "template":
            print(SUBMISSION_TEMPLATE.read_text(encoding="utf-8"))
        elif args.command == "plan-version":
            print_json(
                plan_versioning(
                    args.project_dir,
                    release_level=args.release_level,
                    iteration_count=args.iteration_count,
                    current_version=args.current_version,
                    current_build=args.current_build,
                    use_git=not args.no_git,
                )
            )
        elif args.command == "apply-version":
            print_json(apply_versioning(args))
        elif args.command == "validate":
            print_json(validate_submission_config(load_json(args.config)))
        elif args.command == "plan":
            print_json(plan_submission(load_json(args.config)))
        elif args.command == "plan-growth-strategy":
            print_json(plan_growth_strategy(load_json(args.config)))
        elif args.command == "apply-metadata":
            client = AppStoreConnectClient() if args.yes else None
            print_json(apply_submission(load_json(args.config), client, args.yes))
        elif args.command == "configure-free-download":
            client = AppStoreConnectClient() if args.yes else None
            print_json(configure_free_download(args, client))
        elif args.command == "configure-subscription-pricing":
            client = AppStoreConnectClient() if args.yes else None
            print_json(configure_subscription_pricing(load_json(args.config), client, args.yes))
        elif args.command == "list-subscription-price-points":
            query = {"include": "territory", "limit": "200"}
            if args.territory:
                query["filter[territory]"] = args.territory
            print_json(AppStoreConnectClient().get(f"/v1/subscriptions/{args.subscription_id}/pricePoints", query))
        elif args.command == "upload-screenshots":
            client = AppStoreConnectClient() if args.yes else None
            print_json(upload_screenshots(load_json(args.config), client, args.yes))
        elif args.command == "list-apps":
            query = {}
            if args.bundle_id:
                query["filter[bundleId]"] = args.bundle_id
            if args.name:
                query["filter[name]"] = args.name
            print_json(AppStoreConnectClient().get("/v1/apps", query or None))
        elif args.command == "list-versions":
            query = {"include": "appStoreVersionLocalizations,appStoreReviewDetail,build"}
            if args.platform:
                query["filter[platform]"] = args.platform
            print_json(AppStoreConnectClient().get(f"/v1/apps/{args.app_id}/appStoreVersions", query))
        elif args.command == "api":
            body = load_json(args.body) if args.body else None
            print_json(AppStoreConnectClient().request(args.method, args.path, body=body))
        elif args.command == "upload-build-api":
            client = AppStoreConnectClient() if args.yes else None
            print_json(upload_build_api(args, client))
        elif args.command == "upload-build-transporter":
            print_json(run_transporter(args))
        else:
            parser.error(f"Unsupported command: {args.command}")
    except (AppStoreConnectError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
