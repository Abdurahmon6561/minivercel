import { ArrowDown, FileArchive, Upload } from "lucide-react";

/**
 * Four micro-illustrations for the features grid.
 *
 * They speak SitePreview's language rather than a decorative one: the same
 * borders, the same surface/surface-sunken pairing, the same mono for machine
 * text, and the real status tokens the dashboard uses for Ready, Building and
 * Failed. Nothing here is drawn - it is the product's own furniture at a small
 * size, so a reader recognises the screens before they ever sign in.
 *
 * Built from DOM and existing utilities instead of SVG. There is no new CSS to
 * compile and no path data to ship, which is what keeps four illustrations
 * inside a sub-kilobyte budget.
 *
 * All four are aria-hidden. Each sits directly above a title and a sentence
 * that say the same thing in words, so exposing them would only make a screen
 * reader announce "sk" followed by eight bullets.
 */

/** Shared frame, so the four graphics align across the row. */
function Frame({ children, dashed = false }: { children: React.ReactNode; dashed?: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={`relative flex h-36 flex-col justify-center gap-2 overflow-hidden rounded-lg border bg-surface-sunken p-3 ${
        dashed ? "items-center border-dashed border-border-strong" : "border-border"
      }`}
    >
      {children}
    </div>
  );
}

/** One row of product furniture: mono identifier on the left, status on the right. */
function Row({ mono, children }: { mono: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface px-2.5 py-2">
      <span className="font-mono text-[11px] text-text">{mono}</span>
      {children}
    </div>
  );
}

function Badge({ tone, children }: { tone: "success" | "warning" | "destructive"; children: React.ReactNode }) {
  const tones = {
    success: "bg-success-subtle text-success-subtle-fg",
    warning: "bg-warning-subtle text-warning-subtle-fg",
    destructive: "bg-destructive-subtle text-destructive-subtle-fg",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${tones[tone]}`}>{children}</span>
  );
}

/** Zip upload: a drop target with the file already over it. */
export function ZipDropGraphic() {
  return (
    <Frame dashed>
      <div className="flex flex-col items-center gap-1.5 text-muted">
        <Upload className="size-5" />
        <span className="text-[11px]">Drop to deploy</span>
      </div>
      {/* Tilted and shadowed so it reads as held above the zone, not placed in it. */}
      <div className="absolute right-3 bottom-3 flex rotate-[-6deg] items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 shadow-md">
        <FileArchive className="size-3 text-accent" />
        <span className="font-mono text-[11px] text-text">site.zip</span>
      </div>
    </Frame>
  );
}

/** GitHub auto-deploy: three pushes, three outcomes. */
export function CommitStripGraphic() {
  return (
    <Frame>
      <Row mono="7d36a4e">
        <Badge tone="success">Ready</Badge>
      </Row>
      <Row mono="4a91f2c">
        <Badge tone="warning">Building</Badge>
      </Row>
      <Row mono="b02e5d8">
        <Badge tone="destructive">Failed</Badge>
      </Row>
    </Frame>
  );
}

/**
 * Rollback: two deploys, and Live sitting on the older one.
 *
 * The arrow is the whole point - a static pair would only show two deploys.
 * Pointing down, from the newer deploy to the older one wearing the Live badge,
 * is what makes it read as "this moved back".
 */
export function RollbackGraphic() {
  return (
    <Frame>
      <Row mono="9f2c1ab">
        <span className="text-[10px] text-muted">2 min ago</span>
      </Row>
      <ArrowDown className="mx-auto size-4 shrink-0 text-muted" />
      <div className="flex items-center justify-between gap-2 rounded-md border border-success bg-surface px-2.5 py-2">
        <span className="font-mono text-[11px] text-text">4a91f2c</span>
        <span className="flex items-center gap-1.5 rounded-full bg-success-subtle px-2 py-0.5 text-[10px] font-medium text-success-subtle-fg">
          <span className="size-1.5 rounded-full bg-success" />
          Live
        </span>
      </div>
    </Frame>
  );
}

/**
 * Environment variables: keys visible, values not.
 *
 * The masking is the product's actual behaviour, not a stylistic choice - the
 * values are write-only and Dropbin cannot show them back. Drawing them
 * unmasked here would advertise a feature that does not exist.
 */
export function EnvKeysGraphic() {
  return (
    <Frame>
      {[
        ["API_KEY", "sk••••••••"],
        ["DATABASE_URL", "po••••••••"],
        ["STRIPE_SECRET", "sk••••••••"],
      ].map(([key, masked]) => (
        <Row key={key} mono={key}>
          <span className="font-mono text-[11px] text-muted">{masked}</span>
        </Row>
      ))}
    </Frame>
  );
}
