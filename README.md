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
      release_kit_repository: QuentinHsu/workflow
      release_kit_ref: main
      release_kit_path: release-kits/macos/swiftpm-sparkle
      changelog_path: CHANGELOG.md
      changelog_language: zh-CN
      sparkle_public_ed_key: ${{ vars.SPARKLE_PUBLIC_ED_KEY }}
      architectures: '["arm64","x86_64"]'
    secrets:
      sparkle_private_ed_key: ${{ secrets.SPARKLE_PRIVATE_ED_KEY }}
```

The stable release workflow generates and commits `CHANGELOG.md` before creating a manual release tag. It groups Conventional Commit entries into features, improvements, and fixes, then uses the matching changelog section as the GitHub Release body. Set `changelog_enabled: false` to keep release notes generated directly from git history.

Optional changelog inputs:

- `changelog_path`: changelog file path in the app repository. Defaults to `CHANGELOG.md`.
- `changelog_language`: `zh-CN` or `en`. Defaults to `zh-CN`.
- `changelog_summary_setup_command`: optional shell setup for an external summary command.
- `changelog_summary_command`: optional command template. Use `{prompt_file}` where the generated prompt path should be inserted.
- `changelog_summary_token`: optional secret exposed as both `CHANGELOG_SUMMARY_TOKEN` and `COPILOT_GITHUB_TOKEN`.

Required app-side files:

- `Package.swift`
- `Info.plist`
- optional app icon path passed through `app_icon_path`

Required app repository settings:

- Variable: `SPARKLE_PUBLIC_ED_KEY`
- Secret: `SPARKLE_PRIVATE_ED_KEY`
