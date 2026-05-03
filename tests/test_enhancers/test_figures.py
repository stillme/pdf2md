"""Tests for figure enhancer."""
from unittest.mock import MagicMock
from pdfvault.enhancers.figures import enhance_figures
from pdfvault.document import Figure
from pdfvault.config import FigureMode


def test_skip_mode():
    figures = [Figure(id="fig1", page=0, caption="A plot")]
    result = enhance_figures(figures, mode=FigureMode.SKIP, provider=None)
    assert len(result) == 1
    assert result[0].description is None


def test_caption_mode():
    figures = [Figure(id="fig1", page=0, caption="A plot")]
    result = enhance_figures(figures, mode=FigureMode.CAPTION, provider=None)
    assert result[0].description is None


def test_describe_mode():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "A bar chart showing three conditions with error bars."
    figures = [Figure(id="fig1", page=0, caption="Results", image_base64="ZmFrZQ==")]
    result = enhance_figures(figures, mode=FigureMode.DESCRIBE, provider=mock_provider)
    assert result[0].description is not None
    assert "bar chart" in result[0].description


def test_describe_mode_no_image_skips():
    mock_provider = MagicMock()
    figures = [Figure(id="fig1", page=0, caption="Results")]
    result = enhance_figures(figures, mode=FigureMode.DESCRIBE, provider=mock_provider)
    assert result[0].description is None
    mock_provider.complete_sync.assert_not_called()


def test_extract_mode_saves_path():
    mock_provider = MagicMock()
    mock_provider.complete_sync.return_value = "A scatter plot."
    figures = [Figure(id="fig1", page=0, image_base64="ZmFrZQ==")]
    result = enhance_figures(figures, mode=FigureMode.EXTRACT, provider=mock_provider, output_dir="/tmp/figs")
    assert result[0].description is not None
    assert result[0].image_path is not None
