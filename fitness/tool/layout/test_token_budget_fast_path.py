from pathlib import Path
from types import ModuleType

import pytest
import tiktoken


def test_small_feature_still_rejects_invalid_utf8(tmp_path: Path, adapter_module: ModuleType):
    source = tmp_path / "src/fitness/features/example/contract.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        adapter_module.token_findings(tmp_path, 15000, "cl100k_base")


@pytest.mark.parametrize("text", ["hello world", "你好🌍", "<|endoftext|>"])
def test_token_budget_bounds_preserve_exact_threshold(
    tmp_path: Path, adapter_module: ModuleType, text: str
):
    source = tmp_path / "src/fitness/features/example/contract.py"
    source.parent.mkdir(parents=True)
    source.write_text(text, encoding="utf-8")
    count = len(tiktoken.get_encoding("cl100k_base").encode(text, disallowed_special=()))
    assert adapter_module.token_findings(tmp_path, len(text.encode("utf-8")), "cl100k_base") == []
    assert adapter_module.token_findings(tmp_path, count, "cl100k_base") == []
    findings = adapter_module.token_findings(tmp_path, count - 1, "cl100k_base")
    assert len(findings) == 1
    assert f"{count} tokens" in findings[0]["tool_message"]
