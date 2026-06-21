"""Unit tests for NSE scraper text inference (no HTTP)."""
from __future__ import annotations

from app.db.enums import DocumentType
from app.services.ir_discovery.exchange.nse_scraper import (
    _has_transcript_signals,
    _infer_document_type,
    _is_ingestible_attachment_url,
    _row_to_filing,
)


def test_infer_financial_result_from_media_release_updates():
    blob = (
        "media release - consolidated and standalone unaudited financial results "
        "for the quarter ended september 30, 2024"
    ).lower()
    dt = _infer_document_type("Updates", blob, "https://x/corporate/RELIANCE_MediaRelease.pdf")
    assert dt == DocumentType.FINANCIAL_RESULT


def test_infer_financial_result_from_outcome_of_board_meeting():
    blob = (
        "reliance industries limited has submitted to the exchange, "
        "the financial results for the period ended june 30, 2024"
    ).lower()
    dt = _infer_document_type("Outcome of Board Meeting", blob, "https://x/SEFR_19072024.pdf")
    assert dt == DocumentType.FINANCIAL_RESULT


def test_board_meeting_prior_intimation_is_not_transcript():
    blob = (
        "a meeting of the board of directors of the company is scheduled to be held "
        "on thursday, january 16, 2025, inter alia, to approve unaudited financial "
        "results for the quarter ended december 31, 2024"
    ).lower()
    assert not _has_transcript_signals(blob, "https://x/SE_09012025.pdf")
    dt = _infer_document_type(
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        blob,
        "https://x/SE_09012025.pdf",
    )
    assert dt is None


def test_ingestible_url_suffixes():
    assert _is_ingestible_attachment_url("https://x/corporate/RELIANCE_MediaRelease.pdf")
    assert _is_ingestible_attachment_url("https://x/file.PDF?foo=1")
    assert not _is_ingestible_attachment_url("https://x/corporate/CVR_30042020183241.zip")
    assert not _is_ingestible_attachment_url("https://x/corporate/filing.xlsx")


def test_row_to_filing_drops_zip_attachments():
    row = {
        "desc": "Financial Result Updates",
        "attchmntText": (
            "Reliance Industries Limited has submitted to the Exchange, "
            "the financial results for the period ended March 31, 2020"
        ),
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/CVR_30042020183241.zip",
        "an_dt": "30-Apr-2020 18:32:41",
    }
    assert _row_to_filing(row) is None


def test_transcript_av_recording():
    blob = (
        "audio / video recording and transcript of the presentation made to analysts "
        "on the unaudited financial results for the quarter ended september 30, 2024"
    ).lower()
    assert _has_transcript_signals(blob, "https://x/SETranscriptAV.pdf")
    dt = _infer_document_type(
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        blob,
        "https://x/SETranscriptAV.pdf",
    )
    assert dt == DocumentType.CONCALL_TRANSCRIPT
