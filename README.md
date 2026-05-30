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
- Validate key Apple metadata limits, including 30-character name/subtitle, 100-character keywords, 170-character promotional text, and screenshot count rules.
- Generate App Store screenshot composites from raw UI captures and clearly label paid/subscription features.
- Generate brighter, conversion-focused screenshot composites with salesy ASO/Apple Ads-aware headers, CTA pills, and paid-feature badges.
- Upload screenshots through `appScreenshotSets` and `appScreenshots` asset reservations.
- Set an app to $0/free download and make it available in all App Store territories after an explicit dry-run/approval step.
- Plan and apply App Store versions and build numbers from Xcode project settings, Info.plists, git history, or a Codex iteration count.
- Upload `.ipa` or `.pkg` builds with Apple's Build Uploads API, with Transporter fallback and optional automatic versioning.
- Update App Store version metadata, version localizations, review contact/demo details, selected build relationship, and age rating declarations when resource IDs are supplied.
- Prepare subscription/IAP localization, review screenshot, and App Store description legal-link checklists.
- Prepare IP-sensitive resubmissions by checking unlicensed third-party marks/artwork, front-loading no-affiliation disclaimers, and reminding builders to upload a new binary for asset changes.
- Create dry-run plans so a human can approve exactly what will change.

## Apple Documentation Used

The workflow is based on Apple's current App Store Connect API, App Store Connect Help, and product page guidance:

- [App Store Connect API](https://developer.apple.com/documentation/appstoreconnectapi)
- [Generating tokens for API requests](https://developer.apple.com/documentation/appstoreconnectapi/generating_tokens_for_api_requests)
- [Uploading assets to App Store Connect](https://developer.apple.com/documentation/appstoreconnectapi/uploading_assets_to_app_store_connect)
- [Build uploads](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-builduploads)
- [Upload builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
- [Platform version information](https://developer.apple.com/help/app-store-connect/reference/platform-version-information/)
- [Screenshot specifications](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/)
- [Creating your product page](https://developer.apple.com/app-store/product-page/)
- [Custom product pages](https://developer.apple.com/app-store/custom-product-pages/)
- [Apple Ads custom product pages API](https://developer.apple.com/documentation/apple_search_ads/custom_product_pages)

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

Upload a build with the API:

```bash
python3 plugins/apple-app-store-connect/scripts/asc_cli.py upload-build-api \
  --app-id 1234567890 \
  --file build/App.ipa \
  --version-string 1.0.0 \
  --build-number 42 \
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
  --wait 1800 \
  --yes
```

## Versioning Behavior

Apple separates the user-facing App Store version from the build iteration. `CFBundleShortVersionString` should match the App Store version and use three period-separated integers such as `1.2.3`. `CFBundleVersion` identifies the uploaded build and uses one to three period-separated integers.

The plugin can infer the next values from Xcode `MARKETING_VERSION`, `CURRENT_PROJECT_VERSION`, literal `Info.plist` values, git history, and an optional `--iteration-count`. The default `auto` release level uses git messages conservatively: breaking-change markers become major bumps, conventional `feat:` commits become minor bumps, and other release builds become patch bumps. Build numbers always increment, using the provided iteration count when available.

Generate screenshots:

```bash
python3 -m pip install pillow
cp plugins/apple-app-store-connect/assets/screenshot-recipe.json appstore-screenshot-recipe.json
python3 plugins/apple-app-store-connect/scripts/generate_screenshots.py \
  --config appstore-screenshot-recipe.json
```

Screenshot copy should lead with one high-intent user benefit per image, include search-friendly terms naturally, use bright solid backgrounds that stand out in App Store search results, and clearly label Pro or paid features. Keep the first three screenshots focused on conversion: the core value proposition, a common search/action workflow, and the strongest differentiator. The bundled `screenshot-recipe.json` gives a six-shot App Store sequence: core value, search/action workflow, strongest differentiator, progress/status view, deeper archive/analytics, and paywall or upgrade value.

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
