# Workflow

Reusable GitHub Actions workflows and release kits for different project types.

## Layout

```text
.github/workflows/
  macos-swiftpm-sparkle-dmg-release.yml
  macos-swiftpm-sparkle-dmg-beta-release.yml

release-kits/
  macos/
    swiftpm-sparkle/
      Scripts/
```

Reusable workflows live in `.github/workflows/` so app repositories can call them with `jobs.<job>.uses`.

Release-kit scripts live outside `.github/workflows/` and are checked out by the reusable workflow at runtime. This keeps the repository ready for more project families later, such as Node, Python, Docker, iOS, or other macOS packaging styles.

## macOS SwiftPM Sparkle Kit

Use this kit for Swift Package Manager macOS apps that ship DMGs and Sparkle appcasts.

Caller workflow example:

```yaml
jobs:
  release:
    uses: QuentinHsu/workflow/.github/workflows/macos-swiftpm-sparkle-dmg-release.yml@main
    permissions:
      contents: write
    with:
      app_target_name: SkillsHub
      app_display_name: Skills Hub
      app_bundle_id: com.skillshub.app
      app_min_macos: "15.0"
      app_icon_path: Assets/AppIcon.icns
      macos_runner: macos-15
      xcode_version: latest-stable
      release_kit_repository: QuentinHsu/workflow
      release_kit_ref: main
      release_kit_path: release-kits/macos/swiftpm-sparkle
      changelog_path: CHANGELOG.md
      changelog_language: zh-CN
      sparkle_public_ed_key: ${{ vars.SPARKLE_PUBLIC_ED_KEY }}
      architectures: '["arm64","x86_64"]'
    secrets:
      sparkle_private_ed_key: ${{ secrets.SPARKLE_PRIVATE_ED_KEY }}
      code_sign_certificate_base64: ${{ secrets.MACOS_CODE_SIGN_CERTIFICATE_BASE64 }}
      code_sign_certificate_password: ${{ secrets.MACOS_CODE_SIGN_CERTIFICATE_PASSWORD }}
      notarization_key_base64: ${{ secrets.APPLE_NOTARIZATION_KEY_BASE64 }}
      notarization_key_id: ${{ secrets.APPLE_NOTARIZATION_KEY_ID }}
      notarization_issuer_id: ${{ secrets.APPLE_NOTARIZATION_ISSUER_ID }}
```

The stable release workflow generates and commits `CHANGELOG.md` before creating a manual release tag. It groups Conventional Commit entries into features, improvements, and fixes, then uses the matching changelog body as the GitHub Release body. When a Copilot token is provided, it installs GitHub Copilot CLI and asks Copilot to analyze the raw release commit messages for the top summary sentence only. If Copilot is unavailable or the command fails, it falls back to the local summary. Set `changelog_enabled: false` to keep release notes generated directly from git history.

Optional changelog inputs:

- `changelog_path`: changelog file path in the app repository. Defaults to `CHANGELOG.md`.
- `changelog_language`: `zh-CN` or `en`. Defaults to `zh-CN`.
- `changelog_summary_setup_command`: optional shell setup for the summary command. If omitted and a Copilot token is provided, the workflow runs `npm install -g @github/copilot`.
- `changelog_summary_command`: optional command template for generating only the top summary sentence from the raw commit messages. Use `{prompt_file}` where the generated prompt path should be inserted. If omitted and a Copilot token is provided, the workflow uses `copilot -s --no-ask-user --no-custom-instructions --disable-builtin-mcps -p "$(cat {prompt_file})"`.
- `changelog_summary_token`: optional secret exposed as `CHANGELOG_SUMMARY_TOKEN`, `COPILOT_GITHUB_TOKEN`, `GH_TOKEN`, and `GITHUB_TOKEN`.

Optional toolchain inputs:

- `macos_runner`: GitHub-hosted macOS runner label for the build job. Defaults to `macos-15`.
- `xcode_version`: Xcode version passed to `maxim-lobanov/setup-xcode`. Defaults to `latest-stable`.

Use both when a package requires a newer Swift tools version than the default runner provides, for example by selecting a runner image that includes the needed Xcode and then setting `xcode_version` to that installed version.

For Swift 6.3, use an image that includes Xcode 26.4.1:

```yaml
with:
  macos_runner: macos-26
  xcode_version: "26.4.1"
```

For GitHub Copilot CLI changelog summaries, create a fine-grained personal access token from [GitHub personal access tokens](https://github.com/settings/personal-access-tokens/new), add the `Copilot Requests` account permission, and make sure the token owner has access to GitHub Copilot. Classic personal access tokens and the built-in `GITHUB_TOKEN` do not provide Copilot Requests access. Save the token in the caller repository as the `COPILOT_GITHUB_TOKEN` Actions secret, then pass it through with:

```yaml
secrets:
  changelog_summary_token: ${{ secrets.COPILOT_GITHUB_TOKEN }}
```

The default Copilot command uses silent, non-interactive mode so the release workflow can capture a clean summary without prompts.

Required app-side files:

- `Package.swift`
- `Info.plist`
- optional app icon path passed through `app_icon_path`

Required app repository settings:

- Variable: `SPARKLE_PUBLIC_ED_KEY`
- Secret: `SPARKLE_PRIVATE_ED_KEY`

Recommended signing and notarization settings for public releases:

- Secret: `MACOS_CODE_SIGN_CERTIFICATE_BASE64`
- Secret: `MACOS_CODE_SIGN_CERTIFICATE_PASSWORD`
- Secret: `APPLE_NOTARIZATION_KEY_BASE64`
- Secret: `APPLE_NOTARIZATION_KEY_ID`
- Secret: `APPLE_NOTARIZATION_ISSUER_ID`

`MACOS_CODE_SIGN_CERTIFICATE_BASE64` should contain a base64-encoded `.p12` with a Developer ID Application certificate and private key. `APPLE_NOTARIZATION_KEY_BASE64` should contain a base64-encoded App Store Connect API key `.p8`. If signing secrets are omitted, the workflow falls back to ad-hoc signing, which is useful for internal testing but will be rejected by Gatekeeper for normal downloaded releases.
