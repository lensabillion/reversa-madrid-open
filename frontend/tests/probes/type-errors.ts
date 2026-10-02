// Deliberate type errors: a gate probe, not application code. Each block below is an
// error only because one floor flag in ../../tsconfig.json is on, so the probe fails if
// that flag is removed. The main tsconfig.json excludes this folder;
// tests/gate-probes.test.ts type-checks it through ./tsconfig.json and expects exactly
// these diagnostics.

// strict (noImplicitAny): the parameter has no type.
export function echo(value) {
  return value;
}

// noUncheckedIndexedAccess: the index may be out of range, so the element may be undefined.
const scores: number[] = [0.5];
export const first: number = scores[0];

// exactOptionalPropertyTypes: an optional property may be missing, not set to undefined.
interface Label {
  text?: string;
}
export const label: Label = { text: undefined };

// noImplicitReturns: one path returns a value and the other runs off the end.
export function sign(x: number) {
  if (x > 0) {
    return "positive";
  }
}

// noFallthroughCasesInSwitch: case 0 runs on into case 1.
export function count(n: number): string {
  let words = "";
  switch (n) {
    // biome-ignore lint/suspicious/noFallthroughSwitchClause: the fallthrough is the violation tsc must reject.
    case 0:
      words = "zero";
    case 1:
      words += "one";
      break;
    default:
      words = "many";
  }
  return words;
}

// noImplicitOverride: a method that replaces a base-class method must say `override`.
class Base {
  name(): string {
    return "base";
  }
}
export class Derived extends Base {
  name(): string {
    return "derived";
  }
}
