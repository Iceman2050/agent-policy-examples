# Changelog

## 0.1.0 — 2026-11-13

- Initial release. Five versioned example policies (customer refunds,
  outbound payments, vendor bank-detail changes, high-risk database
  writes, task spend envelope), each with ordered rules carrying a
  mandatory human-readable reason per verdict.
- 26 fixture test actions with expected verdicts AND expected deciding
  rules, including the live Agent Auth Gateway Policy Playground verdicts
  for the refunds shape ($12 refund -> REQUIRE_APPROVAL, $25 -> DENY over
  the $20/day hard cap).
- Reference evaluator + CLI runner (standard library only): first-match
  rule ordering, computed projected daily/task totals, `value_field`
  comparisons so an envelope's limit is read from the task itself.
- 15 unit tests, all passing at release.
