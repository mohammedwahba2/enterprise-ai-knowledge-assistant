// RTL guard (approved design decision): Tailwind physical-direction utilities are banned.
const physical =
  "(^|[\\s:])(ml|mr|pl|pr|left|right|text-left|text-right|float-left|float-right|rounded-l|rounded-r|rounded-tl|rounded-tr|rounded-bl|rounded-br|border-l|border-r|scroll-ml|scroll-mr|scroll-pl|scroll-pr)(-|\\s|$)";
export const rtlGuard = {
  "no-restricted-syntax": [
    "error",
    {
      selector: `Literal[value=/${physical}/]`,
      message: "Use logical utilities (ms-/me-/ps-/pe-/start-/end-/text-start/text-end/border-s/border-e/rounded-s/rounded-e) for RTL support.",
    },
    {
      selector: `TemplateElement[value.raw=/${physical}/]`,
      message: "Use logical utilities (ms-/me-/ps-/pe-/start-/end-/text-start/text-end/border-s/border-e/rounded-s/rounded-e) for RTL support.",
    },
  ],
};

