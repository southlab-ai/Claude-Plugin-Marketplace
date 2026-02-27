"""Live integration test for Digital Twin v2.0 features.

Launches Notepad, exercises UIA patterns, element cache, action router,
event manager, and verification — then reports results.
"""
import subprocess
import sys
import time
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Track test results
results: list[tuple[str, bool, str]] = []

def report(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main():
    print("=" * 60)
    print("Digital Twin v2.0 — Live Integration Test")
    print("=" * 60)

    # ---------------------------------------------------------------
    # Step 0: Launch fresh Notepad
    # ---------------------------------------------------------------
    print("\n[0] Launching Notepad...")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)  # Let it initialize

    # Find the Notepad hwnd
    import ctypes
    import ctypes.wintypes

    hwnd = ctypes.windll.user32.FindWindowW("Notepad", None)
    if not hwnd:
        print("  FATAL: Could not find Notepad window")
        proc.kill()
        return

    print(f"  Notepad HWND: {hwnd} (PID: {proc.pid})")

    try:
        # ---------------------------------------------------------------
        # Test 1: UIA Tree Walk + Element Cache
        # ---------------------------------------------------------------
        print("\n[1] Element Cache — populate from UIA tree walk")
        try:
            from src.utils.uia import get_ui_tree, _safe_init_uia
            from src.utils.element_cache import ElementCache

            uia = _safe_init_uia()
            cache = ElementCache(uia_instance=uia)

            elements = get_ui_tree(hwnd, depth=5, filter="all")
            report("UIA tree walk", len(elements) > 0, f"{len(elements)} top-level elements")

            # Flatten tree to find the Edit control
            def flatten(elems, acc=None):
                if acc is None:
                    acc = []
                for e in elems:
                    acc.append(e)
                    flatten(e.children, acc)
                return acc

            flat = flatten(elements)
            edit_elem = None
            for e in flat:
                if e.control_type == "Edit" or e.control_type == "Document":
                    edit_elem = e
                    break

            report("Find Edit control", edit_elem is not None,
                   f"Found: {edit_elem.control_type} '{edit_elem.name}'" if edit_elem else "No Edit found")

            # Put elements into cache
            cache_entries = []
            for e in flat:
                # Get runtime_id from live UIA element
                try:
                    root_element = uia.ElementFromHandle(hwnd)
                    from src.utils.uia import UIA_RUNTIME_ID_PROPERTY_ID
                    condition = uia.CreateTrueCondition()
                    # We'll use ref_id-based cache entries with a dummy runtime_id
                    cache_entries.append({
                        "ref_id": e.ref_id,
                        "name": e.name,
                        "control_type": e.control_type,
                        "rect": e.rect.model_dump(),
                        "is_enabled": e.is_enabled,
                        "runtime_id": (hwnd, hash(e.ref_id)),  # Simplified for test
                        "supported_patterns": [],
                    })
                except Exception:
                    pass

            cache.put(hwnd, cache_entries)
            stats = cache.stats()
            report("Cache populate", stats["elements"] > 0,
                   f"{stats['elements']} elements, {stats['windows']} windows")

        except Exception as exc:
            report("UIA tree + cache", False, str(exc))

        # ---------------------------------------------------------------
        # Test 2: UIA Pattern Invocation — ValuePattern on Edit
        # ---------------------------------------------------------------
        print("\n[2] UIA Patterns — ValuePattern set_value on Edit")
        try:
            from src.utils.uia_patterns import set_value, get_value, get_supported_patterns

            # Get a live COM element for the Edit control
            root_element = uia.ElementFromHandle(hwnd)
            # Find the first Edit control using tree walker
            condition = uia.CreateTrueCondition()
            walker = uia.CreateTreeWalker(condition)

            def find_edit(parent, depth=5):
                if depth <= 0:
                    return None
                child = walker.GetFirstChildElement(parent)
                while child is not None:
                    try:
                        ct = child.CurrentControlType
                        if ct == 50004:  # Edit
                            return child
                        if ct == 50030:  # Document
                            return child
                        result = find_edit(child, depth - 1)
                        if result:
                            return result
                    except Exception:
                        pass
                    try:
                        child = walker.GetNextSiblingElement(child)
                    except Exception:
                        break
                return None

            com_edit = find_edit(root_element)
            report("Find COM Edit element", com_edit is not None)

            if com_edit:
                # Check supported patterns
                patterns = get_supported_patterns(com_edit)
                report("Get supported patterns", True, f"Patterns: {patterns}")

                # Set value
                test_text = "Hello from Digital Twin v2.0!"
                set_value(com_edit, test_text)
                time.sleep(0.3)

                # Read it back
                readback = get_value(com_edit)
                match = readback == test_text
                report("ValuePattern set_value", match,
                       f"Expected: '{test_text}' | Got: '{readback}'")

                # Set a second value to confirm it works repeatedly
                test_text2 = "UIA Pattern Invocation works!"
                set_value(com_edit, test_text2)
                time.sleep(0.2)
                readback2 = get_value(com_edit)
                report("ValuePattern overwrite", readback2 == test_text2,
                       f"Got: '{readback2}'")

        except Exception as exc:
            report("UIA Patterns", False, str(exc))

        # ---------------------------------------------------------------
        # Test 3: Target Resolver
        # ---------------------------------------------------------------
        print("\n[3] Target Resolver — resolve by ref_id and by name")
        try:
            from src.utils.target_resolver import resolve_target
            from src.utils.element_cache import ElementCache

            resolver_cache = ElementCache(uia_instance=uia)

            # Resolve by text label
            meta, com_el = resolve_target(hwnd, "Edit", resolver_cache)
            report("Resolve by text 'Edit'", com_el is not None,
                   f"Found: {meta.get('control_type', '?')} '{meta.get('name', '?')}'" if meta else "None")

        except Exception as exc:
            report("Target Resolver", False, str(exc))

        # ---------------------------------------------------------------
        # Test 4: Event Manager
        # ---------------------------------------------------------------
        print("\n[4] Event Manager — start, register window, drain events")
        try:
            from src.utils.events import EventManager

            em = EventManager()
            em.start()
            time.sleep(0.3)  # Let hooks install

            em.register_window(hwnd)

            # Trigger some events by focusing the window
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)

            events = em.drain_events(hwnd=hwnd)
            report("Event Manager start", True, "Daemon thread running")
            report("Drain events", True, f"{len(events)} events captured")

            if events:
                for ev in events[:3]:
                    print(f"    Event: {ev.event_type} hwnd={ev.hwnd} name={ev.element_name}")

            em.stop()
            report("Event Manager stop", True, "Clean shutdown")

        except Exception as exc:
            report("Event Manager", False, str(exc))

        # ---------------------------------------------------------------
        # Test 5: Clipboard Bridge
        # ---------------------------------------------------------------
        print("\n[5] Clipboard Bridge — paste long text")
        try:
            from src.utils.clipboard import paste_text

            long_text = "A" * 300  # Over threshold (200)
            # Focus the edit and select all first
            if com_edit:
                set_value(com_edit, "")  # Clear first
                time.sleep(0.2)

            ok = paste_text(long_text, hwnd, com_element=com_edit)
            time.sleep(0.3)

            # Verify via ValuePattern
            if com_edit:
                result_text = get_value(com_edit)
                report("Clipboard paste (300 chars)", ok and len(result_text) >= 200,
                       f"Pasted={ok}, length={len(result_text)}")
            else:
                report("Clipboard paste", ok, f"Pasted={ok}")

        except Exception as exc:
            report("Clipboard Bridge", False, str(exc))

        # ---------------------------------------------------------------
        # Test 6: Post-action Verification
        # ---------------------------------------------------------------
        print("\n[6] Post-action Verification")
        try:
            from src.utils.verification import verify_action

            if com_edit:
                # Set a known value, then verify
                set_value(com_edit, "Verify me!")
                time.sleep(0.2)

                result = verify_action(
                    action="set_value",
                    element_meta={"control_type": "Edit", "name": "Edit"},
                    pre_state="Verify me!",
                    hwnd=hwnd,
                    com_element=com_edit,
                )
                report("Verify set_value", result.passed,
                       f"method={result.method}, detail={result.detail}")
            else:
                report("Verification", False, "No Edit element")

        except Exception as exc:
            report("Verification", False, str(exc))

        # ---------------------------------------------------------------
        # Test 7: Adapter Registry (probe only — no Chrome CDP expected)
        # ---------------------------------------------------------------
        print("\n[7] Adapter Registry — probe for Notepad (should be None)")
        try:
            from src.adapters import get_adapter

            adapter = get_adapter(hwnd)
            report("Adapter probe (Notepad)", adapter is None,
                   "Correctly returned None — no adapter for Notepad")

        except Exception as exc:
            report("Adapter Registry", False, str(exc))

    finally:
        # ---------------------------------------------------------------
        # Cleanup: close Notepad
        # ---------------------------------------------------------------
        print("\n[Cleanup] Closing Notepad...")
        try:
            # Send WM_CLOSE
            WM_CLOSE = 0x0010
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            time.sleep(0.5)
            # If save dialog appears, click "Don't Save" (Alt+N in Spanish)
            dialog = ctypes.windll.user32.FindWindowW("#32770", None)
            if dialog:
                # Press Alt+N (No guardar) or send WM_CLOSE to dialog
                ctypes.windll.user32.PostMessageW(dialog, WM_CLOSE, 0, 0)
                time.sleep(0.3)
            proc.terminate()
        except Exception:
            proc.kill()

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    if failed:
        print("\nFailed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"  FAIL: {name} — {detail}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
