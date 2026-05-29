# Changelog

All notable changes to this project are documented here.

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
