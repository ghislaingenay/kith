import { cn } from "@/lib/utils";

/** Kith's small hand-drawn line art, in palette tokens. Purely decorative:
 * hidden from assistive technology, so pages must say everything in text. */

export function StackedPages({ className }: { readonly className?: string }) {
  return (
    <svg
      viewBox="0 0 96 80"
      aria-hidden="true"
      focusable="false"
      fill="none"
      strokeWidth="1.5"
      strokeLinejoin="round"
      strokeLinecap="round"
      className={cn("h-20 w-24 stroke-muted-foreground", className)}
    >
      <rect x="32" y="4" width="48" height="62" rx="2" className="fill-card" />
      <rect x="25" y="9" width="48" height="62" rx="2" className="fill-card" />
      <rect x="18" y="14" width="48" height="62" rx="2" className="fill-card" />
      <path d="M26 32h22M26 39h30M26 46h30M26 53h30M26 60h18" />
      <path d="M50 14v18l4-4 4 4V14" className="fill-primary stroke-primary" />
    </svg>
  );
}

export function BookmarkRibbon({ className }: { readonly className?: string }) {
  return (
    <svg
      viewBox="0 0 16 24"
      aria-hidden="true"
      focusable="false"
      strokeWidth="1.5"
      strokeLinejoin="round"
      className={cn("h-6 w-4 fill-primary stroke-primary", className)}
    >
      <path d="M3 1h10v21l-5-5-5 5z" />
    </svg>
  );
}
