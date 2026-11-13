const PATHS = {
  ask: "M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z",
  library: "M3 2.5h8a2 2 0 0 1 2 2v9H5a2 2 0 0 1-2-2zM3 11.5a2 2 0 0 1 2-2h8",
  attention: "M8 2.2a5.8 5.8 0 1 0 0 11.6A5.8 5.8 0 0 0 8 2.2zM8 5v3.4M8 10.8v.1",
  collections: "M2 4.5h4l1.2 1.5H14v6.5H2z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" viewBox="0 0 16 16" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
