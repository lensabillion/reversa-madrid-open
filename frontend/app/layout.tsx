import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

const title = "Influence Atlas";
const description =
  "Who shapes EU law: asks traced to amendments and to the final text, with the evidence side by side.";

/**
 * The public origin (for example https://atlas.example.org), set by the host so link
 * previews carry absolute URLs. Unset, the key is left out and Next.js uses its own
 * default rather than a guessed address.
 */
const publicUrl = process.env.INFLUENCE_PUBLIC_URL;

export const metadata: Metadata = {
  ...(publicUrl === undefined || publicUrl === "" ? {} : { metadataBase: new URL(publicUrl) }),
  title,
  description,
  openGraph: {
    title,
    description,
    siteName: title,
    type: "website",
    locale: "en",
  },
  twitter: {
    card: "summary",
    title,
    description,
  },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className="scheme-light">
      <body className="bg-[#fcfbf8] font-sans text-stone-900 antialiased selection:bg-teal-100 selection:text-teal-950">
        {children}
      </body>
    </html>
  );
}
