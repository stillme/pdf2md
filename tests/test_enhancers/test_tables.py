"""Tests for table enhancer."""
from unittest.mock import MagicMock
from pdf2md.enhancers.tables import enhance_table
from pdf2md.document import Table

CONFIDENCE_THRESHOLD = 0.7

def test_enhance_table_high_confidence_unchanged():
    table = Table(id="tab1", markdown="| A | B |\n|---|---|\n| 1 | 2 |",
                  headers=["A", "B"], rows=[["1", "2"]], page=0, confidence=0.95)
    mock_provider = MagicMock()
    result = enhance_table(table, provider=mock_provider)
    mock_provider.complete_sync.assert_not_called()
    assert result.markdown == table.markdown


def test_enhance_table_low_confidence_uses_vlm():
    table = Table(id="tab1", markdown="| A | B |\n|---|---|\n| 1 | 2 |",
                  headers=["A", "B"], rows=[["1", "2"]], page=0, confidence=0.4)
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
    result = enhance_table(table, provider=mock_provider, page_image=b"fake_image")
    assert "C" in result.markdown
    assert result.confidence > table.confidence


def test_enhance_table_no_provider_unchanged():
    table = Table(id="tab1", markdown="| A |\n|---|\n| 1 |",
                  headers=["A"], rows=[["1"]], page=0, confidence=0.3)
    result = enhance_table(table, provider=None)
    assert result.markdown == table.markdown
