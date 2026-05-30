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
- Subscription apps: append a `SUBSCRIPTION INFORMATION:` section to the App Store description before review. It must include the Pro/subscription value, trial and plan cadence summary, auto-renewal/cancellation disclosure, a functional Privacy Policy URL, and a functional Terms of Use/EULA URL. Apple can block review if the Terms of Use link is missing from metadata.
- Third-party/IP-sensitive apps: do not use unlicensed official logos, crests, trophies, event marks, player photos, broadcaster marks, or confusingly similar generated artwork in the app binary, app icon, screenshots, or metadata. If the app is an independent fan/reference app, put a clear no-affiliation disclaimer in the first paragraph of the description, repeat it in App Review notes, avoid trademark-heavy keywords, and use original generic artwork unless the user provides documentary authorization.
- Keywords: 100 characters maximum. Use relevant comma-separated terms with no spaces after commas. Avoid duplicates, plural variants when singular is present, category names, competitor names, trademarks, celebrity names, irrelevant terms, and objectionable terms.
- Promotional text: 170 characters maximum. Use for current launches, offers, or updates; do not use it for search ranking keywords.
- What's New: describe user-visible changes plainly. Avoid empty "bug fixes" copy when the release has meaningful improvements.

## Third-Party IP Safety

Run this checklist for any app that references real brands, organizations, people, characters, events, teams, leagues, venues, books, films, music, games, public figures, media properties, or third-party datasets.

- Identify every place third-party IP could appear: app name, subtitle, keywords, description, promotional text, screenshots, app icon, in-app art, generated images, logos, crests, product shapes, player/celebrity photos, team or event marks, bundled media, and App Review notes.
- If the user has written authorization, record only the need-to-know App Review note and attachment checklist. Do not commit licenses, contact details, or confidential agreements unless the user explicitly asks.
- If there is no authorization, remove or replace official marks, confusingly similar generated art, copyrighted images, player/celebrity likenesses, copied UI/art, and trademark-heavy keyword targeting. Prefer original generic artwork, neutral descriptors, country/region names, and factual editorial references.
- For independent reference/fan/companion apps, put a clear no-affiliation disclaimer in the first paragraph of the App Store description and add a concise App Review note explaining that the app uses original/generic artwork and is not affiliated with third parties.
- Keep reviewer notes brief and need-to-know: say what changed and how reviewers can verify it, but avoid unnecessary internal implementation details, legal speculation, or admissions beyond the facts.
- If any bundled binary asset changed after App Review feedback, increment the build number, archive/upload a new binary, wait for processing, and update `version.buildId`. Metadata-only fixes do not change app icons or bundled assets.
- In `appstore-submission.json`, include an `ipReview` block for IP-sensitive apps so validation warns when authorization, disclaimer, binary-asset, or official-mark checks are incomplete.

## App Icon Options

For iOS apps, help the creator choose an App Store-safe icon before the final release build:

1. Generate or sketch five visually distinct numbered app icon options before replacing the project icon. Use `assets/app-icon-options-recipe.json` as the default creative brief.
2. Make the five options different in style, not just color. Include a premium realistic direction, a minimal symbol direction, an environment/energy direction, a collectible/foil direction, and a friendly utility direction unless the user gives a stronger brief.
3. Keep icons symbol-only by default: no text, initials, acronyms, numbers, pseudo-text, labels, slogans, or watermarks. Icons with text usually look redundant, cluttered, and illegible at App Store and Home Screen sizes. Only include a real brand mark if the creator explicitly asks and owns the rights.
4. For IP-sensitive apps, keep all options original and generic. Do not include unlicensed official logos, crests, event marks, product shapes, trophy silhouettes, player or celebrity likenesses, or confusingly similar generated artwork.
5. Show the contact sheet to the creator and wait for their explicit choice. Do not upload a new build merely because options were generated.
6. After selection, generate the chosen direction as a standalone 1024x1024 PNG with no text, no watermark, and no baked rounded corners unless the creator explicitly asks otherwise.
7. Inspect the standalone icon at full size and small size, copy it into the app icon asset catalog, increment the build number, archive/upload a new build, and update the selected build in App Store Connect. App icon changes are binary changes.

This workflow mirrors the standalone personal skill `ios-app-icon-design`. If you change app icon rules here, update that skill as well so release work and standalone icon design stay in sync.

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

## Screenshot Recipe

Use this repeatable recipe when creating App Store screenshots for a new app:

1. Capture clean app UI screenshots for the target device size, usually `APP_IPHONE_67` first.
2. Copy `assets/screenshot-recipe.json` into the app repo, then replace each `source`, `output`, `headline`, `subheadline`, and `cta`.
3. Order screenshots by conversion value:
   - Screenshot 1: core value proposition and highest-intent ASO terms.
   - Screenshot 2: search, filter, browse, or most common user workflow.
   - Screenshot 3: strongest differentiator or paid feature, clearly labeled if Pro.
   - Screenshot 4: progress, organization, dashboard, groups, timeline, or status view.
   - Screenshot 5: depth feature such as history, archive, analytics, exports, or rankings.
   - Screenshot 6: paywall, trial, subscription value, or upgrade screen when monetized.
4. Use bright solid backgrounds, not busy patterns, so screenshots stand out in App Store search.
5. Keep text short: one sales-focused headline, one benefit line, and one CTA pill.
6. Include search-friendly wording naturally, but do not keyword-stuff or make claims the app cannot support.
7. For paid features, set `paid: true` so the renderer adds a Pro label.
8. Render a contact sheet or quick preview and check text legibility before upload.

The bundled recipe is intentionally generic and should be copied, not edited in place:

```bash
cp plugins/apple-app-store-connect/assets/screenshot-recipe.json appstore-screenshot-recipe.json
```

To render screenshots from raw captures:

```bash
python3 plugins/apple-app-store-connect/scripts/generate_screenshots.py \
  --config appstore-screenshot-recipe.json
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

When App Review rejects artwork or bundled assets, increment the build number, archive a new binary, upload the new build, and update `version.buildId`. Metadata-only changes are not enough for icon, asset catalog, bundled screenshot, or binary content changes.

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
- Include Privacy Policy and Terms of Use links in the App Store description, even if the app info localization already has a privacy URL.
- Include a subscription information section that explains the trial, weekly/monthly/yearly or relevant plan cadence, auto-renewal, cancellation timing, account billing, and account settings management.
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
