# Changelog

All notable changes to this project are documented here.

## [1.14.6] - 2026-06-06

- Added `.pkg` support to build-asset verification by expanding macOS packages and inspecting the embedded `.app` bundle for `Contents/Resources/Assets.car`.
- Added automatic macOS `.pkg` asset-catalog preflight to API and Transporter upload dry-runs/uploads so package deliveries with missing compiled asset catalogs are blocked locally.
- Accepted common platform aliases such as `MAC_OS` and `MacOS` by normalizing them to the App Store bundle platform marker `MacOSX`.

## [1.14.5] - 2026-06-05

- Added `verify-subscription-status` to read subscription product and localization states from App Store Connect.
- Flagged `DEVELOPER_ACTION_NEEDED`, `REJECTED`, and missing subscription localization metadata as release blockers, with `READY_TO_SUBMIT` surfaced as a first-review warning.
- Added MCP, docs, and tests so rejected subscription localizations are caught alongside screenshot and availability checks.

## [1.14.4] - 2026-06-05

- Added subscription availability validation, live readback, dry-run planning, and `configure-subscription-availability` support so product sale territories are verified separately from prices and introductory offers.
- Added `upload-subscription-review-screenshots` for subscription App Review screenshot reservations, uploads, replacement, commits, and processing polls.
- Added macOS desktop-shape checks for subscription App Review screenshots so `MAC_OS` submissions fail when App Store Connect still has phone-sized portrait paywall evidence.

## [1.14.3] - 2026-06-05

- Accepted RevenueCat v2 `items` project-list payloads and Codex-rendered text project lists as valid preflight proof after OAuth reauthorization.

## [1.14.2] - 2026-06-05

- Allowed explicitly marked initial app or platform releases to omit `versionLocalizations[].whatsNew` without a validation warning, matching App Store Connect first-platform behavior.
- Fixed build-asset verification for macOS archive bundles by reading `Contents/Info.plist` and `Contents/Resources/Assets.car`.
- Added validation coverage and release guidance for `version.initialPlatformRelease`.

## [1.14.1] - 2026-06-05

- Added What's New/version-history normalization so flat paragraphs are sent to App Store Connect as hyphen-prefixed bullet lines, one user-visible change per line.
- Updated validation, templates, release guidance, and tests to prefer bullet-formatted `versionLocalizations[].whatsNew` copy.

## [1.14.0] - 2026-06-05

- Added `verify-build-assets` to inspect `.ipa`, `.xcarchive`, and `.app` artifacts for `Assets.car`, bundle ID, and platform before upload.
- Added automatic iOS `.ipa` asset-catalog preflight to API and Transporter upload commands so missing compiled asset catalogs are blocked locally instead of reaching App Store processing.
- Updated release guidance to archive iOS builds with `generic/platform=iOS`, verify the archive and exported IPA, and treat `ITMS-90546`-style missing asset catalog findings as hard upload blockers.

## [1.13.1] - 2026-06-05

- Added macOS platform release guardrails for `.pkg` uploads, `APP_DESKTOP` screenshots, and explicit `MAC_OS` platform handling.
- Added iOS/macOS universal-purchase validation for shared Apple app records, bundle IDs, subscription product catalogs, and separate-platform product mappings.
- Added RevenueCat cross-platform checks for same project, shared entitlement, shared offering/paywall, equivalent packages, and public SDK key documentation.
- Added `preserveCurrentPrice` and `preserveCurrentIntroductoryOffer` no-op handling so existing iOS subscription prices/trials can be intentionally reused for macOS releases.
- Updated release templates, field map, skill guidance, and README for macOS uploads and consistent iOS/macOS subscription/paywall setup.

## [1.13.0] - 2026-06-05

- Added public App Store screenshot copy validation that blocks price, free, trial, discount, savings, and no-payment wording before rendered screenshots are produced.
- Updated screenshot recipe defaults to use neutral CTA copy while preserving visible Pro/paid-feature labels.
- Clarified release guidance so trial/no-payment wording stays in the in-app paywall, App Store description, subscription metadata, or private App Review material, not public screenshot overlays.

## [1.12.0] - 2026-06-05

- Added validation warnings for missing `versionLocalizations[].whatsNew` so App Store version history/changelog copy is not forgotten during release prep.
- Enlarged default App Store screenshot composition with bigger device captures, larger CTA pills, and guidance to verify UI legibility before upload.
- Expanded release skill guidance for user-visible What's New copy and screenshot sizing best practices.

## [1.11.0] - 2026-06-04

- Added subscription App Review screenshot verification for missing, unprocessed, suspiciously small, mostly black, or duplicate screenshots.
- Added plan-specific screenshot checks so weekly, monthly, and yearly products should each show the matching selected plan unless a shared screenshot is intentionally documented.
- Added CLI and MCP tooling for live App Store Connect screenshot readback plus local validation/template fields for screenshot IDs, checksums, expected selected plans, and processed state.

## [1.10.0] - 2026-06-04

- Added a release-readiness gate for first-time IAP and subscription products that are still in `READY_TO_SUBMIT`.
- Documented Apple's website-only first-time product selection requirement and the `FIRST_SUBSCRIPTION_MUST_BE_SUBMITTED_ON_VERSION` API rejection.
- Added template evidence fields for recording the uploaded selected build and App Store Connect product-selection confirmation before a submission is declared ready for review.

## [1.9.1] - 2026-06-03

- Removed app-specific release-history wording so plugin documentation and changelog entries stay generic and reusable for any app category.
- Kept the subscription, paywall, screenshot, upload-fallback, and readiness guidance unchanged while making examples category-neutral.

## [1.9.0] - 2026-06-02

- Added default launch pricing: weekly `$4.99`, monthly `$9.99`, and yearly `$29.99` Pro plans, each with a 14-day free trial unless builders record an intentional override.
- Added paywall defaults and validation for `Start 14-day free trial` plus `✓ No payment due now`, only when StoreKit or RevenueCat confirms a real introductory offer.
- Strengthened release readiness guidance so "ready for submission" means the build is uploaded, processed, selected, and paired with complete metadata, screenshots, pricing, subscriptions, and review details.
- Added Xcode `destination=upload` as a documented fallback when the Build Uploads API or local Transporter path fails.
- Improved screenshot recipes and rendering so App Store screenshots require big headlines, visible CTAs, colorful branded backgrounds, Pro labels, and optional CTA notes.

## [1.8.0] - 2026-06-01

- Made weekly, monthly, and yearly the default subscription cadence set across templates and validation.
- Added `defaultCadences` and `creatorCanOverrideCadences` so builders can intentionally remove or change plan durations with `customCadenceReason`.
- Updated the generic submission template to include a weekly product and RevenueCat weekly package by default.

## [1.7.0] - 2026-06-01

- Added six-month subscription pricing research freshness checks so Codex warns when weekly/monthly/yearly pricing benchmarks need to be refreshed.
- Added pricing research metadata and benchmark anchors for weekly, monthly, and yearly subscription plans, including event-driven weekly guidance and annual best-value positioning.
- Added cadence validation for weekly-primary plans, missing monthly anchors, annual best-value labels, and weak annual discounts when benchmark/customer prices are available.

## [1.6.0] - 2026-06-01

- Added `preflight-access` and MCP `asc_preflight_access` so Codex checks App Store Connect API access and RevenueCat MCP access before release/subscription automation.
- Added explicit reauthorization prompts for revoked, unauthorized, missing, or under-scoped App Store Connect and RevenueCat credentials.
- Added `accessPreflight` and `revenueCatIntegration` template blocks so subscription submissions start with RevenueCat project/offering/entitlement coordination and token-readiness checks.

## [1.5.0] - 2026-06-01

- Added a flexible `freeProAccessModel` default for subscription apps, targeting 70-80% useful Free functionality and 20-30% high-intent Pro depth.
- Added validation and growth-plan output for Free/Pro access split, creator override rationale, core-loop gating, and paywall trigger timing.
- Updated subscription/onboarding templates, release guidance, field map, and README to apply a generic Free + Pro subscription pattern by default.

## [1.4.0] - 2026-06-01

- Added subscription pricing strategy support with dry-run planning, App Store Connect price point guidance, and confirmed `subscriptionPrices`/introductory-offer creation.
- Added `subscription-onboarding-review-template.json` for free-download subscription apps, value-first onboarding, paywall timing, and StoreKit review trigger policy.
- Added validation for subscription pricing gaps, single subscription group recommendations, annual best-value options, intro offers, paywall legal links, and blocked review prompt contexts.
- Added MCP tools and CLI commands for growth strategy planning, subscription price point lookup, and subscription pricing application.

## [1.3.7] - 2026-05-31

- Added a no-text app icon rule so generated icon options avoid words, initials, numbers, pseudo-text, labels, slogans, and watermarks by default.
- Linked the app icon option workflow to the standalone `ios-app-icon-design` Codex skill so release icon guidance and standalone icon-design guidance stay in sync.

## [1.3.6] - 2026-05-31

- Added a reusable iOS app icon option workflow so creators get five visually distinct, App Store-safe icon directions before bundled icon assets are replaced.
- Added `app-icon-options-recipe.json` with default creative directions and third-party IP safety checks for icon exploration.
- Documented that selected app icon changes require a standalone 1024x1024 asset, small-size inspection, a build-number increment, and a newly uploaded/selected build.

## [1.3.5] - 2026-05-31

- Added a reusable third-party IP safety checklist for App Store releases, covering app icons, screenshots, metadata, generated artwork, official marks, and independent reference/fan app disclaimers.
- Added an optional `ipReview` submission-config block plus validation warnings for missing authorization, missing no-affiliation disclaimers, incomplete official-mark checks, and binary asset changes that still need a new build.
- Expanded reviewer-note guidance so IP-remediation notes stay concise, factual, and need-to-know.

## [1.3.4] - 2026-05-31

- Added App Review IP guidance for independent fan/reference apps: front-load no-affiliation disclaimers, avoid unlicensed official marks/artwork, and upload a new build when binary assets change.
- Updated the free-download helper to tolerate App Store Connect's current read-only `appAvailabilities` update behavior while still verifying all territories.
- Adjusted Build Uploads API checksum commits to send the SHA-256 checksum in the encoded form Apple expects.

## [1.3.3] - 2026-05-30

- Tightened subscription metadata validation so Terms of Use/EULA and Privacy Policy URLs must be labeled in the App Store description.
- Added regression coverage for descriptions that mention terms without a functional Terms of Use/EULA link.

## [1.3.2] - 2026-05-30

- Added subscription-app validation for Terms of Use, Privacy Policy, and subscription information inside App Store descriptions.
- Updated the submission template with a compliant subscription information section.
- Expanded release guidance to call out Apple's metadata Terms of Use requirement before review submission.

## [1.3.1] - 2026-05-30

- Added a reusable `screenshot-recipe.json` asset for six-shot App Store screenshot sequences.
- Expanded the App Store Connect release skill with the screenshot recipe workflow, ordering, CTA guidance, and Pro-labeling rules.
- Documented how to copy and render the recipe for future app submissions.

## [1.3.0] - 2026-05-29

- Added `configure-free-download` to set apps to $0/free download and available in every App Store territory after an explicit dry-run/approval step.
- Added MCP access through `asc_configure_free_download` for future app release workflows.
- Improved screenshot template defaults for bright solid backgrounds, conversion-focused headers, CTA pills, ASO/Apple Ads-aware copy, and clear Pro feature labeling.

## [1.2.0] - 2026-05-29

- Added `credential-setup` and `doctor --fix` helpers for secure local App Store Connect API key setup.
- Added MCP access through `asc_credential_setup`, guarded so private key copies and env-file writes require confirmation.
- Expanded `doctor` output with credential readiness, key-path existence, file mode, and recommended setup paths.
- Documented the secure credentials workflow for team and individual App Store Connect API keys.

## [1.1.0] - 2026-05-29

- Added automatic App Store version/build planning from Xcode project settings, Info.plists, git history, and optional Codex iteration counts.
- Added dry-run and confirmed local version application for `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, literal Info.plist versions, and submission JSON files.
- Added optional auto-versioned build uploads and MCP tools for version planning/application.
- Documented Apple's version/build split and safe release-level defaults.

## [1.0.0] - 2026-05-26

- Initial public release of the Apple App Store Connect Codex Plugin.
- Added a Codex release-prep skill covering App Store metadata, build upload, screenshots, subscriptions, review details, and submission safety.
- Added a dependency-light App Store Connect API CLI and stdio MCP server.
- Added conversion-focused screenshot generation with optional Pillow rendering.
- Added metadata field map, submission templates, tests, CI, MIT license, and contribution guidance.
