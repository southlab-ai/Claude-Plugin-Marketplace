"""Office COM adapter for Excel, Word, and PowerPoint automation."""

from __future__ import annotations

import logging
from typing import Any

from src.adapters import BaseAdapter, AdapterRegistry
from src.models import ActionResult, VerificationResult

logger = logging.getLogger(__name__)

# Office application COM ProgIDs
_OFFICE_PROGIDS = [
    "Excel.Application",
    "Word.Application",
    "PowerPoint.Application",
]


class OfficeCOMAdapter(BaseAdapter):
    """Adapter for Microsoft Office applications via COM automation."""

    def __init__(self) -> None:
        self._app: Any = None
        self._app_type: str = ""

    def probe(self, hwnd: int) -> bool:
        """Try to connect to a running Office application via GetActiveObject.

        Returns True if any Office application is running and accessible.
        Must complete within 500ms.
        """
        try:
            import win32com.client

            for progid in _OFFICE_PROGIDS:
                try:
                    app = win32com.client.GetActiveObject(progid)
                    if app is not None:
                        self._app = app
                        self._app_type = progid.split(".")[0].lower()
                        return True
                except Exception:
                    continue
            return False
        except ImportError:
            logger.info("win32com not available for OfficeCOMAdapter")
            return False
        except Exception as exc:
            logger.debug("OfficeCOMAdapter probe failed: %s", exc)
            return False

    def supports_action(self, action: str) -> bool:
        """Supported actions: set_value, get_value, invoke."""
        return action in ("set_value", "get_value", "invoke")

    def execute(
        self, hwnd: int, target: str, action: str, value: str | None
    ) -> ActionResult:
        """Execute an action on the Office application.

        Args:
            hwnd: Window handle.
            target: Cell reference (e.g., "A1", "Sheet1!B2:C5") or navigation target.
            action: One of set_value, get_value, invoke.
            value: Value for set_value action.
        """
        if not self.supports_action(action):
            return ActionResult(
                success=False,
                strategy_used="adapter_office_com",
                layer=0,
            )

        try:
            # Re-probe to ensure connection
            if self._app is None:
                if not self.probe(hwnd):
                    return ActionResult(
                        success=False,
                        strategy_used="adapter_office_com",
                        layer=0,
                    )

            # Check for VBA macros
            self._check_vba_macros()

            if action == "get_value":
                return self._get_value(target)
            elif action == "set_value":
                return self._set_value(target, value or "")
            elif action == "invoke":
                return self._invoke(target)
            else:
                return ActionResult(
                    success=False, strategy_used="adapter_office_com", layer=0
                )

        except Exception as exc:
            logger.warning("OfficeCOMAdapter.execute failed: %s", exc)
            return ActionResult(
                success=False,
                strategy_used="adapter_office_com",
                layer=0,
            )

    def _check_vba_macros(self) -> None:
        """Check if the active workbook/document has VBA macros and log a warning."""
        try:
            if self._app_type == "excel":
                wb = self._app.ActiveWorkbook
                if wb is not None:
                    try:
                        count = wb.VBProject.VBComponents.Count
                        if count > 0:
                            logger.warning(
                                "Active workbook contains %d VBA component(s). "
                                "Exercise caution when modifying.",
                                count,
                            )
                    except Exception:
                        # VBProject access may be restricted by Trust Center settings
                        pass
            elif self._app_type == "word":
                doc = self._app.ActiveDocument
                if doc is not None:
                    try:
                        count = doc.VBProject.VBComponents.Count
                        if count > 0:
                            logger.warning(
                                "Active document contains %d VBA component(s).",
                                count,
                            )
                    except Exception:
                        pass
        except Exception:
            pass

    def _get_value(self, target: str) -> ActionResult:
        """Read a cell or range value from Excel."""
        try:
            if self._app_type != "excel":
                return ActionResult(
                    success=False,
                    strategy_used="adapter_office_com",
                    layer=0,
                )

            wb = self._app.ActiveWorkbook
            if wb is None:
                return ActionResult(
                    success=False, strategy_used="adapter_office_com", layer=0
                )

            # Parse sheet!range or just range
            sheet, cell_ref = self._parse_cell_reference(target)
            if sheet:
                ws = wb.Sheets(sheet)
            else:
                ws = self._app.ActiveSheet

            rng = ws.Range(cell_ref)
            val = rng.Value

            # Convert COM value to string representation
            if val is None:
                val_str = ""
            elif isinstance(val, tuple):
                # Multi-cell range returns tuple of tuples
                val_str = str(val)
            else:
                val_str = str(val)

            return ActionResult(
                success=True,
                strategy_used="adapter_office_com",
                layer=0,
                verification=VerificationResult(method="none", passed=True),
                element={"value": val_str, "target": target},
            )
        except Exception as exc:
            logger.debug("OfficeCOM get_value failed: %s", exc)
            return ActionResult(
                success=False, strategy_used="adapter_office_com", layer=0
            )

    def _set_value(self, target: str, value: str) -> ActionResult:
        """Write a value to a cell or range in Excel."""
        try:
            if self._app_type != "excel":
                return ActionResult(
                    success=False,
                    strategy_used="adapter_office_com",
                    layer=0,
                )

            wb = self._app.ActiveWorkbook
            if wb is None:
                return ActionResult(
                    success=False, strategy_used="adapter_office_com", layer=0
                )

            sheet, cell_ref = self._parse_cell_reference(target)
            if sheet:
                ws = wb.Sheets(sheet)
            else:
                ws = self._app.ActiveSheet

            rng = ws.Range(cell_ref)
            rng.Value = value

            return ActionResult(
                success=True,
                strategy_used="adapter_office_com",
                layer=0,
                verification=VerificationResult(method="none", passed=True),
                element={"value": value, "target": target},
            )
        except Exception as exc:
            logger.debug("OfficeCOM set_value failed: %s", exc)
            return ActionResult(
                success=False, strategy_used="adapter_office_com", layer=0
            )

    def _invoke(self, target: str) -> ActionResult:
        """Invoke a navigation operation (limited to safe operations)."""
        try:
            # Limited to navigation: go to cell or sheet
            if self._app_type == "excel":
                sheet, cell_ref = self._parse_cell_reference(target)
                if sheet:
                    ws = self._app.ActiveWorkbook.Sheets(sheet)
                    ws.Activate()
                if cell_ref:
                    self._app.ActiveSheet.Range(cell_ref).Select()
            elif self._app_type == "word":
                # Navigate to bookmark or page
                doc = self._app.ActiveDocument
                if doc is not None:
                    try:
                        doc.Bookmarks(target).Select()
                    except Exception:
                        pass

            return ActionResult(
                success=True,
                strategy_used="adapter_office_com",
                layer=0,
                verification=VerificationResult(method="none", passed=True),
            )
        except Exception as exc:
            logger.debug("OfficeCOM invoke failed: %s", exc)
            return ActionResult(
                success=False, strategy_used="adapter_office_com", layer=0
            )

    @staticmethod
    def _parse_cell_reference(target: str) -> tuple[str, str]:
        """Parse a cell reference like 'Sheet1!A1:B2' into (sheet_name, cell_ref).

        Returns ('', target) if no sheet qualifier is present.
        """
        if "!" in target:
            parts = target.split("!", 1)
            return parts[0], parts[1]
        return "", target


# Register with the AdapterRegistry
AdapterRegistry().register(
    ["excel", "winword", "powerpnt"],
    OfficeCOMAdapter,
)
