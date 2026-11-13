import { describe, expect, it } from "vitest";
import stylelint from "stylelint";
import { ESLint } from "eslint";
import { rtlGuard } from "../eslint.rtl-guard.mjs";
import styleConfig from "../stylelint.config.mjs";

async function lintCss(code: string) {
  const r = await stylelint.lint({ code, config: styleConfig as never });
  return r.results[0]!.warnings.map((w) => w.rule);
}

async function lintTsx(code: string) {
  const eslint = new ESLint({
    overrideConfigFile: true,
    overrideConfig: [{ languageOptions: { ecmaVersion: 2022, sourceType: "module" }, rules: rtlGuard }],
  });
  const [res] = await eslint.lintText(code, { filePath: "x.js" });
  return res!.messages.map((m) => m.ruleId);
}

describe("stylelint blocks physical CSS properties", () => {
  it.each([
    "a { margin-left: 1px; }",
    "a { padding-right: 1px; }",
    "a { left: 0; }",
    "a { border-right: 1px solid red; }",
    "a { border-top-left-radius: 2px; }",
    "a { text-align: left; }",
    "a { float: right; }",
  ])("rejects %s", async (css) => {
    expect(await lintCss(`${css}\n`)).toContain(css.includes("text-align") || css.includes("float") ? "declaration-property-value-disallowed-list" : "property-disallowed-list");
  });
  it("allows logical properties", async () => {
    const css = "a {\n  margin-inline-start: 1px;\n  inset-inline-end: 0;\n  text-align: start;\n  border-start-start-radius: 2px;\n}\n";
    expect(await lintCss(css)).toEqual([]);
  });
});

describe("eslint blocks physical Tailwind utilities", () => {
  it.each(['const a = "ml-2";', 'const a = "flex pr-4";', 'const a = "md:text-left";', "const a = `rounded-l-lg ${x}`;"])(
    "rejects %s",
    async (code) => {
      expect(await lintTsx(`const x = 1;\n${code}\n`)).toContain("no-restricted-syntax");
    },
  );
  it("allows logical utilities and unrelated words", async () => {
    expect(await lintTsx('const a = "ms-2 pe-4 text-start border-s leftover-note";\n')).toEqual([]);
  });
});
