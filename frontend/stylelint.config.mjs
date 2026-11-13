// RTL guard (approved design decision): only logical CSS properties are allowed.
export const physicalPropertyRules = {
  "property-disallowed-list": [
    [
      "left",
      "right",
      "/^(margin|padding|scroll-margin|scroll-padding)-(left|right)$/",
      "/^border-(left|right)(-.+)?$/",
      "/^border-(top|bottom)-(left|right)-radius$/",
      "overflow-x-left",
    ],
    { message: "Use logical properties (inline-start/end, block-start/end) so RTL works." },
  ],
  "declaration-property-value-disallowed-list": [
    { "text-align": ["left", "right"], float: ["left", "right"], clear: ["left", "right"] },
    { message: "Use start/end (or inline-start/inline-end) instead of left/right." },
  ],
};

const config = {
  extends: ["stylelint-config-standard"],
  rules: {
    ...physicalPropertyRules,
    "at-rule-no-unknown": [
      true,
      { ignoreAtRules: ["theme", "source", "utility", "variant", "custom-variant", "plugin", "apply", "config"] },
    ],
    "import-notation": null,
    "custom-property-pattern": null,
    "selector-class-pattern": null,
    "value-keyword-case": null,
    "no-descending-specificity": null,
  },
};

export default config;
