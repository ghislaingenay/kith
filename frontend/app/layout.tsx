import type { Metadata } from "next";
import { IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "./providers";
import { Toaster } from "@/components/ui/sonner";

// Serif for reading text and headings, sans for the interface, mono for metadata.
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
});

// Self-hosted: on CI runners Google serves IBM Plex Sans in a form Turbopack
// can't resolve ("next/font/google queries have exactly one entry"), which
// broke the image build intermittently. One variable file covers 400–600.
const plexSans = localFont({
  variable: "--font-plex-sans",
  src: "./fonts/ibm-plex-sans-latin.woff2",
  weight: "400 600",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Kith",
  description: "Search and ask your team's documents.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sourceSerif.variable} ${plexSans.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>
          {children}
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
