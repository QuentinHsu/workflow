#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass


LANGUAGE_PRESETS = {
    "zh-CN": {
        "feature": "新增功能",
        "improvement": "优化改进",
        "fix": "问题修复",
        "other": "其他",
        "summary_prefix": "本次更新重点覆盖",
        "summary_all": "同时包含能力补齐、体验整理和稳定性修复。",
        "summary_feature_improvement": "主要补齐能力并整理使用体验。",
        "summary_feature_fix": "主要补齐功能并修复关键问题。",
        "summary_improvement_fix": "主要提升体验表现并修复稳定性问题。",
        "summary_feature": "以新能力补齐为主。",
        "summary_improvement": "主要是一次体验与实现整理。",
        "summary_fix": "以稳定性修复为主。",
        "multiple_scopes": "多个模块",
        "no_entries": "- 暂无独立条目。",
        "stats_title": "### 变更统计",
        "stats_feature": "新增功能",
        "stats_improvement": "优化改进",
        "stats_fix": "问题修复",
        "grouped_title": "### 按模块归纳",
        "separator": "；",
        "summary_separator": "，",
        "colon": "：",
        "item_suffix": " 项",
        "prompt_intro": "请为 {project_name} v{version} 生成一句中文发布摘要。",
        "prompt_requirements": (
            "要求：\n"
            "1. 只输出一句话，不要标题，不要列表。\n"
            "2. 重点说明这次更新给用户带来的结果。\n"
            "3. 不要虚构未出现的能力，不要提及 Git commit、scope 或统计数字。\n"
            "4. 语气克制、简洁，适合放在 GitHub Release 顶部。\n"
            "5. 不要提及版本号，用「本次更新」作为主语开头。"
        ),
        "fallback_release": "发布 {version}",
    },
    "en": {
        "feature": "Features",
        "improvement": "Improvements",
        "fix": "Fixes",
        "other": "Other",
        "summary_prefix": "This update focuses on",
        "summary_all": "with new capabilities, refinements, and stability fixes.",
        "summary_feature_improvement": "with new capabilities and usability refinements.",
        "summary_feature_fix": "with new capabilities and important fixes.",
        "summary_improvement_fix": "with refinements and stability fixes.",
        "summary_feature": "with new capabilities.",
        "summary_improvement": "with implementation and experience refinements.",
        "summary_fix": "with stability fixes.",
        "multiple_scopes": "multiple areas",
        "no_entries": "- No standalone entries.",
        "stats_title": "### Change Stats",
        "stats_feature": "Features",
        "stats_improvement": "Improvements",
        "stats_fix": "Fixes",
        "grouped_title": "### Grouped Changes",
        "separator": "; ",
        "summary_separator": ", ",
        "colon": ": ",
        "item_suffix": "",
        "prompt_intro": "Write one concise English release summary sentence for {project_name} v{version}.",
        "prompt_requirements": (
            "Requirements:\n"
            "1. Output one sentence only, with no title and no list.\n"
            "2. Focus on the user-facing result of this update.\n"
            "3. Do not invent changes, mention Git commits, scopes, or statistics.\n"
            "4. Keep the tone concise and suitable for the top of a GitHub Release.\n"
            "5. Do not mention the version number; start with \"This update\"."
        ),
        "fallback_release": "Release {version}",
    },
}


TYPE_TO_CATEGORY = {
    "feat": "feature",
    "fix": "fix",
    "perf": "improvement",
    "refactor": "improvement",
    "build": "improvement",
    "ci": "improvement",
    "docs": "improvement",
    "style": "improvement",
    "test": "improvement",
    "chore": "improvement",
    "revert": "fix",
}


IGNORED_SUBJECT_PREFIXES = (
    "merge ",
)


CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?:\s*(?P<description>.+)$"
)


TOOL_LOG_PATTERN = re.compile(
    r"^\s*>?\s*[✗●○◆◇▶▷→⟶⏵]\s+.+\((?:shell|bash|zsh|sh)\)\s*$"
    r"|^\s*[●○◆◇▶▷→⟶⏵\-\*]\s+(?:Read|Write|Search|View|Execute|Open|Fetch|Load)\s+.+$"
    r"|^\s*[└├│─┌┐┘┤┬┴┼╠╣╔╗╚╝]\s*.*$"
    r"|^\s*L\d+:\d+\s*\(.*\)$",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass
class CommitMessage:
    subject: str
    body: str
    lower_subject: str


@dataclass
class CommitEntry:
    category: str
    scope: str | None
    description: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or update CHANGELOG.md from git commits.")
    parser.add_argument("--version", required=True, help="Release version without leading v")
    parser.add_argument("--to-ref", default="HEAD", help="Ending git ref for the changelog range")
    parser.add_argument("--from-ref", default="", help="Starting git ref, exclusive")
    parser.add_argument("--changelog", default="CHANGELOG.md", help="Path to CHANGELOG.md")
    parser.add_argument("--project-name", default=os.getenv("CHANGELOG_PROJECT_NAME", ""), help="Project name for optional summaries")
    parser.add_argument("--language", default=os.getenv("CHANGELOG_LANGUAGE", "zh-CN"), choices=sorted(LANGUAGE_PRESETS))
    parser.add_argument(
        "--scope-alias",
        action="append",
        default=[],
        metavar="FROM=TO",
        help="Normalize a commit scope label; may be repeated",
    )
    parser.add_argument(
        "--mode",
        choices=["section", "body", "write"],
        default="section",
        help="Print full section, print body only, or write back to CHANGELOG.md",
    )
    return parser.parse_args()


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def build_revision_range(from_ref: str, to_ref: str) -> str:
    if from_ref:
        return f"{from_ref}..{to_ref}"
    return to_ref


def parse_scope_aliases(values: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --scope-alias value: {value!r}; expected FROM=TO")
        raw_from, raw_to = value.split("=", maxsplit=1)
        from_key = normalize_scope(raw_from, {})
        to_value = normalize_scope(raw_to, {})
        if from_key and to_value:
            aliases[from_key] = to_value
    return aliases


def normalize_scope(scope: str | None, aliases: dict[str, str]) -> str | None:
    if scope is None:
        return None

    normalized = scope.strip().lower().replace("_", "-")
    if not normalized:
        return None
    return aliases.get(normalized, normalized)


def normalize_description(description: str) -> str:
    cleaned = re.sub(r"\s+", " ", description.strip())
    return cleaned.rstrip("。.;；")


def collect_commits(from_ref: str, to_ref: str) -> list[CommitMessage]:
    revision_range = build_revision_range(from_ref, to_ref)
    raw_log = run_git("log", "--reverse", "--format=%s%x1f%b%x1e", revision_range)
    commits: list[CommitMessage] = []

    for record in raw_log.strip("\x1e").split("\x1e"):
        if not record.strip():
            continue
        subject, body = (record.split("\x1f", maxsplit=1) + [""])[:2]
        normalized_subject = subject.strip()
        normalized_body = body.strip()
        lower_subject = normalized_subject.lower()
        if any(lower_subject.startswith(prefix) for prefix in IGNORED_SUBJECT_PREFIXES):
            continue
        commits.append(CommitMessage(subject=normalized_subject, body=normalized_body, lower_subject=lower_subject))

    return commits


def classify_commit(subject: str, body: str, lower_subject: str, scope_aliases: dict[str, str], preset: dict[str, str]) -> CommitEntry:
    match = CONVENTIONAL_COMMIT_PATTERN.match(subject)

    if match:
        commit_type = match.group("type").lower()
        scope = normalize_scope(match.group("scope"), scope_aliases)
        description = normalize_description(match.group("description"))
        breaking = bool(match.group("breaking")) or "BREAKING CHANGE" in body
        category = TYPE_TO_CATEGORY.get(commit_type, "improvement")
        if breaking:
            description = f"Breaking: {description}"
        return CommitEntry(category=category, scope=scope, description=description)

    fallback_category = "fix" if any(keyword in lower_subject for keyword in ("fix", "bug")) else "improvement"
    return CommitEntry(
        category=fallback_category,
        scope=None,
        description=normalize_description(subject) or preset["fallback_release"].format(version=""),
    )


def group_entries(entries: list[CommitEntry]) -> OrderedDict[str, dict[str, list[str]]]:
    grouped: OrderedDict[str, dict[str, list[str]]] = OrderedDict()

    for entry in entries:
        scope_key = entry.scope or "other"
        if scope_key not in grouped:
            grouped[scope_key] = {
                "feature": [],
                "improvement": [],
                "fix": [],
            }
        grouped[scope_key][entry.category].append(entry.description)

    return grouped


def dedupe_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def format_scope_label(scope: str, preset: dict[str, str]) -> str:
    if scope == "other":
        return preset["other"]
    return f"`{scope}`"


def format_descriptions(items: list[str], preset: dict[str, str]) -> str:
    return preset["separator"].join(dedupe_items(items))


def build_summary(entries: list[CommitEntry], preset: dict[str, str]) -> str:
    counts = {
        "feature": 0,
        "improvement": 0,
        "fix": 0,
    }
    scope_counts: OrderedDict[str, int] = OrderedDict()
    scope_order: dict[str, int] = {}

    for index, entry in enumerate(entries):
        counts[entry.category] += 1
        scope_key = entry.scope or "other"
        if scope_key not in scope_order:
            scope_order[scope_key] = index
        scope_counts[scope_key] = scope_counts.get(scope_key, 0) + 1

    ranked_scopes = [
        scope
        for scope, _ in sorted(
            scope_counts.items(),
            key=lambda item: (-item[1], scope_order[item[0]]),
        )
    ]
    display_scopes = [format_scope_label(scope, preset) for scope in ranked_scopes if scope != "other"][:3]
    scope_text = "、".join(display_scopes) if display_scopes else preset["multiple_scopes"]

    if counts["feature"] and counts["improvement"] and counts["fix"]:
        result_text = preset["summary_all"]
    elif counts["feature"] and counts["improvement"]:
        result_text = preset["summary_feature_improvement"]
    elif counts["feature"] and counts["fix"]:
        result_text = preset["summary_feature_fix"]
    elif counts["improvement"] and counts["fix"]:
        result_text = preset["summary_improvement_fix"]
    elif counts["feature"]:
        result_text = preset["summary_feature"]
    elif counts["improvement"]:
        result_text = preset["summary_improvement"]
    else:
        result_text = preset["summary_fix"]

    return f"> {preset['summary_prefix']} {scope_text}{preset['summary_separator']}{result_text}"


def render_stats(entries: list[CommitEntry], preset: dict[str, str]) -> str:
    counts = {
        "feature": 0,
        "improvement": 0,
        "fix": 0,
    }
    for entry in entries:
        counts[entry.category] += 1

    return "\n".join(
        [
            preset["stats_title"],
            "",
            f"- {preset['stats_feature']}{preset['colon']}{counts['feature']}{preset['item_suffix']}",
            f"- {preset['stats_improvement']}{preset['colon']}{counts['improvement']}{preset['item_suffix']}",
            f"- {preset['stats_fix']}{preset['colon']}{counts['fix']}{preset['item_suffix']}",
        ]
    )


def render_grouped_changes(entries: list[CommitEntry], preset: dict[str, str]) -> str:
    grouped = group_entries(entries)
    lines = [preset["grouped_title"], ""]

    if not grouped:
        lines.append(preset["no_entries"])
        return "\n".join(lines)

    for scope, categories in grouped.items():
        lines.append(f"- {format_scope_label(scope, preset)}")
        for category in ("feature", "improvement", "fix"):
            descriptions = categories[category]
            if not descriptions:
                continue
            lines.append(f"  - {preset[category]}{preset['colon']}{format_descriptions(descriptions, preset)}")

    return "\n".join(lines)


def render_commit_messages(commits: list[CommitMessage], preset: dict[str, str]) -> str:
    if not commits:
        return preset["fallback_release"].format(version="")

    lines: list[str] = []
    for index, commit in enumerate(commits, start=1):
        lines.append(f"{index}. {commit.subject}")
        if commit.body:
            body = re.sub(r"\n{3,}", "\n\n", commit.body.strip())
            lines.extend(f"   {line}" if line else "" for line in body.splitlines())

    return "\n".join(lines)


def build_summary_prompt(project_name: str, version: str, commits: list[CommitMessage], preset: dict[str, str], language: str) -> str:
    commit_messages = render_commit_messages(commits, preset)
    if language == "zh-CN":
        return f"""{preset["prompt_intro"].format(project_name=project_name, version=version)}

{preset["prompt_requirements"]}

请直接分析下面的 Git commit message 来归纳摘要，不要根据 Conventional Commit 的 type、scope 或数量机械拼接。

Commit messages:
{commit_messages}
"""

    return f"""{preset["prompt_intro"].format(project_name=project_name, version=version)}

{preset["prompt_requirements"]}

Analyze the Git commit messages below directly. Do not mechanically compose the summary from Conventional Commit types, scopes, or counts.

Commit messages:
{commit_messages}
"""


def _sanitize_summary_output(text: str) -> str:
    cleaned = TOOL_LOG_PATTERN.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_markdown_fence(text: str) -> str:
    match = re.match(r"^```(?:markdown|md)?\s*\n(?P<body>.*)\n```\s*$", text.strip(), re.DOTALL | re.IGNORECASE)
    if match:
        return match.group("body").strip()
    return re.sub(r"^```(?:markdown|md)?\s*", "", re.sub(r"\s*```$", "", text.strip(), flags=re.IGNORECASE), flags=re.IGNORECASE).strip()


def run_prompt_command(command_template: str, prompt: str, warning_label: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as prompt_file:
        prompt_file.write(prompt)
        prompt_path = prompt_file.name

    completed: subprocess.CompletedProcess[str] | None = None
    try:
        command = command_template.replace("{prompt_file}", shlex.quote(prompt_path))
        completed = subprocess.run(
            ["/bin/sh", "-lc", command],
            capture_output=True,
            text=True,
        )
    finally:
        pathlib.Path(prompt_path).unlink(missing_ok=True)

    if completed.returncode != 0:
        print(
            f"Warning: {warning_label} failed, falling back to local changelog: {completed.stderr.strip()}",
            file=sys.stderr,
        )
        return None

    output = _strip_markdown_fence(_sanitize_summary_output(completed.stdout))
    return output or None


def build_summary_with_optional_command(project_name: str, version: str, commits: list[CommitMessage], entries: list[CommitEntry], preset: dict[str, str], language: str) -> str:
    command_template = os.getenv("CHANGELOG_SUMMARY_COMMAND", "").strip()
    if not command_template:
        return build_summary(entries, preset)

    prompt = build_summary_prompt(project_name, version, commits, preset, language)
    output = run_prompt_command(command_template, prompt, "summary command")
    if output is None:
        return build_summary(entries, preset)

    summary = output.lstrip("> ").strip()
    return f"> {summary}"


def render_by_category(entries: list[CommitEntry], preset: dict[str, str]) -> str:
    categories: dict[str, OrderedDict[str | None, list[str]]] = {
        "feature": OrderedDict(),
        "improvement": OrderedDict(),
        "fix": OrderedDict(),
    }

    for entry in entries:
        scoped_entries = categories[entry.category]
        if entry.scope not in scoped_entries:
            scoped_entries[entry.scope] = []
        scoped_entries[entry.scope].append(entry.description)

    lines: list[str] = []
    for category in ("feature", "improvement", "fix"):
        scoped_entries = categories[category]
        if not scoped_entries:
            continue
        if lines:
            lines.append("")
        lines.append(f"### {preset[category]}")
        lines.append("")
        for scope, descriptions in scoped_entries.items():
            unique_descriptions = dedupe_items(descriptions)
            if not unique_descriptions:
                continue
            if scope is None:
                lines.extend(f"- {description}" for description in unique_descriptions)
                continue
            if len(unique_descriptions) == 1:
                lines.append(f"- **{scope}**{preset['colon']}{unique_descriptions[0]}")
                continue
            lines.append(f"- **{scope}**{preset['colon']}")
            lines.extend(f"  - {description}" for description in unique_descriptions)

    return "\n".join(lines)


def render_local_section(project_name: str, version: str, commits: list[CommitMessage], entries: list[CommitEntry], preset: dict[str, str], language: str) -> str:
    if not entries:
        entries = [CommitEntry(category="improvement", scope=None, description=preset["fallback_release"].format(version=version))]

    section_parts = [
        f"## v{version}",
        "",
        build_summary_with_optional_command(project_name, version, commits, entries, preset, language),
        "",
        render_by_category(entries, preset),
    ]
    return "\n".join(section_parts).strip() + "\n"


def write_changelog(changelog_path: pathlib.Path, version: str, section: str) -> None:
    existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
    pattern = re.compile(rf"^##\s+v?{re.escape(version)}\s*$\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)

    if pattern.search(existing):
        updated = pattern.sub(section.rstrip() + "\n\n", existing, count=1)
    else:
        updated = section.rstrip() + "\n\n" + existing.lstrip()

    changelog_path.write_text(updated.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    preset = LANGUAGE_PRESETS[args.language]
    project_name = args.project_name or os.getenv("GITHUB_REPOSITORY", "Project").split("/")[-1]
    scope_aliases = parse_scope_aliases(args.scope_alias)

    commits = collect_commits(args.from_ref, args.to_ref)
    entries = [
        classify_commit(commit.subject, commit.body, commit.lower_subject, scope_aliases, preset)
        for commit in commits
    ]
    section = render_local_section(project_name, args.version, commits, entries, preset, args.language)

    if args.mode == "section":
        sys.stdout.write(section)
        return 0

    if args.mode == "body":
        body = section.split("\n", maxsplit=1)[1]
        sys.stdout.write(body.lstrip())
        return 0

    changelog_path = pathlib.Path(args.changelog)
    write_changelog(changelog_path, args.version, section)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
