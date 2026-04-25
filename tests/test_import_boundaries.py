from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return imports


def test_shared_grounding_modules_do_not_import_domains() -> None:
    for relative_path in ("pipeline/frame_grounding.py", "pipeline/secondary_fact_utils.py"):
        imports = _imports_for(REPO_ROOT / relative_path)
        assert not any(module.startswith("pipeline.domains") for module in imports), relative_path


def test_domain_modules_import_shared_helpers_from_non_domain_modules() -> None:
    expected_imports = {
        "pipeline/domains/public_employment.py": "pipeline.frame_grounding",
        "pipeline/domains/public_money.py": "pipeline.frame_grounding",
        "pipeline/domains/funding.py": "pipeline.frame_grounding",
        "pipeline/domains/political_profile.py": "pipeline.secondary_fact_utils",
    }
    for relative_path, expected_module in expected_imports.items():
        imports = _imports_for(REPO_ROOT / relative_path)
        assert expected_module in imports, relative_path


def test_relations_service_remains_domain_facing_facade() -> None:
    imports = _imports_for(REPO_ROOT / "pipeline/relations/service.py")
    assert any(module.startswith("pipeline.domains") for module in imports)
