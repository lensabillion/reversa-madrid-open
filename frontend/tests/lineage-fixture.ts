import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { LineageView } from "../lib/lineage-api";

/** Written by backend/tests/test_lineage_views.py from a collected, invented test world. */
export function fixtureView(): LineageView {
  return JSON.parse(
    readFileSync(resolve(process.cwd(), "../backend/tests/fixtures/lineage/view.json"), "utf8"),
  ) as LineageView;
}
