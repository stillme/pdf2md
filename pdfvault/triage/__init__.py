"""Triage — page analysis and engine routing."""

from pdfvault.triage.analyzer import analyze_page, PageAnalysis
from pdfvault.triage.router import select_engine, select_tier

__all__ = ["analyze_page", "PageAnalysis", "select_engine", "select_tier"]
