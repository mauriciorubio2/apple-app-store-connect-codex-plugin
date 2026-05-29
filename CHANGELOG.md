# Changelog

All notable changes to this project are documented here.

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
