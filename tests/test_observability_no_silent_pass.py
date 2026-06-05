import ast
from pathlib import Path

SRC_ROOT = Path("src")
ADMIN_ROUTER_TARGETS = tuple(sorted(Path("src/routers/admin").glob("*.py")))

TARGETS = (
    Path("src/services/fast_mode.py"),
    Path("src/skills/seedance_video_generate.py"),
    Path("src/skills/remotion_assemble.py"),
    Path("src/api.py"),
    Path("src/routers/_state.py"),
    Path("src/tasks/bg_registry.py"),
    Path("src/telemetry.py"),
    Path("src/graph/pipeline.py"),
    Path("src/graph/routing.py"),
    Path("src/pipeline/state_manager.py"),
    *ADMIN_ROUTER_TARGETS,
    Path("src/skills/elevenlabs_tts.py"),
    Path("src/skills/media_quality_audit.py"),
    Path("src/skills/video_analysis.py"),
    Path("src/quality/skill_versioning.py"),
)

ALLOWED_BARE_PASS_EXCEPTIONS = {
    ("src/_version.py", "get_version", "PackageNotFoundError"),
    ("src/agents/strategy.py", "StrategyAgent.run", "ValueError"),
    ("src/pipeline/gate_manager.py", "_get_next_step", "ValueError"),
    ("src/pipeline/step_runner.py", "_get_next_step", "ValueError"),
    ("src/routers/assets.py", "<module>", "ImportError"),
    ("src/skills/character_identity.py", "<module>", "ValueError"),
    ("src/skills/gpt_image_generate.py", "<module>", "ValueError"),
    ("src/skills/keyframe_images.py", "<module>", "ValueError"),
    ("src/skills/product_strategy.py", "<module>", "ValueError"),
    ("src/skills/seedance_prompt.py", "<module>", "ValueError"),
    ("src/skills/thumbnail_prompt.py", "<module>", "ValueError"),
    ("src/skills/video_continuity_manager.py", "<module>", "ValueError"),
    ("src/tools/llm_client.py", "LLMClient._parse_json", "json.JSONDecodeError"),
    ("src/tools/video_downloader.py", "VideoDownloader._check_whisper", "ImportError"),
    ("src/tools/video_downloader.py", "VideoDownloader._validate_url", "ValueError"),
    ("src/tools/webhook_manager.py", "_is_safe_webhook_url", "ValueError"),
}


def _exception_type_name(node: ast.expr | None) -> str:
    if node is None:
        return "<bare>"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_exception_type_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Tuple):
        return "(" + ", ".join(_exception_type_name(item) for item in node.elts) + ")"
    return ast.unparse(node)


def _context_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    names: list[str] = []
    parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(parent.name)
        parent = parents.get(parent)
    return ".".join(reversed(names)) if names else "<module>"


def _bare_pass_exception_handlers(path: Path) -> set[tuple[str, str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parents = {
        child: node
        for node in ast.walk(tree)
        for child in ast.iter_child_nodes(node)
    }
    handlers: set[tuple[str, str, str]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            handlers.add(
                (
                    path.as_posix(),
                    _context_name(node, parents),
                    _exception_type_name(node.type),
                )
            )

    return handlers


def test_high_impact_video_paths_do_not_silently_swallow_exceptions() -> None:
    failures: list[str] = []

    for path in TARGETS:
        failures.extend(
            f"{location[0]}:{location[1]}:{location[2]}"
            for location in _bare_pass_exception_handlers(path)
        )

    assert not failures, "bare pass in exception handlers: " + ", ".join(failures)


def test_all_remaining_bare_pass_exception_handlers_are_explicitly_allowlisted() -> None:
    discovered = set()
    for path in SRC_ROOT.rglob("*.py"):
        discovered.update(_bare_pass_exception_handlers(path))

    unexpected = sorted(discovered - ALLOWED_BARE_PASS_EXCEPTIONS)
    stale = sorted(ALLOWED_BARE_PASS_EXCEPTIONS - discovered)

    assert not unexpected, "unexpected bare pass in exception handlers: " + ", ".join(
        f"{path}:{context}:{exception_type}"
        for path, context, exception_type in unexpected
    )
    assert not stale, "stale bare pass allowlist entries: " + ", ".join(
        f"{path}:{context}:{exception_type}"
        for path, context, exception_type in stale
    )
