---
type: is
id: is-01m40wbhcnese3yhvjy2rv3fnz
title: Reject future test features and unsupported forecasts
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3yyx3aamcphb4v8hp350npw
created_at: 2026-10-03T12:38:20.821Z
updated_at: 2026-10-03T12:38:20.821Z
---
Main2fbb229 read-only audit reproduced forecast.validate accepting200 synthetic examples with feature observed_at one day AFTER outcome;160 test observations still yielded adequate=True and Brier .0007605. Test-side observed_at is not checked before validation prediction. forecast_ask then accepts that Validation with empty current training history and emits probability0.0 despite missing historical_outcomes. Add test-side cutoff checks, validation/model provenance binding, and no numeric forecast with missing history. Forecast service is not yet wired into Atlas runtime.
