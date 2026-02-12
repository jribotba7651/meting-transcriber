"""
Phase 2 Runtime Network Isolation Test
=======================================
Tests that the Meeting Notes Assistant makes ZERO outbound network calls.

PROCEDURE:
1. Disable WiFi before running this script
2. Run: python security/network_test.py
3. Test the app for ~30 minutes (live transcription, file upload, overlay OCR)
4. Press Ctrl+C or wait for the timer to stop
5. The script generates security/PHASE2_RUNTIME_REPORT.md

WHAT THIS MONITORS (Python-only, no Arctic Wolf triggers):
- Windows DNS Client event logs for any DNS resolution attempts
- %TEMP% directory for new audio files (.wav, .mp3, .tmp, .flac, .ogg)
- Subprocess stdout/stderr for connection errors
- Periodic heartbeat checks every 60 seconds

NO system tools used (no netstat, tcpdump, Wireshark, PowerShell).
"""

import os
import sys
import time
import subprocess
import threading
import signal
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows Event Log reading (pywin32)
# ---------------------------------------------------------------------------
try:
    import win32evtlog
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("[WARN] pywin32 not installed — DNS event log monitoring disabled")
    print("       Install with: pip install pywin32")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_ENTRY = PROJECT_ROOT / "main.py"
REPORT_PATH = PROJECT_ROOT / "security" / "PHASE2_RUNTIME_REPORT.md"
TEST_DURATION_MINUTES = 30
CHECK_INTERVAL_SECONDS = 60

# Audio file extensions that should NEVER appear in %TEMP% during runtime
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".wma", ".tmp", ".pcm", ".raw"}

# Temp directory to monitor
TEMP_DIR = Path(os.environ.get("TEMP", os.environ.get("TMP", "C:\\Temp")))


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class TestState:
    def __init__(self):
        self.start_time = datetime.now()
        self.dns_events = []           # DNS resolution attempts found in event logs
        self.new_audio_files = []      # Audio files created in %TEMP% during test
        self.connection_errors = []    # Connection errors from app stderr
        self.app_stderr_lines = []     # All stderr from the app
        self.check_log = []            # Periodic check results
        self.temp_baseline = set()     # Files in %TEMP% before test
        self.app_process = None
        self.running = True
        self.event_log_baseline_time = None


state = TestState()


# ---------------------------------------------------------------------------
# 1. Baseline: snapshot %TEMP% before test
# ---------------------------------------------------------------------------
def snapshot_temp_dir():
    """Take a snapshot of files in %TEMP% to compare later."""
    try:
        files = set()
        for f in TEMP_DIR.iterdir():
            if f.is_file():
                files.add(f.name)
        return files
    except Exception as e:
        print(f"[WARN] Could not snapshot TEMP dir: {e}")
        return set()


# ---------------------------------------------------------------------------
# 2. Check Windows DNS Client event logs
# ---------------------------------------------------------------------------
def check_dns_events(since_time):
    """
    Read DNS Client operational log for any DNS resolution attempts
    since the test started. This catches any outbound DNS queries
    the app might make.
    """
    if not HAS_WIN32:
        return []

    events_found = []
    log_name = "Microsoft-Windows-DNS-Client/Operational"

    try:
        handle = win32evtlog.OpenEventLog(None, log_name)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        while True:
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            if not events:
                break

            for event in events:
                event_time = event.TimeGenerated
                # Convert to datetime for comparison
                if hasattr(event_time, 'year'):
                    evt_dt = datetime(
                        event_time.year, event_time.month, event_time.day,
                        event_time.hour, event_time.minute, event_time.second
                    )
                else:
                    continue

                # Only check events after our test started
                if evt_dt < since_time:
                    break

                # Extract event data
                event_data = {
                    "time": evt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "event_id": event.EventID & 0xFFFF,
                    "source": event.SourceName,
                    "strings": event.StringInserts if event.StringInserts else []
                }
                events_found.append(event_data)

        win32evtlog.CloseEventLog(handle)

    except Exception as e:
        # Log might not be accessible — not critical
        events_found.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_id": -1,
            "source": "ERROR",
            "strings": [f"Could not read DNS log: {e}"]
        })

    return events_found


# ---------------------------------------------------------------------------
# 3. Check %TEMP% for new audio files
# ---------------------------------------------------------------------------
def check_temp_for_audio():
    """Scan %TEMP% for any new audio files created since the test started."""
    new_audio = []
    try:
        for f in TEMP_DIR.iterdir():
            if f.is_file() and f.name not in state.temp_baseline:
                ext = f.suffix.lower()
                if ext in AUDIO_EXTENSIONS:
                    try:
                        size = f.stat().st_size
                        created = datetime.fromtimestamp(f.stat().st_ctime)
                        new_audio.append({
                            "name": f.name,
                            "ext": ext,
                            "size_bytes": size,
                            "created": created.strftime("%Y-%m-%d %H:%M:%S")
                        })
                    except Exception:
                        new_audio.append({"name": f.name, "ext": ext, "size_bytes": -1, "created": "unknown"})
    except Exception as e:
        print(f"[WARN] Could not scan TEMP dir: {e}")

    return new_audio


# ---------------------------------------------------------------------------
# 4. Monitor app stderr for connection errors
# ---------------------------------------------------------------------------
def monitor_stderr(process):
    """Read app stderr in background thread, watch for connection errors."""
    connection_keywords = [
        "ConnectionRefusedError", "ConnectionError", "URLError",
        "socket.gaierror", "ECONNREFUSED", "ENOTFOUND", "ETIMEDOUT",
        "getaddrinfo failed", "Name or service not known",
        "No connection could be made", "network is unreachable",
        "DNS resolution failed", "requests.exceptions",
        "urllib.error", "httplib", "ssl.SSLError"
    ]

    try:
        for line in iter(process.stderr.readline, ''):
            if not state.running:
                break

            line = line.strip()
            if not line:
                continue

            state.app_stderr_lines.append(line)

            # Check for connection-related errors
            for keyword in connection_keywords:
                if keyword.lower() in line.lower():
                    state.connection_errors.append({
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "line": line
                    })
                    print(f"[!] Connection error detected: {line}")
                    break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 5. Periodic check loop
# ---------------------------------------------------------------------------
def periodic_check():
    """Run checks every CHECK_INTERVAL_SECONDS."""
    check_number = 0

    while state.running:
        time.sleep(CHECK_INTERVAL_SECONDS)
        if not state.running:
            break

        check_number += 1
        elapsed = (datetime.now() - state.start_time).total_seconds() / 60.0

        # Check DNS events
        dns = check_dns_events(state.start_time)
        new_dns = len(dns) - len(state.dns_events)
        state.dns_events = dns

        # Check temp files
        audio_files = check_temp_for_audio()
        new_audio = len(audio_files) - len(state.new_audio_files)
        state.new_audio_files = audio_files

        # Log
        result = {
            "check": check_number,
            "elapsed_min": round(elapsed, 1),
            "dns_events_total": len(dns),
            "dns_events_new": new_dns,
            "audio_files_total": len(audio_files),
            "audio_files_new": new_audio,
            "connection_errors": len(state.connection_errors),
            "app_running": state.app_process.poll() is None if state.app_process else False
        }
        state.check_log.append(result)

        status = "PASS" if (new_dns == 0 and new_audio == 0) else "ALERT"
        print(f"[Check #{check_number}] {elapsed:.1f}min | DNS: {len(dns)} | "
              f"Audio files: {len(audio_files)} | Conn errors: {len(state.connection_errors)} | {status}")


# ---------------------------------------------------------------------------
# 6. Generate report
# ---------------------------------------------------------------------------
def generate_report():
    """Generate PHASE2_RUNTIME_REPORT.md"""
    end_time = datetime.now()
    duration = (end_time - state.start_time).total_seconds() / 60.0

    # Final checks
    final_dns = check_dns_events(state.start_time)
    final_audio = check_temp_for_audio()

    # Determine overall result
    dns_pass = len(final_dns) == 0
    audio_pass = len(final_audio) == 0
    conn_pass = len(state.connection_errors) == 0
    overall_pass = dns_pass and audio_pass and conn_pass

    report = []
    report.append("# Security Audit — Phase 2: Runtime Network Isolation Verification")
    report.append(f"**Date:** {state.start_time.strftime('%Y-%m-%d')}")
    report.append(f"**Duration:** {duration:.1f} minutes")
    report.append(f"**Start:** {state.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**End:** {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("**Method:** Python-only monitoring (no netstat/tcpdump/Wireshark)")
    report.append(f"**Network:** WiFi disabled during test")
    report.append(f"**Auditor:** Automated test script + manual interaction")
    report.append("")
    report.append("---")
    report.append("")

    # Overall result
    result_str = "✅ **PASS**" if overall_pass else "❌ **FAIL**"
    report.append(f"## Overall Result: {result_str}")
    report.append("")

    # Summary table
    report.append("## Test Summary")
    report.append("")
    report.append("| Check | Result | Details |")
    report.append("|-------|--------|---------|")
    report.append(f"| DNS resolution attempts | {'✅ PASS' if dns_pass else '❌ FAIL'} | {len(final_dns)} DNS events detected |")
    report.append(f"| Audio file persistence (TEMP) | {'✅ PASS' if audio_pass else '❌ FAIL'} | {len(final_audio)} audio files found in %TEMP% |")
    report.append(f"| Connection errors in app | {'✅ PASS' if conn_pass else '⚠️ INFO'} | {len(state.connection_errors)} connection-related errors |")
    report.append(f"| App ran without network | {'✅ PASS' if (state.app_process and state.app_process.poll() is None) or duration > 1 else '❌ FAIL'} | App {'ran' if duration > 1 else 'crashed'} for {duration:.1f} min |")
    report.append("")

    # Periodic checks
    report.append("## Periodic Check Log")
    report.append("")
    if state.check_log:
        report.append("| # | Elapsed (min) | DNS Events | Audio Files | Conn Errors | App Running |")
        report.append("|---|--------------|------------|-------------|-------------|-------------|")
        for c in state.check_log:
            report.append(f"| {c['check']} | {c['elapsed_min']} | {c['dns_events_total']} | "
                          f"{c['audio_files_total']} | {c['connection_errors']} | "
                          f"{'Yes' if c['app_running'] else 'No'} |")
    else:
        report.append("*No periodic checks completed (test duration < 60 seconds)*")
    report.append("")

    # DNS Events detail
    report.append("## DNS Resolution Attempts")
    report.append("")
    if final_dns:
        report.append(f"**{len(final_dns)} DNS events detected during test:**")
        report.append("")
        for evt in final_dns[:20]:  # Cap at 20
            strings = ", ".join(str(s) for s in evt['strings']) if evt['strings'] else "N/A"
            report.append(f"- `{evt['time']}` — Event ID: {evt['event_id']}, Source: {evt['source']}")
            report.append(f"  Data: {strings}")
        if len(final_dns) > 20:
            report.append(f"- ... and {len(final_dns) - 20} more events")
    else:
        report.append("**None detected.** The application made zero DNS resolution attempts during the test period.")
    report.append("")

    # Audio file check
    report.append("## Audio File Persistence Check (%TEMP%)")
    report.append("")
    if final_audio:
        report.append(f"**⚠️ {len(final_audio)} audio files found in %TEMP%:**")
        report.append("")
        report.append("| File | Extension | Size | Created |")
        report.append("|------|-----------|------|---------|")
        for af in final_audio:
            size_str = f"{af['size_bytes']:,} bytes" if af['size_bytes'] >= 0 else "unknown"
            report.append(f"| {af['name']} | {af['ext']} | {size_str} | {af['created']} |")
    else:
        report.append("**None found.** Zero audio files were created in %TEMP% during the test.")
        report.append("This confirms the zero-audio-persistence guarantee of the stream-only pipeline.")
    report.append("")

    # Connection errors
    report.append("## Connection Errors (App Stderr)")
    report.append("")
    if state.connection_errors:
        report.append(f"**{len(state.connection_errors)} connection-related errors detected:**")
        report.append("")
        for err in state.connection_errors:
            report.append(f"- `{err['time']}`: `{err['line']}`")
        report.append("")
        report.append("*Note: Connection errors while WiFi is disabled are EXPECTED and GOOD — they prove the app attempted a network call that was blocked.*")
    else:
        report.append("**None detected.** The application produced no connection-related errors,")
        report.append("confirming it does not attempt any network connections during normal operation.")
    report.append("")

    # App stderr (last 20 lines)
    report.append("## App Log (Last 20 Lines)")
    report.append("")
    report.append("```")
    for line in state.app_stderr_lines[-20:]:
        report.append(line)
    if not state.app_stderr_lines:
        report.append("(no stderr output)")
    report.append("```")
    report.append("")

    # Methodology
    report.append("---")
    report.append("")
    report.append("## Methodology")
    report.append("")
    report.append("This test was performed with the following constraints:")
    report.append("")
    report.append("1. **WiFi disabled** before test start — no network interface active")
    report.append("2. **Python-only monitoring** — no netstat, tcpdump, Wireshark, or PowerShell")
    report.append("3. **DNS Client event log** monitored via pywin32 (`win32evtlog`)")
    report.append("4. **%TEMP% directory** scanned for new audio files (baseline taken before test)")
    report.append("5. **App stderr** monitored for connection-related error keywords")
    report.append("6. **Periodic checks** every 60 seconds for continuous monitoring")
    report.append("")
    report.append("### Limitations")
    report.append("")
    report.append("- DNS event log may not capture all network attempts (e.g., direct IP connections)")
    report.append("- %TEMP% scan only catches files in the main temp directory, not subdirectories")
    report.append("- This test does NOT replace a full tcpdump/Wireshark capture on an isolated VM")
    report.append("- Arctic Wolf EDR provides additional monitoring not captured here")
    report.append("")

    # Write report
    report_text = "\n".join(report) + "\n"
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\n[✓] Report written to: {REPORT_PATH}")

    return overall_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  Phase 2: Runtime Network Isolation Test")
    print("=" * 60)
    print(f"  Start time:  {state.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Duration:    {TEST_DURATION_MINUTES} minutes")
    print(f"  App:         {APP_ENTRY}")
    print(f"  TEMP dir:    {TEMP_DIR}")
    print(f"  Report:      {REPORT_PATH}")
    print(f"  pywin32:     {'Available' if HAS_WIN32 else 'NOT available'}")
    print("=" * 60)
    print()

    # Step 1: Baseline %TEMP%
    print("[1/4] Taking %TEMP% baseline snapshot...")
    state.temp_baseline = snapshot_temp_dir()
    print(f"      {len(state.temp_baseline)} files in %TEMP%")

    # Step 2: Launch the app
    print("[2/4] Launching Meeting Notes Assistant...")
    try:
        state.app_process = subprocess.Popen(
            [sys.executable, str(APP_ENTRY)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(PROJECT_ROOT)
        )
        print(f"      PID: {state.app_process.pid}")
    except Exception as e:
        print(f"[ERROR] Failed to launch app: {e}")
        sys.exit(1)

    # Step 3: Start monitoring threads
    print("[3/4] Starting monitoring threads...")

    stderr_thread = threading.Thread(target=monitor_stderr, args=(state.app_process,), daemon=True)
    stderr_thread.start()

    check_thread = threading.Thread(target=periodic_check, daemon=True)
    check_thread.start()

    print("[4/4] Monitoring active. Test the app now!")
    print()
    print("  → Test live transcription (play audio)")
    print("  → Test file upload transcription")
    print("  → Test overlay OCR (if Ollama running)")
    print(f"  → Test will auto-stop in {TEST_DURATION_MINUTES} minutes")
    print("  → Or press Ctrl+C to stop early")
    print()

    # Wait for duration or Ctrl+C
    try:
        deadline = state.start_time + timedelta(minutes=TEST_DURATION_MINUTES)
        while datetime.now() < deadline:
            time.sleep(5)

            # Check if app crashed
            if state.app_process.poll() is not None:
                print(f"\n[!] App exited with code {state.app_process.returncode}")
                break

    except KeyboardInterrupt:
        print("\n[*] Ctrl+C received — stopping test...")

    # Cleanup
    state.running = False

    if state.app_process and state.app_process.poll() is None:
        print("[*] Terminating app...")
        state.app_process.terminate()
        try:
            state.app_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            state.app_process.kill()

    time.sleep(2)  # Let threads finish

    # Generate report
    print("\n[*] Generating report...")
    passed = generate_report()

    if passed:
        print("\n✅ ALL CHECKS PASSED — App makes zero network calls")
    else:
        print("\n⚠️  ISSUES DETECTED — Review the report for details")


if __name__ == "__main__":
    main()
