---
name: app-store-connect-release
description: Prepare, validate, upload, and submit Apple App Store Connect releases from Codex, including ASO/Apple Ads metadata, conversion-focused screenshots, build upload, review details, subscriptions, and custom product pages.
---

# App Store Connect Release

Use this skill when the user asks Codex to work on App Store Connect, TestFlight/App Store build uploads, App Store release metadata, screenshots, Apple Ads or ASO copy, subscriptions, in-app purchase review material, custom product pages, product page optimization, or App Review submissions.

## Operating Rules

- Never submit an app, upload screenshots, change pricing/availability, or mutate App Store Connect unless the user has explicitly confirmed the exact change.
- Run dry-run commands first. Use `--yes` only after the user confirms.
- Before applying App Store Connect changes or doing RevenueCat subscription setup, run access preflight. App Store Connect must pass a live read-only API probe, and RevenueCat must pass an MCP `list_projects` probe. If either fails, stop and prompt the user to re-authorize that service before continuing.
- Before finalizing subscription prices, check `pricingResearch`. If the last review is older than six months, pause pricing decisions and refresh current RevenueCat benchmark research plus Apple subscription/pricing guidance.
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
2. Run the local doctor and access preflight:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor
python3 plugins/apple-app-store-connect/scripts/asc_cli.py preflight-access
python3 plugins/apple-app-store-connect/scripts/asc_cli.py field-map
python3 plugins/apple-app-store-connect/scripts/asc_cli.py template
```

`preflight-access` verifies App Store Connect credentials with `GET /v1/apps?limit=1`. It also requires a RevenueCat MCP probe because RevenueCat OAuth/API-token state belongs to the RevenueCat plugin, not this local script. If the preflight output says `external_probe_required`, call the RevenueCat MCP tool `list_projects` with `limit=1`, then treat the result as the RevenueCat access proof. If the RevenueCat tool returns `authorization_error`, `access token has been revoked`, `401`, `403`, or `insufficient_scope`, tell the user RevenueCat must be re-authorized in Codex before subscription setup can continue.

3. If `doctor` reports missing credentials and the user has downloaded an API key, prepare local credentials without exposing the private key:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor --fix \
  --key-id <KEY_ID> \
  --issuer-id <ISSUER_ID> \
  --import-key ~/Downloads/AuthKey_<KEY_ID>.p8 \
  --write-env-file
```

Then source the returned env file and rerun `doctor`. For individual API keys, pass `--key-type individual` and omit `--issuer-id`.

If App Store Connect preflight fails, prompt the user to reconnect/replace the App Store Connect API key and rerun `doctor --fix ... --verify`. If RevenueCat preflight fails, prompt the user to reconnect the RevenueCat plugin/OAuth session or configure a valid RevenueCat API v2 secret key with write access for products, entitlements, offerings, and paywalls.

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

8. For subscription apps, plan pricing, the Free/Pro access split, onboarding, paywall timing, and review triggers before final metadata:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan-growth-strategy \
  --config appstore-submission.json
```

Use `assets/subscription-onboarding-review-template.json` as the default pattern for event-driven apps such as sports, tournament, or countdown trackers. It defaults to Free + Pro, with Free granting roughly 70-80% of useful app functionality and Pro reserving the remaining high-intent depth.

The default subscription launch pattern is a free-download app with weekly `$4.99`, monthly `$9.99`, and yearly `$29.99` Pro plans, each with a 14-day free trial for eligible first-time subscribers. Builders can override any cadence, price, or trial by recording the rationale in `customCadenceReason` or `customIntroOfferReason`.

If `plan-growth-strategy` reports stale pricing research, use web research before recommending final prices. Prefer current RevenueCat State of Subscription Apps benchmarks and Apple subscription/pricing docs, then update `pricingResearch.lastReviewedOn`, `nextReviewDue`, `sources`, and benchmark notes.

## Policy Source Checks

Before declaring a subscription app ready for upload or App Review, cross-check the current Apple documentation rather than relying on memory. At minimum, review these source categories and record the review date in the submission notes or local planning file:

- App Store Review Guidelines for in-app purchase, auto-renewable subscriptions, app completeness, metadata accuracy, privacy, and permission use.
- App Store Connect subscription help for subscription groups, product metadata, pricing, review screenshots, and first-time in-app purchase submission.
- StoreKit documentation for product metadata, purchase state, entitlement checks, transaction updates, and restore-purchase flows.
- Human Interface Guidelines for onboarding, permission timing, ratings/reviews, and avoiding disruptive prompts.

If Apple guidance has changed since the local template was last reviewed, update `assets/subscription-onboarding-review-template.json` first, then apply the app or App Store Connect changes.

## Metadata Guidance

Use Apple's product page recommendations:

- Name: 2-30 characters. Make the app name or brand clear. Add a category/use-case phrase only if it fits naturally.
- Subtitle: 30 characters maximum. Describe the core user outcome, not a vague slogan.
- Description: lead with the strongest benefit in the first sentence because it is visible before expansion. Use one concise paragraph followed by a short feature list. Avoid keyword stuffing and avoid specific prices.
- Subscription apps: append a `SUBSCRIPTION INFORMATION:` section to the App Store description before review. It must include the Pro/subscription value, trial and plan cadence summary, auto-renewal/cancellation disclosure, a functional Privacy Policy URL, and a functional Terms of Use/EULA URL. Apple can block review if the Terms of Use link is missing from metadata.
- Pricing: treat app download price and subscription prices as separate. Free-download subscription apps should use `$0` app pricing plus explicit subscription price point IDs for each subscription product. Do not put exact prices in App Store description copy unless the user explicitly asks and accepts localization/currency maintenance risk.
- Third-party/IP-sensitive apps: do not use unlicensed official logos, crests, trophies, event marks, player photos, broadcaster marks, or confusingly similar generated artwork in the app binary, app icon, screenshots, or metadata. If the app is an independent fan/reference app, put a clear no-affiliation disclaimer in the first paragraph of the description, repeat it in App Review notes, avoid trademark-heavy keywords, and use original generic artwork unless the user provides documentary authorization.
- Keywords: 100 characters maximum. Use relevant comma-separated terms with no spaces after commas. Avoid duplicates, plural variants when singular is present, category names, competitor names, trademarks, celebrity names, irrelevant terms, and objectionable terms.
- Promotional text: 170 characters maximum. Use for current launches, offers, or updates; do not use it for search ranking keywords.
- What's New: describe user-visible changes plainly. Format it as hyphen-prefixed bullet lines, one change per line, for example `-Added a Past tab for finished matches.` Avoid empty "bug fixes" copy when the release has meaningful improvements.
- Version history: before applying metadata for any update or resubmission, make sure every `versionLocalizations[]` entry has `whatsNew` copy that reads like App Store version-history/changelog text. Mention user-visible features, content/data refreshes, review-compliance art or metadata fixes when relevant, and meaningful bug fixes. Keep it concise, avoid internal implementation details, do not include exact subscription prices unless the creator explicitly accepts localization/currency maintenance risk, and rely on the CLI formatter to normalize flat paragraphs into hyphen-prefixed bullet lines before upload.
- Initial app or platform releases may legitimately have no editable What's New/version-history text in App Store Connect. Record this with `version.initialPlatformRelease: true`, `version.initialRelease: true`, or a matching `reviewSubmission`/localization flag so validation does not treat the empty field as a forgotten changelog.

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
- Do not upload plain raw app screenshots by themselves for App Store marketing sets. Composite them into a store screenshot with a big bold sales headline at the top, a short benefit line, a visible CTA pill, and enough colorful branded background to stand out in search results.
- Use bright solid or lightly patterned branded backgrounds that stand out in search results while preserving app-legibility. Avoid busy backgrounds that compete with the device capture.
- Make one benefit unmistakable per screenshot and align it with high-intent ASO/Apple Ads search terms.
- Keep overlay copy short enough to scan, with a sales-focused header and an explicit neutral CTA such as "Open the dashboard", "Track every kickoff", "Compare Pro plans", or "Pro feature".
- Do not put price, free, trial, discount, savings, or no-payment wording in public App Store screenshots or previews. Apple may treat references to free or discounted services as price references in screenshot metadata. Keep those details in the App Store description, in-app paywall, subscription product metadata, or private App Review material instead.
- Make the CTA pill and device capture large enough to read in App Store search/gallery views. Small device mockups and tiny CTAs underperform visually, especially on mobile App Store pages.
- Include at least one dark-mode screenshot if dark mode is a meaningful part of the experience.
- For subscription apps, make the base experience look useful in the first screenshots and show at least one Pro benefit as an upgrade. If subscriptions or paid features are shown, mark them clearly in the screenshot itself with labels such as "Pro feature", "Full set with Pro", or the subscription tier name.
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
   - Screenshot 6: paywall, subscription value, or upgrade screen when monetized, with neutral public screenshot copy.
4. Use bright solid or simple branded color backgrounds, not plain raw captures and not busy patterns, so screenshots stand out in App Store search.
5. Keep text short and mandatory: one big bold sales-focused headline, one benefit line, and one large CTA pill.
6. Include search-friendly wording naturally, but do not keyword-stuff or make claims the app cannot support.
7. For paid features, set `paid: true` and use a CTA or badge that names the tier, so the renderer adds a visible Pro label and the screenshot cannot be mistaken for base-tier functionality.
8. Render a contact sheet or quick preview and check headline size, CTA visibility, Pro labels, text legibility, device UI legibility, and absence of price/free/trial/discount/no-payment copy before upload. If the device UI is hard to inspect, increase `phoneWidthRatio` before upload.

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

For subscription App Review screenshots, verify App Store Connect's stored assets before declaring review readiness:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-subscription-status \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-subscription-review-screenshots \
  --config appstore-submission.json \
  --download-dir build/app-store/subscription-review-readback
```

Treat rejected or developer-action-needed subscription products/localizations, missing screenshots, incomplete processing, suspiciously small files, mostly black screenshots, macOS submissions that still have phone-sized portrait screenshots, or identical screenshots reused across different weekly/monthly/yearly plan expectations as blockers. For multi-plan paywalls, the weekly product screenshot should show weekly selected, monthly should show monthly selected, and yearly should show yearly selected unless `allowSharedReviewScreenshot` is deliberately set with a documented reason. For macOS submissions, set `subscriptionReviewScreenshots.requiredPlatform` to `MAC_OS` and use desktop-shaped Mac paywall screenshots.

## Build Uploads

The plugin supports Apple's Build Uploads API for `.ipa` and `.pkg` files and also includes a Transporter fallback.

For platform uploads:

- iOS, tvOS, and visionOS uploads use `.ipa`.
- macOS App Store uploads use `.pkg`.
- macOS App Store screenshots use the `APP_DESKTOP` display target.
- Always pass the target platform explicitly for Mac uploads, for example `--platform MAC_OS`, so the plugin validates the artifact and creates or patches the correct platform version.

When App Review rejects artwork or bundled assets, increment the build number, archive a new binary, upload the new build, and update `version.buildId`. Metadata-only changes are not enough for icon, asset catalog, bundled screenshot, or binary content changes.

For iOS, iPadOS, tvOS, and visionOS archive work, pass an explicit generic device destination instead of relying on Xcode's default destination. If Xcode defaults to a Mac "Designed for iPad/iPhone" destination, the upload workflow can become ambiguous. For iOS, use:

```bash
xcodebuild -project App.xcodeproj \
  -scheme App \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/App.xcarchive \
  archive
```

Before uploading an iOS `.ipa`, verify the binary artifact itself has the expected app bundle, platform, and compiled asset catalog:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-build-assets \
  --path build/App.xcarchive \
  --expect-bundle-id com.example.product \
  --expect-platform iPhoneOS

python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-build-assets \
  --path build/App.ipa \
  --expect-bundle-id com.example.product \
  --expect-platform iPhoneOS
```

For macOS archives, use `MacOSX` as the expected platform. The verifier reads the Mac bundle layout under `Contents/Info.plist` and `Contents/Resources/Assets.car`:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-build-assets \
  --path build/App-macOS.xcarchive \
  --expect-bundle-id com.example.product \
  --expect-platform MacOSX
```

Treat missing `Assets.car`, a bundle mismatch, or an unexpected platform as a hard upload blocker. Missing `Assets.car` can trigger `ITMS-90546: Missing asset catalog` after delivery.

Use this upload fallback order:

1. Try `upload-build-api` after a dry run and explicit confirmation.
2. If the API rejects the upload commit, checksum payload, or reservation, try `upload-build-transporter` when `iTMSTransporter` or `xcrun iTMSTransporter` is installed.
3. If Transporter is missing or fails locally, use Xcode's archive export upload fallback:

```bash
xcodebuild -exportArchive \
  -archivePath build/App.xcarchive \
  -exportPath build/app-store-upload \
  -exportOptionsPlist build/ExportOptionsUpload.plist \
  -allowProvisioningUpdates
```

For the Xcode fallback, the export options should use `destination=upload`, automatic signing when appropriate, and `signingCertificate=Apple Distribution`. Remove stale manual `provisioningProfiles` from the upload export options when automatic signing is intended.

After any upload succeeds, poll App Store Connect builds until the new build is processed and `VALID`, then set `version.buildId` to that build ID and run `apply-metadata --yes` after confirmation. "Ready for submission" means the App Store Connect version has the uploaded build selected, required metadata applied, screenshots uploaded, subscription prices/trials configured, subscription availability verified, subscription review screenshots uploaded and verified from App Store Connect readback, first-time IAP/subscription products selected with the app version when required, review details complete, and preflight checks passing. A local archive, GitHub push, or unselected uploaded build is not ready for submission.

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
  --build-number 42 \
  --expect-bundle-id com.example.product
```

Automatic-version upload dry run:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --auto-version \
  --project-dir . \
  --expect-bundle-id com.example.product
```

Confirmed API upload:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --version-string 1.0.0 \
  --build-number 42 \
  --expect-bundle-id com.example.product \
  --wait 1800 \
  --yes
```

Transporter fallback:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-transporter \
  --file build/App.ipa \
  --expect-bundle-id com.example.product
```

Use the build relationship in `version.buildId` after Apple finishes processing the build.

## iOS And macOS Sync

When the user wants an iOS app and a native macOS app to stay independent but experience-consistent, treat them as separate platform targets sharing a release contract:

- Do not change an iOS build or App Store version that the user says is already approved, under review, or otherwise frozen. Work on the `MAC_OS` platform version only unless the user explicitly asks to change iOS.
- Prefer Apple universal purchase when the Mac app is the desktop version of the same product. Apple platform versions under universal purchase use the same App Store Connect app record, Apple ID, SKU, and bundle ID, and in-app purchases can be shared across platform versions.
- If the Mac app must be a separate app record or legacy Mac configuration, create separate Apple product IDs for Mac, but map them to equivalent RevenueCat packages and the same entitlement/offering so user-facing access and paywall behavior stay aligned.
- Keep shared app logic, product IDs, entitlement identifiers, paywall copy, pricing, restore behavior, and App Review subscription evidence in a shared code/config layer where the app architecture allows it. Let Mac differ in desktop interaction details such as windows, sidebars, keyboard shortcuts, toolbar controls, and `APP_DESKTOP` screenshots.
- Record the decision in `crossPlatformRelease`: source/target platforms, `distributionModel`, whether the app uses the shared Apple app record, whether subscription product IDs are shared or mapped, and source links reviewed on the release date.

For RevenueCat with iOS + macOS:

- Use the same RevenueCat project for related iOS/macOS apps so entitlements are shared across apps in that project.
- Use one entitlement such as `pro` for equivalent premium access on both platforms.
- Use one offering/paywall such as `default` when pricing, trial, and paywall copy should stay consistent.
- Configure packages as the cross-platform grouping layer. A weekly package should contain the equivalent weekly product for each platform/app record, monthly the equivalent monthly product, and annual/yearly the equivalent annual product.
- Configure the SDK with the correct public SDK key only. Public keys are app-specific under a project; secret keys must never be embedded in client apps. For universal-purchase Mac apps, RevenueCat's macOS guidance is based on Apple universal purchases and may use the Apple app public key. Add a separate Mac RevenueCat app/public key only when the RevenueCat dashboard/support flow requires a distinct Mac configuration.
- If the app is still using native StoreKit while RevenueCat is used only for catalog/release coordination, record that explicitly in `revenueCatIntegration.appIntegration` and do not claim that the binary is RevenueCat-SDK-powered until the SDK is actually integrated and tested.

Ready-for-submission sequence for a Mac platform version:

1. Run `doctor`, App Store Connect preflight, and the RevenueCat `list_projects` probe.
2. Validate `crossPlatformRelease` and `revenueCatIntegration.crossPlatform`.
3. Upload the signed `.pkg` with `upload-build-api --platform MAC_OS` after dry run and explicit confirmation.
4. Wait for the build to process and become selectable.
5. Create or patch the `MAC_OS` App Store version, select the processed Mac build, and apply Mac-specific review notes.
6. Upload `APP_DESKTOP` screenshots.
7. Verify free download pricing, shared subscription pricing/trials, RevenueCat entitlement/offering/package mapping, and subscription review screenshots.
8. Stop before review submission unless the user explicitly confirms submitting the Mac version for review.

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

- Default to a flexible Free + Pro model unless the creator explicitly wants another setup. Free should grant roughly 70-80% of useful functionality so users get a real product, while Pro should unlock the remaining 20-30% of high-intent depth.
- Before creating or changing subscription products, entitlements, offerings, paywalls, or App Store Connect subscription pricing, verify both App Store Connect and RevenueCat access. Do not start the subscription setup while either token/key is revoked, unauthorized, missing, or under-scoped.
- Refresh subscription pricing research every six months. Treat weekly/monthly/yearly price anchors as benchmark-driven starting points, not permanent truths.
- Use weekly, monthly, and yearly as the default subscription cadence set. Keep `creatorCanOverrideCadences` true and use `customCadenceReason` when a builder intentionally removes or changes a cadence.
- Use weekly `$4.99`, monthly `$9.99`, and yearly `$29.99` as the default benchmark prices. Keep them flexible, but require a documented reason before changing the default pattern.
- Configure the default introductory offer as a 14-day free trial (`duration=TWO_WEEKS`, `numberOfPeriods=1`, `offerMode=FREE_TRIAL`) on every weekly, monthly, and yearly product unless the builder records `customIntroOfferReason`.
- Keep the app's core loop available on Free: basic browsing, search, personalization, status/detail views, and a sensible number of tracked items should not be blocked by default.
- Reserve Pro for enticing but non-essential depth: unlimited usage, advanced alerts, widgets/live activities, history, analytics, exports, premium personalization, themes, automations, or an ad-free experience when relevant.
- If an app needs a different split, keep the plugin flexible: adjust `freeProAccessModel.targetFreeAccessPercent`, `targetProAccessPercent`, pricing products, paywall triggers, and add `customAccessSplitReason`.
- Include localized subscription names and descriptions.
- Include App Review screenshots for the paywall or purchased feature. For multi-plan paywalls, verify each subscription product has a visible, processed, plan-specific screenshot; do not reuse a yearly-selected screenshot for weekly or monthly unless `allowSharedReviewScreenshot` is intentionally documented.
- Prefer one subscription group for most apps so users cannot accidentally hold multiple active subscriptions.
- Offer a clear monthly/default option and an annual best-value option when the discount is real. Weekly plans can be useful for short event apps, but do not make them the only obvious path.
- For event-driven, seasonal, or short-horizon apps, weekly can be a short-term access plan, monthly should anchor ongoing Pro value, and yearly should be positioned as best value for committed users. Use category/current benchmark research before choosing exact price points.
- Use a first-time introductory offer only after the onboarding flow has shown value; display it with StoreKit/paywall terms, not vague marketing copy.
- When a real StoreKit or RevenueCat trial is present, the default primary button text is `Start 14-day free trial`, with `✓ No payment due now` below the button. Never show this tagline for a product that does not have a real free-trial introductory offer.
- Use `list-subscription-price-points` to find price point IDs, then `configure-subscription-pricing` to dry-run and apply subscription prices/intro offers after explicit confirmation.
- Use `verify-subscription-status` before review submission so rejected/developer-action-needed subscription products or localizations are caught before calling the release ready.
- Use `verify-subscription-availability` and `configure-subscription-availability` because subscription prices/trials do not automatically make a product available in every sale territory.
- Use `upload-subscription-review-screenshots --replace-existing` only after the user confirms replacing the current product review screenshots; rerun `verify-subscription-review-screenshots` after upload.
- Include Privacy Policy and Terms of Use links in the App Store description, even if the app info localization already has a privacy URL.
- Include a subscription information section that explains the trial, weekly/monthly/yearly or relevant plan cadence, auto-renewal, cancellation timing, account billing, and account settings management.
- For first-time IAPs/subscriptions, upload and select a new processed build, then select the products with the app version in App Store Connect's website UI when Apple requires it. If direct `subscriptionSubmissions` calls fail with `FIRST_SUBSCRIPTION_MUST_BE_SUBMITTED_ON_VERSION`, treat it as a manual website-selection requirement, not a credential failure. Record the selected build and UI confirmation in `firstTimeSubscriptionSubmission` before calling the app ready for review.
- In screenshots and description, avoid presenting paid-only features as free.
- App Review notes should explain how reviewers can access sandbox purchase paths or pre-unlocked demos.

Subscription pricing commands:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan-growth-strategy \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py list-subscription-price-points \
  --subscription-id subscription-id \
  --territory USA

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-subscription-pricing \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-subscription-pricing \
  --config appstore-submission.json --yes

python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-subscription-availability \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-subscription-availability \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-subscription-availability \
  --config appstore-submission.json --yes

python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-subscription-review-screenshots \
  --config appstore-submission.json \
  --replace-existing \
  --wait 300

python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-subscription-review-screenshots \
  --config appstore-submission.json \
  --replace-existing \
  --wait 300 \
  --yes
```

## Onboarding And Review Prompts

For subscription apps, especially event-driven, seasonal, or countdown-style trackers:

- Treat onboarding, paywall, subscriptions, and review prompts as a binary release gate before archiving. Inspect the app code, not only App Store Connect metadata, and verify the app has a real first-run onboarding path, a compliant paywall, product/entitlement IDs that match App Store Connect or RevenueCat, restore purchases, Privacy Policy and Terms links, and a delayed review-prompt policy.
- If any of those pieces are missing, implement them before uploading a new release build. Do not claim the app is ready merely because metadata and screenshots are complete.
- Keep onboarding value-first and short, usually 3-5 screens: core outcome, personalization or local context, permission education, then optional Pro. Location and notification permission prompts should appear only after the user sees why the permission helps.
- Make the paywall optional for freemium apps. It must have a visible close or continue-free path unless the app is intentionally paid-only and the App Store description/review notes make that clear.
- Keep the Free tier genuinely useful, normally 70-80% of the core loop. Gate high-intent depth such as unlimited saved items, full archives/readers, advanced alerts, widgets, premium personalization, exports, or future premium extras.
- Use live StoreKit or RevenueCat product metadata for display prices whenever possible. Fallback prices are acceptable only for previews/development and must not be the evidence used to declare App Store readiness.
- Before build upload, cross-check every product ID in code against App Store Connect/RevenueCat products. Product IDs, subscription group, localizations, pricing, availability, review screenshot, and review notes must be ready for first subscription review.
- Required paywall elements: product name, billing duration, price, trial duration and post-trial price when a real trial exists, primary CTA, `✓ No payment due now` reassurance when the trial is real, auto-renewal disclosure, cancellation at least 24 hours before renewal, renewal charge within 24 hours before renewal, restore purchases, Privacy Policy link, Terms of Use/EULA link, and clear purchase/loading/error states.
- Do not say "No payment due now", "free trial", or similar unless StoreKit/RevenueCat confirms the selected product has a real introductory offer.
- Let users choose favorite teams, tournaments, groups, or notification preferences before the paywall.
- Show personalized value before asking for payment: a tailored schedule, match center, countdown, reminders, standings, or tracked items.
- Let users continue for free after onboarding whenever sensible. The first paywall should appear after personalized value, after a generous free limit, or when the user taps a clearly labeled Pro feature.
- Ask notification permission only after explaining what the alert does.
- Show Restore Purchases plus Terms of Use and Privacy Policy links wherever the paywall appears.
- Do not call StoreKit `requestReview` on launch, during onboarding, on a paywall, after a purchase prompt, after cancellation, after an error, after an offline failure, or as a direct result of tapping a "Rate us" button.
- Use review prompts only after positive completed outcomes, such as following a first team/topic, opening a personalized match/event hub, reading a useful daily briefing, completing onboarding, or receiving a useful reminder. Add local gates before calling the system prompt: onboarding complete, at least 24 hours since first launch, at least 3 launches, at least 3 positive engagement events, no active modal/paywall/error, and a local cooldown of about 90 days.
- Use an App Store `?action=write-review` URL for explicit user-initiated review actions in settings/help.

## Manual Or Limited Areas

Prepare these for the user, but do not claim full API automation unless Apple adds public endpoints:

- Paid Apps Agreement, tax, and banking setup.
- App Privacy nutrition labels.
- Some export compliance documents and account/legal forms.
- Regulated claims for medical, financial, gambling, kids, legal, or safety-sensitive apps.

## MCP Tools

When the plugin MCP server is installed, prefer these tools over shell calls:

- `asc_doctor`
- `asc_preflight_access`
- `asc_credential_setup`
- `asc_field_map`
- `asc_validate_submission_config`
- `asc_plan_submission_config`
- `asc_plan_version`
- `asc_apply_version`
- `asc_apply_metadata`
- `asc_configure_free_download`
- `asc_plan_growth_strategy`
- `asc_configure_subscription_pricing`
- `asc_configure_subscription_availability`
- `asc_verify_subscription_availability`
- `asc_list_subscription_price_points`
- `asc_list_apps`
- `asc_upload_build_api`
- `asc_generate_screenshots`
- `asc_upload_subscription_review_screenshots`
- `asc_verify_subscription_review_screenshots`

The same confirmation rules apply to MCP tools: pass `confirm: true` only after the user approves the action.
