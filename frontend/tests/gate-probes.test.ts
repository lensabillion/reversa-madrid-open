// Gate probes: a gate that is switched off or scoped away also passes clean code, so each
// probe feeds the committed configuration a known violation and requires the exact rule
// to reject it.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, beforeAll, describe, expect, test } from "vitest";

/** frontend/: the project whose committed biome.jsonc and tsconfig.json are probed. */
const projectRoot = fileURLToPath(new URL("..", import.meta.url));

/** Exit status and output of one finished tool run. */
interface ToolRun {
  status: number;
  stdout: string;
  stderr: string;
}

/**
 * Run a tool installed in node_modules with the current Node.js binary, so a missing
 * package fails here instead of being downloaded. BIOME_* variables are removed because
 * BIOME_BINARY and BIOME_CONFIG_PATH would point Biome at a different binary or config.
 */
function runLocalTool(scriptPath: string, args: readonly string[]): ToolRun {
  const env: NodeJS.ProcessEnv = { ...process.env };
  for (const name of Object.keys(env)) {
    if (name.startsWith("BIOME_")) {
      delete env[name];
    }
  }
  const result = spawnSync(process.execPath, [path.join(projectRoot, scriptPath), ...args], {
    cwd: projectRoot,
    encoding: "utf8",
    env,
  });
  if (result.error !== undefined) {
    throw result.error;
  }
  if (result.status === null) {
    throw new Error(`${scriptPath} was stopped by signal ${String(result.signal)}`);
  }
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

/** A source file that must break exactly one Biome rule. */
interface BiomeProbe {
  rule: string;
  file: string;
  source: string;
}

const biomeProbes: readonly BiomeProbe[] = [
  {
    rule: "lint/style/useBlockStatements",
    file: "braces.ts",
    source: "export function stop(done: boolean): void {\n  if (done) return;\n}\n",
  },
  {
    rule: "lint/correctness/noUnusedImports",
    file: "unused-import.ts",
    source: 'import { readFileSync } from "node:fs";\n\nexport const answer = 42;\n',
  },
  {
    rule: "lint/correctness/noUnusedVariables",
    file: "unused-variable.ts",
    source: "export function two(): number {\n  const unused = 1;\n  return 2;\n}\n",
  },
  {
    rule: "lint/style/useImportType",
    file: "import-type.ts",
    source: 'import { Metadata } from "next";\n\nexport const metadata: Metadata = {};\n',
  },
  {
    rule: "lint/nursery/noFloatingPromises",
    file: "floating-promise.ts",
    source:
      "async function save(): Promise<void> {}\n\nexport function run(): void {\n  save();\n}\n",
  },
  {
    rule: "lint/nursery/noMisusedPromises",
    file: "misused-promise.ts",
    source:
      "const ready: Promise<boolean> = Promise.resolve(true);\n\n" +
      'export function check(): string {\n  if (ready) {\n    return "yes";\n  }\n  return "no";\n}\n',
  },
  {
    rule: "lint/nursery/useAwaitThenable",
    file: "await-non-promise.ts",
    source: "export async function answer(): Promise<number> {\n  return await 42;\n}\n",
  },
  {
    rule: "assist/source/organizeImports",
    file: "unsorted-imports.ts",
    source:
      'import { join } from "node:path";\nimport { readFileSync } from "node:fs";\n\n' +
      'export const read = (dir: string): string => readFileSync(join(dir, "a"), "utf8");\n',
  },
  {
    // In the recommended preset and named nowhere in biome.jsonc, so it fires only while
    // the preset itself is applied.
    rule: "lint/suspicious/noDoubleEquals",
    file: "double-equals.ts",
    source: "export const same = (a: number, b: number): boolean => a == b;\n",
  },
];

/** Compliant code: the same run must report nothing for it, or a rejection proves nothing. */
const cleanSource =
  "async function save(): Promise<void> {}\n\n" +
  "export async function run(done: boolean): Promise<void> {\n" +
  "  if (done) {\n    return;\n  }\n  await save();\n}\n";

/** Biome's rdjson report (the Reviewdog Diagnostic Format), reduced to the fields read. */
interface RdjsonReport {
  diagnostics: { code: { value: string }; location: { path: string } }[];
}

describe("Biome rejects each floor violation", () => {
  // Biome's stdin mode reports no lint diagnostics, and its type-aware promise rules only
  // analyze files inside the project folder it scans, so the probes are real files in a
  // temporary folder inside frontend/.
  let probeDir = "";
  let run: ToolRun = { status: -1, stdout: "", stderr: "" };
  const rulesByFile = new Map<string, string[]>();

  beforeAll(() => {
    probeDir = mkdtempSync(path.join(projectRoot, "tests", "gate-probe-tmp-"));
    for (const probe of biomeProbes) {
      writeFileSync(path.join(probeDir, probe.file), probe.source);
    }
    writeFileSync(path.join(probeDir, "clean.ts"), cleanSource);

    run = runLocalTool("node_modules/@biomejs/biome/bin/biome", [
      "check",
      "--colors=off",
      "--reporter=rdjson",
      `--config-path=${projectRoot}`,
      path.relative(projectRoot, probeDir),
    ]);
    let report: RdjsonReport;
    try {
      report = JSON.parse(run.stdout);
    } catch {
      throw new Error(`Biome printed no rdjson report. Its stderr:\n${run.stderr}`);
    }
    for (const diagnostic of report.diagnostics) {
      const file = path.basename(diagnostic.location.path);
      rulesByFile.set(file, [...(rulesByFile.get(file) ?? []), diagnostic.code.value]);
    }
  });

  afterAll(() => {
    if (probeDir !== "") {
      rmSync(probeDir, { recursive: true, force: true });
    }
  });

  test("the run fails", () => {
    expect(run.status).toBe(1);
  });

  test.each(biomeProbes)("$rule rejects $file and nothing else fires", ({ rule, file }) => {
    expect(rulesByFile.get(file)).toEqual([rule]);
  });

  test("compliant code passes the same configuration", () => {
    expect(rulesByFile.has("clean.ts")).toBe(false);
  });
});

/** A tsconfig floor flag and the one diagnostic that only that flag produces. */
interface TypeProbe {
  flag: string;
  code: string;
  message: string;
}

const typeProbes: readonly TypeProbe[] = [
  { flag: "strict", code: "TS7006", message: "implicitly has an 'any' type" },
  {
    flag: "noUncheckedIndexedAccess",
    code: "TS2322",
    message: "Type 'number | undefined' is not assignable to type 'number'",
  },
  { flag: "exactOptionalPropertyTypes", code: "TS2375", message: "exactOptionalPropertyTypes" },
  { flag: "noImplicitReturns", code: "TS7030", message: "Not all code paths return a value" },
  { flag: "noFallthroughCasesInSwitch", code: "TS7029", message: "Fallthrough case in switch" },
  { flag: "noImplicitOverride", code: "TS4114", message: "must have an 'override' modifier" },
];

describe("tsc rejects each tsconfig floor violation", () => {
  // tests/probes/tsconfig.json extends the real tsconfig.json and compiles only
  // tests/probes/type-errors.ts, which the real tsconfig.json excludes.
  let run: ToolRun = { status: -1, stdout: "", stderr: "" };
  let errorLines: string[] = [];

  beforeAll(() => {
    run = runLocalTool("node_modules/typescript/bin/tsc", [
      "--project",
      "tests/probes/tsconfig.json",
      "--pretty",
      "false",
    ]);
    errorLines = run.stdout.split("\n").filter((line) => line.includes(": error TS"));
  });

  test("the run fails with one error per probed flag and no other error", () => {
    // A broken probe setup (for example "No inputs were found") also fails the run, but
    // with other errors, so the count and the file are checked too.
    expect(run.status).not.toBe(0);
    expect(errorLines).toHaveLength(typeProbes.length);
    for (const line of errorLines) {
      expect(line.startsWith("tests/probes/type-errors.ts(")).toBe(true);
    }
  });

  test.each(typeProbes)("$flag produces $code", ({ code, message }) => {
    const matches = errorLines.filter(
      (line) => line.includes(`error ${code}:`) && line.includes(message),
    );
    expect(matches).toHaveLength(1);
  });
});
