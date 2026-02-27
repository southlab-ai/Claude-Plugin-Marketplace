"""Unit tests for OfficeCOMAdapter."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from src.adapters.office_com import OfficeCOMAdapter


@pytest.fixture
def adapter():
    """Create a fresh OfficeCOMAdapter for each test."""
    return OfficeCOMAdapter()


class TestOfficeCOMProbe:
    """Tests for probe behavior."""

    def test_probe_success_excel(self, adapter):
        """probe returns True when Excel.Application is running."""
        mock_app = MagicMock()
        mock_client = MagicMock()
        mock_client.GetActiveObject.return_value = mock_app

        mock_win32com = MagicMock()
        mock_win32com.client = mock_client

        with patch.dict("sys.modules", {"win32com": mock_win32com, "win32com.client": mock_client}):
            result = adapter.probe(12345)
            assert result is True
            assert adapter._app is mock_app
            assert adapter._app_type == "excel"

    def test_probe_success_word(self, adapter):
        """probe returns True when Word.Application is running."""
        def side_effect(progid):
            if progid == "Word.Application":
                return MagicMock()
            raise Exception("not running")

        mock_client = MagicMock()
        mock_client.GetActiveObject = side_effect
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client

        with patch.dict("sys.modules", {"win32com": mock_win32com, "win32com.client": mock_client}):
            result = adapter.probe(12345)
            assert result is True
            assert adapter._app_type == "word"

    def test_probe_failure_no_office(self, adapter):
        """probe returns False when no Office application is running."""
        mock_client = MagicMock()
        mock_client.GetActiveObject = MagicMock(side_effect=Exception("not running"))
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client

        with patch.dict("sys.modules", {"win32com": mock_win32com, "win32com.client": mock_client}):
            result = adapter.probe(12345)
            assert result is False

    def test_probe_handles_import_error(self, adapter):
        """probe returns False if win32com is not available."""
        with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}):
            result = adapter.probe(12345)
            assert result is False


class TestOfficeCOMSupportsAction:
    """Tests for supports_action."""

    def test_supports_set_value(self, adapter):
        assert adapter.supports_action("set_value") is True

    def test_supports_get_value(self, adapter):
        assert adapter.supports_action("get_value") is True

    def test_supports_invoke(self, adapter):
        assert adapter.supports_action("invoke") is True

    def test_does_not_support_delete(self, adapter):
        assert adapter.supports_action("delete") is False


class TestOfficeCOMExecute:
    """Tests for execute method."""

    def test_execute_get_value(self, adapter):
        """get_value reads cell value from Excel."""
        mock_app = MagicMock()
        mock_sheet = MagicMock()
        mock_range = MagicMock()
        mock_range.Value = 42

        mock_app.ActiveWorkbook = MagicMock()
        mock_app.ActiveSheet = mock_sheet
        mock_sheet.Range.return_value = mock_range

        adapter._app = mock_app
        adapter._app_type = "excel"

        result = adapter.execute(12345, "A1", "get_value", None)
        assert result.success is True
        assert result.element["value"] == "42"

    def test_execute_set_value(self, adapter):
        """set_value writes to a cell in Excel."""
        mock_app = MagicMock()
        mock_sheet = MagicMock()
        mock_range = MagicMock()

        mock_app.ActiveWorkbook = MagicMock()
        mock_app.ActiveSheet = mock_sheet
        mock_sheet.Range.return_value = mock_range

        adapter._app = mock_app
        adapter._app_type = "excel"

        result = adapter.execute(12345, "B2", "set_value", "hello")
        assert result.success is True

    def test_execute_with_sheet_reference(self, adapter):
        """Cell references with sheet names are parsed correctly."""
        mock_app = MagicMock()
        mock_wb = MagicMock()
        mock_sheet = MagicMock()
        mock_range = MagicMock()
        mock_range.Value = "test"

        mock_app.ActiveWorkbook = mock_wb
        mock_wb.Sheets.return_value = mock_sheet
        mock_sheet.Range.return_value = mock_range

        adapter._app = mock_app
        adapter._app_type = "excel"

        result = adapter.execute(12345, "Sheet1!A1", "get_value", None)
        assert result.success is True
        mock_wb.Sheets.assert_called_with("Sheet1")

    def test_execute_unsupported_action(self, adapter):
        """Unsupported actions return failure."""
        adapter._app = MagicMock()
        adapter._app_type = "excel"

        result = adapter.execute(12345, "A1", "delete", None)
        assert result.success is False

    def test_execute_get_value_non_excel(self, adapter):
        """get_value on non-Excel apps returns failure."""
        adapter._app = MagicMock()
        adapter._app_type = "word"

        result = adapter.execute(12345, "A1", "get_value", None)
        assert result.success is False


class TestOfficeCOMVBACheck:
    """Tests for VBA macro detection."""

    def test_vba_check_warns_on_macros(self, adapter):
        """_check_vba_macros logs warning when VBA components exist."""
        mock_app = MagicMock()
        mock_wb = MagicMock()
        mock_vb = MagicMock()
        mock_vb.VBComponents.Count = 3
        mock_wb.VBProject = mock_vb
        mock_app.ActiveWorkbook = mock_wb

        adapter._app = mock_app
        adapter._app_type = "excel"

        with patch("src.adapters.office_com.logger") as mock_logger:
            adapter._check_vba_macros()
            mock_logger.warning.assert_called_once()
            assert "VBA component" in mock_logger.warning.call_args[0][0]
            assert mock_logger.warning.call_args[0][1] == 3

    def test_vba_check_no_warning_without_macros(self, adapter):
        """_check_vba_macros does not warn when no VBA components."""
        mock_app = MagicMock()
        mock_wb = MagicMock()
        mock_vb = MagicMock()
        mock_vb.VBComponents.Count = 0
        mock_wb.VBProject = mock_vb
        mock_app.ActiveWorkbook = mock_wb

        adapter._app = mock_app
        adapter._app_type = "excel"

        with patch("src.adapters.office_com.logger") as mock_logger:
            adapter._check_vba_macros()
            mock_logger.warning.assert_not_called()

    def test_vba_check_handles_access_denied(self, adapter):
        """_check_vba_macros handles VBProject access being restricted."""
        mock_app = MagicMock()
        mock_wb = MagicMock()
        type(mock_wb).VBProject = PropertyMock(side_effect=Exception("Access denied"))
        mock_app.ActiveWorkbook = mock_wb

        adapter._app = mock_app
        adapter._app_type = "excel"

        # Should not raise
        adapter._check_vba_macros()


class TestParseCellReference:
    """Tests for _parse_cell_reference."""

    def test_simple_cell(self):
        sheet, ref = OfficeCOMAdapter._parse_cell_reference("A1")
        assert sheet == ""
        assert ref == "A1"

    def test_sheet_qualified(self):
        sheet, ref = OfficeCOMAdapter._parse_cell_reference("Sheet1!B2:C5")
        assert sheet == "Sheet1"
        assert ref == "B2:C5"

    def test_sheet_with_spaces(self):
        sheet, ref = OfficeCOMAdapter._parse_cell_reference("My Sheet!D4")
        assert sheet == "My Sheet"
        assert ref == "D4"
