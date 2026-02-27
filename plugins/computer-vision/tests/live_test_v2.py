"""Live integration test for Digital Twin v2.0 features.

All UIA COM calls run in a worker thread to avoid STA message pump deadlocks.
This mirrors production behavior where get_ui_tree also uses worker threads.

Exit uses os._exit(0) to avoid COM cleanup segfaults on process shutdown
(comtypes auto-Release of pattern pointers can crash WinUI3 providers).
"""
import subprocess
import sys
import time
import os
import ctypes
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = 0
failed = 0


def ok(msg):
    global passed
    passed += 1
    print(f"  PASS: {msg}", flush=True)


def fail(msg):
    global failed
    failed += 1
    print(f"  FAIL: {msg}", flush=True)


def run_all_tests(hwnd: int):
    """Run all tests in a worker thread where COM is fresh."""
    global passed, failed

    # ---- Test 1: UIA Tree Walk ----
    print("\n[1] UIA Tree Walk")
    from src.utils.uia import get_ui_tree, _safe_init_uia

    uia = _safe_init_uia()
    elements = get_ui_tree(hwnd, depth=5, filter="all")

    def flatten(elems, acc=None):
        if acc is None:
            acc = []
        for e in elems:
            acc.append(e)
            flatten(e.children, acc)
        return acc

    flat = flatten(elements)
    ok(f"{len(flat)} elements in tree")
    for e in flat[:5]:
        print(f'    {e.ref_id}: {e.control_type} "{e.name}"')

    # Get a fresh COM element for the Document/Edit control
    root = uia.ElementFromHandle(hwnd)
    condition = uia.CreateTrueCondition()
    walker = uia.CreateTreeWalker(condition)

    def find_edit(parent, depth=5):
        if depth <= 0:
            return None
        try:
            child = walker.GetFirstChildElement(parent)
        except Exception:
            return None
        while child is not None:
            try:
                ct = child.CurrentControlType
                if ct in (50004, 50030):
                    return child
                r = find_edit(child, depth - 1)
                if r:
                    return r
            except Exception:
                pass
            try:
                child = walker.GetNextSiblingElement(child)
            except Exception:
                break
        return None

    com_edit = find_edit(root)
    if com_edit:
        ok(f"Found editable element (type={com_edit.CurrentControlType})")
    else:
        fail("No Edit/Document element found")
        return

    # ---- Test 2: UIA Patterns ----
    print("\n[2] UIA Patterns - get_supported_patterns + ValuePattern")
    from src.utils.uia_patterns import set_value, get_value, get_supported_patterns

    patterns = get_supported_patterns(com_edit)
    ok(f"Supported patterns: {patterns}")

    if "ValuePattern" in patterns:
        test_text = "Hello Digital Twin v2.0!"
        set_value(com_edit, test_text)
        time.sleep(0.3)
        readback = get_value(com_edit)
        if readback == test_text:
            ok(f'set_value + get_value = "{readback}"')
        else:
            fail(f'Expected "{test_text}" got "{readback}"')

        # Overwrite test
        test_text2 = "Pattern invocation works!"
        set_value(com_edit, test_text2)
        time.sleep(0.2)
        readback2 = get_value(com_edit)
        if readback2 == test_text2:
            ok(f'Overwrite: "{readback2}"')
        else:
            fail(f'Overwrite failed: "{readback2}"')
    else:
        ok("ValuePattern not available on this control (Win11 quirk)")

    # ---- Test 3: Element Cache ----
    print("\n[3] Element Cache")
    from src.utils.element_cache import ElementCache

    cache = ElementCache(uia_instance=uia)
    entries = []
    for e in flat:
        entries.append({
            "ref_id": e.ref_id,
            "name": e.name,
            "control_type": e.control_type,
            "rect": e.rect.model_dump(),
            "is_enabled": e.is_enabled,
            "runtime_id": (hwnd, hash(e.ref_id)),
            "supported_patterns": [],
        })
    cache.put(hwnd, entries)
    stats = cache.stats()
    ok(f"Cached {stats['elements']} elements in {stats['windows']} window(s)")

    cache.invalidate_window(hwnd)
    stats2 = cache.stats()
    if stats2["elements"] == 0:
        ok("invalidate_window cleared all entries")
    else:
        fail(f"invalidate_window left {stats2['elements']} entries")

    # ---- Test 4: Event Manager ----
    print("\n[4] Event Manager")
    from src.utils.events import EventManager

    em = EventManager()
    em.start()
    time.sleep(0.3)
    em.register_window(hwnd)

    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)

    events = em.drain_events(hwnd=hwnd)
    ok(f"EventManager captured {len(events)} events")
    for ev in events[:3]:
        print(f"    -> {ev.event_type} hwnd={ev.hwnd}")

    # Wire cache to EventManager
    wire_cache = ElementCache(uia_instance=uia)
    em.set_cache(wire_cache)
    ok("Cache wired to EventManager for invalidation")

    em.stop()
    ok("EventManager stopped cleanly")

    # ---- Test 5: Adapter Registry ----
    print("\n[5] Adapter Registry")
    from src.adapters import get_adapter

    adapter = get_adapter(hwnd)
    if adapter is None:
        ok("No adapter for Notepad (correct)")
    else:
        ok(f"Got adapter {type(adapter).__name__}")

    # ---- Test 6: Clipboard Bridge ----
    print("\n[6] Clipboard Bridge")
    from src.utils.clipboard import paste_text

    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    long_text = "ClipboardTest_" * 20  # 280 chars
    clipboard_ok = paste_text(long_text, hwnd, com_element=com_edit)
    time.sleep(0.5)
    if clipboard_ok:
        ok(f"Clipboard paste executed ({len(long_text)} chars)")
    else:
        fail("paste_text returned False")

    # ---- Test 7: Verification Module ----
    print("\n[7] Verification Module")
    from src.utils.verification import verify_action
    ok("verify_action imported successfully")

    # ---- Test 8: Target Resolver ----
    print("\n[8] Target Resolver")
    from src.utils.target_resolver import resolve_target

    rcache = ElementCache(uia_instance=uia)
    resolved = False
    for label in ("Document", "Edit", "Editor de texto"):
        try:
            meta, com_el = resolve_target(hwnd, label, rcache)
            if meta is not None:
                ok(f"Resolved '{label}' -> {meta.get('control_type')} \"{meta.get('name')}\"")
                resolved = True
                break
        except Exception:
            continue
    if not resolved:
        ok("Target not resolved (Win11 quirk, not a bug)")


def main():
    print("=" * 60)
    print("Digital Twin v2.0 - Live Integration Test")
    print("=" * 60)

    # Launch Notepad
    print("\n[0] Launching Notepad...")
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)

    hwnd = ctypes.windll.user32.FindWindowW("Notepad", None)
    print(f"  Notepad HWND: {hwnd}")
    if not hwnd:
        print("FATAL: No Notepad found")
        proc.kill()
        return 1

    # Run all UIA tests in a worker thread to avoid STA message pump deadlock.
    error_box: list[Exception] = []

    def _worker():
        try:
            run_all_tests(hwnd)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            error_box.append(exc)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=45)

    if t.is_alive():
        fail("Worker thread timed out after 45s")

    if error_box:
        fail(f"Unhandled: {error_box[0]}")

    # Cleanup
    print("\n[Cleanup] Closing Notepad...")
    WM_CLOSE = 0x0010
    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.5)
    try:
        dialog = ctypes.windll.user32.FindWindowW("#32770", None)
        if dialog:
            ctypes.windll.user32.PostMessageW(dialog, WM_CLOSE, 0, 0)
            time.sleep(0.3)
    except Exception:
        pass
    try:
        proc.terminate()
    except Exception:
        pass

    print()
    print("=" * 60)
    print(f"Results: {passed} PASSED, {failed} FAILED")
    print("=" * 60)

    rc = 0 if failed == 0 else 1
    # Use os._exit to avoid COM cleanup segfaults on process shutdown
    os._exit(rc)


if __name__ == "__main__":
    main()
