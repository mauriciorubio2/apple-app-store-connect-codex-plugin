# Changelog

All notable changes to this project are documented here.

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
