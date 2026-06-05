# Apple App Store Connect Codex Plugin

An open source Codex plugin for preparing and shipping Apple App Store Connect releases. It helps Codex draft App Store metadata, validate submission fields, render conversion-focused screenshots, upload builds, upload screenshots, fill version/review details, and prepare review submissions using Apple's public App Store Connect APIs and delivery tooling.

The plugin is intentionally conservative: every production mutation starts as a dry run, and review submission/build upload actions require explicit confirmation.

## Install

```bash
codex plugin marketplace add https://github.com/mauriciorubio2/apple-app-store-connect-codex-plugin.git
codex plugin add apple-app-store-connect@apple-app-store-connect-codex-plugin
```

## What It Can Do

- Draft ASO and Apple Ads-aware app name, subtitle, description, keywords, promotional text, and what's-new copy.
- Normalize App Store What's New/version-history copy into hyphen-prefixed bullet lines before applying version localizations.
- Run a release preflight that verifies App Store Connect API access and requires a RevenueCat MCP probe before subscription automation begins.
- Validate key Apple metadata limits, including 30-character name/subtitle, 100-character keywords, 170-character promotional text, and screenshot count rules.
- Generate App Store screenshot composites from raw UI captures and clearly label paid/subscription features.
- Generate brighter, conversion-focused screenshot composites with salesy ASO/Apple Ads-aware headers, large CTA pills, large device captures, and paid-feature badges.
- Block price, free, trial, discount, savings, and no-payment wording in public App Store screenshot overlay copy before rendering.
- Guide iOS app icon selection with five distinct, App Store-safe design options before replacing bundled icon assets.
- Upload screenshots through `appScreenshotSets` and `appScreenshots` asset reservations.
- Set an app to $0/free download and make it available in all App Store territories after an explicit dry-run/approval step.
- Plan and apply subscription product prices and introductory offers when App Store Connect price point IDs are supplied.
- Detect first-time IAP/subscription products left in `READY_TO_SUBMIT` and require selected-build plus App Store Connect website selection evidence before review readiness.
- Verify subscription App Review screenshots from App Store Connect, including processed state, non-black pixel checks, and distinct plan-specific screenshots for weekly/monthly/yearly products.
- Check whether subscription pricing research is stale and prompt Codex to refresh weekly/monthly/yearly benchmarks every six months.
- Default subscription launches to weekly `$4.99`, monthly `$9.99`, and yearly `$29.99` Pro plans, each with a 14-day free trial unless a builder records an override.
- Default subscription apps to a flexible Free + Pro model where Free grants roughly 70-80% of useful functionality and Pro unlocks high-intent depth.
- Validate value-first onboarding, paywall timing, and StoreKit review prompt triggers for subscription apps.
- Plan and apply App Store versions and build numbers from Xcode project settings, Info.plists, git history, or a Codex iteration count.
- Verify iOS `.xcarchive` and `.ipa` artifacts contain the compiled asset catalog (`Assets.car`) before upload.
- Upload `.ipa` or `.pkg` builds with Apple's Build Uploads API, with platform validation, Transporter and Xcode `destination=upload` fallbacks, plus optional automatic versioning.
- Prepare native macOS platform versions with `MAC_OS`, `.pkg` artifacts, and `APP_DESKTOP` screenshots.
- Validate iOS/macOS universal-purchase setup, shared Apple subscription products, and RevenueCat same-project entitlement/offering/package mapping so platform apps stay independent but user-facing pricing and access remain consistent.
- Update App Store version metadata, version localizations, review contact/demo details, selected build relationship, and age rating declarations when resource IDs are supplied.
- Warn when version localizations are missing or use flat `whatsNew` copy so App Store version history/changelog text is not forgotten.
- Prepare subscription/IAP localization, review screenshot, and App Store description legal-link checklists.
- Prepare IP-sensitive releases and resubmissions with a generic third-party IP checklist, optional `ipReview` validation warnings, no-affiliation disclaimer guidance, and new-binary reminders for asset changes.
- Create dry-run plans so a human can approve exactly what will change.

## Apple Documentation Used

The workflow is based on Apple's current App Store Connect API, App Store Connect Help, and product page guidance:

- [App Store Connect API](https://developer.apple.com/documentation/appstoreconnectapi)
- [Generating tokens for API requests](https://developer.apple.com/documentation/appstoreconnectapi/generating_tokens_for_api_requests)
- [Managing assets with asset catalogs](https://developer.apple.com/documentation/xcode/managing-assets-with-asset-catalogs)
- [Uploading assets to App Store Connect](https://developer.apple.com/documentation/appstoreconnectapi/uploading_assets_to_app_store_connect)
- [Build uploads](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-builduploads)
- [Upload builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
- [Platform version information](https://developer.apple.com/help/app-store-connect/reference/platform-version-information/)
- [Universal purchase](https://developer.apple.com/support/universal-purchase/)
- [Configure In-App Purchases](https://developer.apple.com/help/app-store-connect/configure-in-app-purchase-settings/overview-for-configuring-in-app-purchases/)
- [In-App Purchase information](https://developer.apple.com/help/app-store-connect/reference/in-app-purchase-information)
- [Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/)
- [Creating your product page](https://developer.apple.com/app-store/product-page/)
- [Custom product pages](https://developer.apple.com/app-store/custom-product-pages/)
- [Apple Ads custom product pages API](https://developer.apple.com/documentation/apple_search_ads/custom_product_pages)
- [Auto-renewable subscriptions](https://developer.apple.com/app-store/subscriptions/)
- [Manage pricing for auto-renewable subscriptions](https://developer.apple.com/help/app-store-connect/manage-subscriptions/manage-pricing-for-auto-renewable-subscriptions/)
- [Set up introductory offers for auto-renewable subscriptions](https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-introductory-offers-for-auto-renewable-subscriptions/)
- [Product page optimization](https://developer.apple.com/app-store/product-page-optimization/)
- [Requesting App Store reviews](https://developer.apple.com/documentation/storekit/requesting_app_store_reviews/)
- [RevenueCat MCP Server](https://www.revenuecat.com/docs/tools/mcp)
- [RevenueCat MCP setup and authentication](https://www.revenuecat.com/docs/tools/mcp/setup)
- [RevenueCat API keys and OAuth tokens](https://www.revenuecat.com/docs/projects/authentication)
- [RevenueCat macOS / Catalyst](https://www.revenuecat.com/docs/getting-started/installation/macos)
- [RevenueCat entitlements](https://www.revenuecat.com/docs/getting-started/entitlements)
- [RevenueCat offerings and packages](https://www.revenuecat.com/docs/offerings/overview)
- [RevenueCat State of Subscription Apps 2025](https://www.revenuecat.com/state-of-subscription-apps-2025/)
- [RevenueCat subscription trends and benchmarks for 2026](https://www.revenuecat.com/blog/growth/subscription-app-trends-benchmarks-2026/)

## Credentials

Create an App Store Connect API key in App Store Connect, download the `.p8` private key once, and keep it outside the repository.

The helper below copies the downloaded key into `~/.appstoreconnect/private_keys/`, locks file permissions, and can write a local env file that is safe to source but must never be committed:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py credential-setup \
  --key-id ABC123DEFG \
  --issuer-id 00000000-0000-0000-0000-000000000000 \
  --import-key ~/Downloads/AuthKey_ABC123DEFG.p8 \
  --write-env-file

source ~/.appstoreconnect/credentials.env
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor
```

`doctor --fix` is an alias for the same setup flow:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor --fix \
  --key-id ABC123DEFG \
  --issuer-id 00000000-0000-0000-0000-000000000000 \
  --import-key ~/Downloads/AuthKey_ABC123DEFG.p8 \
  --write-env-file
```

To only print shell exports without writing a file, omit `--write-env-file`.

```bash
export ASC_KEY_ID="ABC123DEFG"
export ASC_ISSUER_ID="00000000-0000-0000-0000-000000000000"
export ASC_KEY_PATH="$HOME/.appstoreconnect/private_keys/AuthKey_ABC123DEFG.p8"
export ASC_KEY_TYPE="team"
```

For individual keys:

```bash
export ASC_KEY_ID="ABC123DEFG"
export ASC_KEY_PATH="$HOME/.appstoreconnect/private_keys/AuthKey_ABC123DEFG.p8"
export ASC_KEY_TYPE="individual"
```

## CLI Examples

Run local checks:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py doctor
```

Before App Store Connect or RevenueCat subscription automation, verify access:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py preflight-access
```

This verifies App Store Connect with a read-only `/v1/apps` API request. RevenueCat OAuth/API-token state lives inside the RevenueCat MCP server, so Codex must also call the RevenueCat MCP `list_projects` probe with `limit=1`. If either check fails or reports a revoked/unauthorized token, the plugin tells Codex to stop and prompt you to re-authorize that service before continuing.

Start a submission config:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py template > appstore-submission.json
```

Validate and plan:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py validate --config appstore-submission.json
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan --config appstore-submission.json
```

For apps with auto-renewable subscriptions, validation expects the App Store description to include a `SUBSCRIPTION INFORMATION:` section with trial/plan context, auto-renewal and cancellation language, plus functional Privacy Policy and Terms of Use/EULA links. This catches the common App Review blocker where Terms of Use is present in-app but missing from App Store metadata.

For an app's first IAP or subscription review, Apple may require the products to be selected with the new app version inside `appstoreconnect.apple.com`. If the products remain `READY_TO_SUBMIT`, upload and select a processed build first, then select the products in the app version's In-App Purchases and Subscriptions section. Apple's public `subscriptionSubmissions` API can reject this first-time case with `FIRST_SUBSCRIPTION_MUST_BE_SUBMITTED_ON_VERSION`, so the plugin validates local evidence fields instead of treating the API failure as a credential issue.

For subscription App Review screenshots, use one clear image per plan when the paywall has weekly, monthly, and yearly choices. The weekly product screenshot should show weekly selected, monthly should show monthly selected, and yearly should show yearly selected unless `allowSharedReviewScreenshot` is deliberately set with a documented reason. Before calling a submission ready, run:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-subscription-review-screenshots \
  --config appstore-submission.json \
  --download-dir build/app-store/subscription-review-readback
```

This readback checks App Store Connect's stored assets for missing images, incomplete processing, suspiciously small files, mostly black screenshots, and identical screenshots reused across different selected-plan expectations.

Apply metadata after approval:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py apply-metadata --config appstore-submission.json --yes
```

Plan and apply free download pricing and all-country availability:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-free-download \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-free-download \
  --config appstore-submission.json \
  --yes
```

Plan subscription pricing, Free/Pro access, onboarding, paywall timing, and review prompt triggers:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan-growth-strategy \
  --config appstore-submission.json
```

List App Store Connect subscription price points for a product:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py list-subscription-price-points \
  --subscription-id subscription-id \
  --territory USA
```

Apply subscription prices and introductory offers after filling price point IDs:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-subscription-pricing \
  --config appstore-submission.json

python3 plugins/apple-app-store-connect/scripts/asc_cli.py configure-subscription-pricing \
  --config appstore-submission.json \
  --yes
```

`configure-free-download` handles only the app download price. `configure-subscription-pricing` handles subscription product prices and introductory offers. They are intentionally separate because App Store Connect models them separately.

`plan-growth-strategy` also checks `pricingResearch`. If `lastReviewedOn` is missing or older than the configured six-month interval, Codex should refresh current pricing research before finalizing weekly, monthly, or yearly plan prices. The default cadence set is weekly + monthly + yearly, with benchmark anchors as starting points rather than universal truth: weekly around `$4.99` for short-term/event intent, monthly around `$9.99` as the main comparison plan, and yearly around `$29.99` as a clear best-value anchor when the discount is real.

Builders can change the cadence setup. Keep `creatorCanOverrideCadences: true`, adjust `defaultCadences`/`products`, and add `customCadenceReason` when an app should omit weekly, monthly, or yearly, or use a different plan mix.

Plan the next App Store version and build number:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py plan-version \
  --project-dir /path/to/MyApp \
  --release-level auto \
  --iteration-count 7
```

Apply the recommended version locally after approval:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py apply-version \
  --project-dir /path/to/MyApp \
  --config appstore-submission.json \
  --release-level auto \
  --iteration-count 7 \
  --yes
```

Before uploading an iOS binary, archive with an explicit generic iOS destination and verify the compiled asset catalog is inside the final app. Do not rely on Xcode's default destination when multiple destinations are available.

```bash
xcodebuild -project MyApp.xcodeproj \
  -scheme MyApp \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/MyApp.xcarchive \
  archive

python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-build-assets \
  --path build/MyApp.xcarchive \
  --expect-bundle-id com.example.product \
  --expect-platform iPhoneOS
```

After exporting the `.ipa`, run the same check on the file that will be uploaded. A missing `Assets.car`, bundle mismatch, or wrong platform is a release blocker because it can produce App Store processing failures such as `ITMS-90546: Missing asset catalog`.

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py verify-build-assets \
  --path build/MyApp.ipa \
  --expect-bundle-id com.example.product \
  --expect-platform iPhoneOS
```

Upload a build with the API:

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

Upload a native macOS App Store build with the API:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.pkg \
  --version-string 1.0.0 \
  --build-number 42 \
  --platform MAC_OS \
  --wait 1800 \
  --yes
```

Upload a build and let the plugin infer missing version/build values:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --auto-version \
  --project-dir /path/to/MyApp \
  --iteration-count 7 \
  --expect-bundle-id com.example.product \
  --wait 1800 \
  --yes
```

`upload-build-api` and `upload-build-transporter` automatically run the iOS `.ipa` asset-catalog preflight unless `--skip-binary-asset-check` is deliberately supplied after a separate verification has already passed.

## Versioning Behavior

Apple separates the user-facing App Store version from the build iteration. `CFBundleShortVersionString` should match the App Store version and use three period-separated integers such as `1.2.3`. `CFBundleVersion` identifies the uploaded build and uses one to three period-separated integers.

The plugin can infer the next values from Xcode `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, literal `Info.plist` values, git history, and an optional `--iteration-count`. The default `auto` release level uses git messages conservatively: breaking-change markers become major bumps, conventional `feat:` commits become minor bumps, and other release builds become patch bumps. Build numbers always increment, using the provided iteration count when available.

## Subscription Access, Onboarding, And Reviews

The bundled `subscription-onboarding-review-template.json` captures the release pattern used for event-driven subscription apps: free download, one subscription group, weekly/monthly/yearly Pro plans, RevenueCat project/offering/entitlement coordination, a 14-day free trial for eligible first-time subscribers, a flexible Free + Pro access model, value-first onboarding, visible restore/terms/privacy links on the paywall, and StoreKit review prompts only after successful user outcomes.

Run access preflight first. `accessPreflight` requires a live App Store Connect probe plus a RevenueCat MCP `list_projects` probe before Codex applies metadata, pricing, products, offerings, screenshots, build uploads, or review submission changes. On failure, Codex should prompt for App Store Connect API-key setup or RevenueCat OAuth/API-key reauthorization, then retry the probe.

By default, `freeProAccessModel` gives users a complete Free product experience with roughly 70-80% of useful functionality available before purchase. Pro should reserve the remaining high-intent 20-30%: unlimited usage, advanced alerts, widgets or live activities, deeper history/analytics, exports, premium personalization, themes, automations, or other power-user depth. The core loop should stay usable on Free so users get a real taste of the app.

Creators can still change the setup. Set `creatorCanOverride` to true, adjust `targetFreeAccessPercent`/`targetProAccessPercent`, and add `customAccessSplitReason` when a different access split or pricing model is intentional.

Pricing research belongs beside the subscription setup. Keep `pricingResearch.lastReviewedOn`, `reviewIntervalMonths`, `nextReviewDue`, and `sources` current. The plugin defaults to a six-month review cycle because plan-duration benchmarks, competitive price anchors, category willingness to pay, and conversion patterns change regularly. The default price anchors are weekly `$4.99`, monthly `$9.99`, and yearly `$29.99`; add `customPriceReason`, `customCadenceReason`, or `customIntroOfferReason` when a different launch setup is intentional.

For iOS + macOS releases, record `crossPlatformRelease` and `revenueCatIntegration.crossPlatform`. When the Mac app is a universal-purchase platform version of the same product, use the same App Store app record, bundle ID, subscription group/products, RevenueCat project, entitlement, offering, and package identifiers. If the Mac app is separate, provide a platform product mapping and attach equivalent products to the same RevenueCat packages/entitlement. Use `preserveCurrentPrice` and `preserveCurrentIntroductoryOffer` when a platform release should intentionally reuse existing prices and trials without posting new pricing changes.

Default paywalls should use `Start 14-day free trial` as the primary CTA and show `✓ No payment due now` below the button only when StoreKit or RevenueCat confirms the selected product has a real free-trial introductory offer.

First-time IAP/subscription products need extra release evidence when they are still `READY_TO_SUBMIT`. Upload and select the processed build, select the products with the app version in App Store Connect's website UI when Apple requires it, and record the confirmation in `firstTimeSubscriptionSubmission`. Do not call the release ready while products are still waiting for first review without that selected-version evidence.

Subscription review screenshots are also release evidence. Record each product's `expectedSelectedPlan`, screenshot ID, checksum, and processed state. The default is `allowSharedReviewScreenshot: false`, so duplicate weekly/monthly/yearly screenshots are treated as blockers unless a shared screenshot is intentional and documented.

For review prompts, the plugin validates that `requestReview` is not tied to launch, onboarding, paywall, purchase, cancellation, error, permission, or direct "rate us" button contexts. Use a manual App Store write-review link for explicit user-initiated review actions.

Generate screenshots:

```bash
python3 -m pip install pillow
cp plugins/apple-app-store-connect/assets/screenshot-recipe.json appstore-screenshot-recipe.json
python3 plugins/apple-app-store-connect/scripts/generate_screenshots.py \
  --config appstore-screenshot-recipe.json
```

Screenshot copy should lead with one high-intent user benefit per image, include search-friendly terms naturally, use bright solid or lightly patterned branded backgrounds that stand out in App Store search results, and clearly label Pro or paid features. Keep the first three screenshots focused on conversion: the core value proposition, a common search/action workflow, and the strongest differentiator. Make the CTA pill and device capture large enough to inspect on mobile App Store pages. Public App Store screenshots should not include prices, `free`, trial, discount, savings, or no-payment language; keep those details in the app description, in-app paywall, subscription product metadata, or private App Review material. The bundled `screenshot-recipe.json` gives a six-shot App Store sequence: core value, search/action workflow, strongest differentiator, progress/status view, deeper archive/analytics, and Pro upgrade value with neutral screenshot CTAs.

## App Icon Options

When preparing an iOS app release, use `plugins/apple-app-store-connect/assets/app-icon-options-recipe.json` to produce five numbered icon directions for the creator to choose from before changing the project icon. The options should be meaningfully different in style, symbol-only by default, and avoid text, initials, numbers, pseudo-text, labels, slogans, watermarks, unlicensed third-party IP, official marks, confusingly similar product shapes, player or celebrity likenesses, and copied artwork.

After the creator picks an option, generate it as a standalone 1024x1024 PNG, inspect it at small sizes, copy it into the app icon asset catalog, increment the build number, and upload/select a fresh build because icon changes are bundled binary changes.

The app icon release workflow mirrors the standalone personal Codex skill `ios-app-icon-design`; keep the skill and this plugin recipe aligned when changing icon rules.

## Privacy And Security

This plugin runs locally. It does not send credentials to any third-party service. API requests go to Apple's App Store Connect API or Apple's upload URLs returned by upload reservations.

Do not commit `.p8` keys, JWTs, app binaries, unreleased screenshots, demo account passwords, or private release metadata. The `.gitignore` blocks the most common sensitive file types, but developers remain responsible for reviewing commits.

## Known Boundaries

Some App Store Connect areas still require manual work or account-specific review:

- Paid Apps Agreement, tax, and banking setup.
- App Privacy nutrition labels.
- Some export compliance documents and regulated-app disclosures.
- Final legal, medical, financial, kids, gambling, or safety-sensitive claims.

The plugin can prepare checklists and draft copy for those areas, but it will not pretend to automate unsupported public API fields.

## Development

```bash
python3 -m unittest discover -s tests -v
# In Codex development sessions, also run the bundled plugin validator:
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/apple-app-store-connect
```

## License

MIT
