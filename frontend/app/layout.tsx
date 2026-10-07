import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

const title = "influence";
const description =
  "Experimental wording associations between EU laws, amendments and consultation submissions, with evidence and limitations.";

/**
 * The public origin (for example https://influence.example.org), set by the host so link
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
