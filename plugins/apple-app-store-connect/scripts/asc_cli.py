#!/usr/bin/env python3
"""Command-line release helper for the Apple App Store Connect Codex plugin."""

from __future__ import annotations

import argparse
import json
import os
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

TEXT_LIMITS = {
    "name": (2, 30),
    "subtitle": (0, 30),
    "keywords": (0, 100),
    "promotionalText": (0, 170),
    "description": (0, 4000),
    "whatsNew": (0, 4000),
}

SCREENSHOT_MIN = 1
SCREENSHOT_MAX = 10


def load_json(path: str | Path) -> Any:
    with Path(path).expanduser().open("r", encoding="utf-8") as file:
        return json.load(file)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


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


def validate_submission_config(config: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []

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

    for loc in as_list(config.get("versionLocalizations")):
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

    subscriptions = as_list(config.get("subscriptions"))
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
    if not args.yes:
        return {
            "dryRun": True,
            "appId": args.app_id,
            "file": str(file_path),
            "fileExists": file_path.exists(),
            "versionString": args.version_string,
            "buildNumber": args.build_number,
            "platform": args.platform,
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
                "cfBundleShortVersionString": args.version_string,
                "cfBundleVersion": args.build_number,
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
                    "file": {"hash": file_hash(file_path, "sha_256"), "algorithm": "SHA_256"}
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
        "credentials": {
            "ASC_KEY_ID": bool(os.environ.get("ASC_KEY_ID")),
            "ASC_ISSUER_ID": bool(os.environ.get("ASC_ISSUER_ID")),
            "ASC_KEY_PATH": bool(os.environ.get("ASC_KEY_PATH")),
            "ASC_KEY_TYPE": os.environ.get("ASC_KEY_TYPE", "team"),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    sub.add_parser("field-map")
    sub.add_parser("template")

    validate = sub.add_parser("validate", help="Validate an App Store submission JSON config.")
    add_common_config_argument(validate)

    plan = sub.add_parser("plan", help="Show the API operations implied by a config.")
    add_common_config_argument(plan)

    apply = sub.add_parser("apply-metadata", help="Apply app info, version, localization, review, and age fields.")
    add_common_config_argument(apply)
    apply.add_argument("--yes", action="store_true", help="Apply changes. Without this flag, prints a dry run.")

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
    upload.add_argument("--version-string", required=True)
    upload.add_argument("--build-number", required=True)
    upload.add_argument("--platform", default="IOS")
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
            print_json(doctor())
        elif args.command == "field-map":
            print_json(load_json(FIELD_MAP))
        elif args.command == "template":
            print(SUBMISSION_TEMPLATE.read_text(encoding="utf-8"))
        elif args.command == "validate":
            print_json(validate_submission_config(load_json(args.config)))
        elif args.command == "plan":
            print_json(plan_submission(load_json(args.config)))
        elif args.command == "apply-metadata":
            client = AppStoreConnectClient() if args.yes else None
            print_json(apply_submission(load_json(args.config), client, args.yes))
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
