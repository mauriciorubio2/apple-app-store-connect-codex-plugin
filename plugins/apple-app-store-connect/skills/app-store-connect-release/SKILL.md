---
name: app-store-connect-release
description: Prepare, validate, upload, and submit Apple App Store Connect releases from Codex, including ASO/Apple Ads metadata, conversion-focused screenshots, build upload, review details, subscriptions, and custom product pages.
---

# App Store Connect Release

Use this skill when the user asks Codex to work on App Store Connect, TestFlight/App Store build uploads, App Store release metadata, screenshots, Apple Ads or ASO copy, subscriptions, in-app purchase review material, custom product pages, product page optimization, or App Review submissions.

## Operating Rules

- Never submit an app, upload screenshots, change pricing/availability, or mutate App Store Connect unless the user has explicitly confirmed the exact change.
- Run dry-run commands first. Use `--yes` only after the user confirms.
- Never commit, print, or paste `.p8` private keys, JWTs, demo passwords, unreleased screenshots, or private app metadata into public files.
- Use App Store Connect API keys from environment variables:
  - `ASC_KEY_ID`
  - `ASC_KEY_PATH`
  - `ASC_ISSUER_ID` for team keys
  - `ASC_KEY_TYPE=individual` for individual keys
- If credentials are missing, run `doctor --fix` or `credential-setup` to copy a downloaded `.p8` key into `~/.appstoreconnect/private_keys/`, write a local ignored env file, and print the exact `source` command. Do not invent credentials or commit the env file.
- Prefer the bundled scripts over hand-written API calls. They encode field names, dry runs, upload reservations, and checksum commits.
- If a field is not exposed by Apple public APIs, prepare a precise checklist for the user rather than pretending it can be filled automatically.

## First Steps

1. Inspect the project and gather the app facts:
   - Bundle ID, App Store app ID, SKU, platform, current version, build number, primary locale.
   - Target audience, primary use case, top three benefits, differentiators, pricing/subscription model.
   - Required URLs: privacy policy, support, marketing, privacy choices if applicable.
   - App Review contact, demo account, notes, feature flags, sandbox subscription setup.
2. Run:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor
python3 plugins/apple-app-store-connect/scripts/asc_cli.py field-map
python3 plugins/apple-app-store-connect/scripts/asc_cli.py template
```

3. If `doctor` reports missing credentials and the user has downloaded an API key, prepare local credentials without exposing the private key:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor --fix \
  --key-id <KEY_ID> \
  --issuer-id <ISSUER_ID> \
  --import-key ~/Downloads/AuthKey_<KEY_ID>.p8 \
  --write-env-file
```

Then source the returned env file and rerun `doctor`. For individual API keys, pass `--key-type individual` and omit `--issuer-id`.

4. Draft or update a submission JSON file using `assets/submission-template.json`.
5. Plan versioning before upload or submission:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan-version \
  --project-dir . \
  --release-level auto
```

Use `--iteration-count <n>` when Codex or a build system has tracked the number of release-candidate iterations. This folds those iterations into the build number.

6. Validate and plan before changes:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py validate --config appstore-submission.json
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan --config appstore-submission.json
```

7. For free-to-download apps, plan the $0 price and all-country availability before submission:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-free-download \
  --config appstore-submission.json
```

Apply only after the user confirms the app should be free in every App Store territory:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-free-download \
  --config appstore-submission.json --yes
```

## Metadata Guidance

Use Apple's product page recommendations:

- Name: 2-30 characters. Make the app name or brand clear. Add a category/use-case phrase only if it fits naturally.
- Subtitle: 30 characters maximum. Describe the core user outcome, not a vague slogan.
- Description: lead with the strongest benefit in the first sentence because it is visible before expansion. Use one concise paragraph followed by a short feature list. Avoid keyword stuffing and avoid specific prices.
- Keywords: 100 characters maximum. Use relevant comma-separated terms with no spaces after commas. Avoid duplicates, plural variants when singular is present, category names, competitor names, trademarks, celebrity names, irrelevant terms, and objectionable terms.
- Promotional text: 170 characters maximum. Use for current launches, offers, or updates; do not use it for search ranking keywords.
- What's New: describe user-visible changes plainly. Avoid empty "bug fixes" copy when the release has meaningful improvements.

When optimizing for Apple Ads:

- Align copy and screenshots to a specific search intent or ad group.
- Prefer custom product pages for distinct audience or keyword clusters.
- Make each custom page's screenshots, promotional text, and keywords unique to that intent.
- Use product page optimization tests for icons, screenshots, and previews when the app is already eligible.

## Screenshot Guidance

Apple allows one to ten screenshots per supported device size/localization. The first one to three images matter most in search results when no app preview appears.

- Use real app UI captures as the base image.
- Use bright solid backgrounds that stand out in search results while preserving app-legibility.
- Make one benefit unmistakable per screenshot and align it with high-intent ASO/Apple Ads search terms.
- Keep overlay copy short enough to scan, with a sales-focused header and optional CTA such as "Free to download", "Track every kickoff", or "Start free trial".
- Include at least one dark-mode screenshot if dark mode is a meaningful part of the experience.
- If subscriptions or paid features are shown, mark them clearly with labels such as "Pro feature", "Included with Pro", or the subscription tier name.
- Do not imply a paid feature is free. Do not hide terms, paywall state, or subscription context.

To render screenshots from raw captures:

```bash
python3 plugins/apple-app-store-connect/scripts/generate_screenshots.py \
  --config plugins/apple-app-store-connect/assets/screenshot-template.json
```

Install Pillow first if the script asks for it:

```bash
python3 -m pip install pillow
```

Upload screenshots only after dry run and confirmation:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-screenshots \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-screenshots \
  --config appstore-submission.json --yes
```

## Build Uploads

The plugin supports Apple's Build Uploads API for `.ipa` and `.pkg` files and also includes a Transporter fallback.

## Versioning

Apple separates:

- App Store version: `CFBundleShortVersionString`, the user-visible version. Use three period-separated integers such as `1.2.3`, and keep it matched with App Store Connect's version string.
- Build number: `CFBundleVersion`, the uploaded build iteration. Use one to three period-separated integers and increment it for each upload.

Use the version planner before uploading:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan-version \
  --project-dir . \
  --release-level auto \
  --iteration-count 7
```

The planner reads Xcode `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, literal `Info.plist` values, and git history. `--release-level auto` is conservative: breaking-change markers produce a major bump, conventional `feat:` commits produce a minor bump, and other release builds produce a patch bump. If Codex has a reliable iteration count, pass it with `--iteration-count`; otherwise the planner uses commits since the latest tag or falls back to one.

Apply the version locally only after confirmation:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py apply-version \
  --project-dir . \
  --config appstore-submission.json \
  --release-level auto \
  --iteration-count 7 \
  --yes
```

This updates `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, literal Info.plist version values, and the submission config's version/build fields. Do not use `--force-plist` unless the user wants variable Info.plist values overwritten.

API upload dry run:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --version-string 1.0.0 \
  --build-number 42
```

Automatic-version upload dry run:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --auto-version \
  --project-dir .
```

Confirmed API upload:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --version-string 1.0.0 \
  --build-number 42 \
  --wait 1800 \
  --yes
```

Transporter fallback:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-transporter \
  --file build/App.ipa
```

Use the build relationship in `version.buildId` after Apple finishes processing the build.

## Applying Metadata

Dry run:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py apply-metadata \
  --config appstore-submission.json
```

Confirmed apply:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py apply-metadata \
  --config appstore-submission.json --yes
```

This can update app info localizations, version fields, version localizations, App Review details, age rating declarations, and the selected build when IDs are supplied. Use `list-apps` and `list-versions` to discover IDs:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py list-apps --bundle-id com.example.product
python3 plugins/apple-app-store-connect/scripts/asc_cli.py list-versions --app-id 1234567890 --platform IOS
```

## Pricing And Availability

For free apps, set the download price to $0 and make the app available in all countries before review:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-free-download \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-free-download \
  --config appstore-submission.json --yes
```

The confirmed apply finds the base territory's free price point, writes an app price schedule at $0, enables availability for all current App Store territories, and sets new territories to become available automatically. Use this for free-download apps with paid subscriptions or IAP; subscription prices remain separate from the app download price.

## Subscriptions And IAP

For subscriptions and paid features:

- Include localized subscription names and descriptions.
- Include App Review screenshots for the paywall or purchased feature.
- For first-time IAPs/subscriptions, prepare to submit them with a new app version when Apple requires it.
- In screenshots and description, avoid presenting paid-only features as free.
- App Review notes should explain how reviewers can access sandbox purchase paths or pre-unlocked demos.

## Manual Or Limited Areas

Prepare these for the user, but do not claim full API automation unless Apple adds public endpoints:

- Paid Apps Agreement, tax, and banking setup.
- App Privacy nutrition labels.
- Some export compliance documents and account/legal forms.
- Regulated claims for medical, financial, gambling, kids, legal, or safety-sensitive apps.

## MCP Tools

When the plugin MCP server is installed, prefer these tools over shell calls:

- `asc_doctor`
- `asc_credential_setup`
- `asc_field_map`
- `asc_validate_submission_config`
- `asc_plan_submission_config`
- `asc_plan_version`
- `asc_apply_version`
- `asc_apply_metadata`
- `asc_configure_free_download`
- `asc_list_apps`
- `asc_upload_build_api`
- `asc_generate_screenshots`

The same confirmation rules apply to MCP tools: pass `confirm: true` only after the user approves the action.
