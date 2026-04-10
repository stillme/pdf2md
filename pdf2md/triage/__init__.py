"""Triage — page analysis and engine routing."""

from pdf2md.triage.analyzer import analyze_page, PageAnalysis
from pdf2md.triage.router import select_engine, select_tier

__all__ = ["analyze_page", "PageAnalysis", "select_engine", "select_tier"]
