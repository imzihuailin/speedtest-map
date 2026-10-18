# Local validation

Validated on 2026-10-18, with the final **map-free** implementation.

## Host

- Omarchy 4.0.5-1
- Quickshell 0.3.2, revision `2b4501a282689792b62e94f3fb30d8f512324fe6`
- Qt 6.12.0
- Ookla Speedtest CLI 1.2.0.84, separately installed at `~/.local/bin/speedtest`
- Ethernet with the existing FlClash TUN routing

## Passed

- 11 Python unit tests: source-link installation, repeated install, moved source,
  conflict preservation, activation rollback, original disabled-state recovery,
  later replacement preservation, standard-checkout backup removal, read-only
  settings, executable paths with spaces and rejection of Python speedtest-cli.
- JavaScript model assertions: bytes/s to Mbps, invalid rates, live stages,
  final-result latching, incomplete results and every completion-event ordering.
- Four actual QML integration cases with a synthetic CLI: fragmented JSON plus
  a final result without newline, license failure, missing final result and
  mid-test close. No CLI process remained alive after any case. These tests
  use isolated settings and make no network requests.
- Omarchy manifest validation and Python compilation.
- On the real desktop: source-linked install, uninstall with the original
  `omarchy.speedtest` enabled again, reinstall, repeat install, original-ID
  routing and QML hard reload through the plugin hook. The actual developer
  watcher was also exercised: a source timestamp change reset the running
  synthetic panel, and Ctrl+C closed it cleanly.
- Final real test invoked through `omarchy.speedtest`: live download/upload,
  final **117.516288 Mbps down / 11.220552 Mbps up**, provider **DMIT**, server
  **Uniti**. These values describe one run, not a bandwidth guarantee.
- Purely synthetic preview generated without capturing desktop contents.

## Coverage limits

- Physical Wi-Fi switching, other monitor sizes/scales and other proxy routes
  have not been exercised on this machine. No interface name is hard-coded.
- A public Marketplace installation has not been attempted. The source layout
  validates and the standard-checkout recovery path is covered in isolation.
