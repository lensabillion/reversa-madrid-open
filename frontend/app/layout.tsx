import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Influence Atlas",
  description:
    "Who shapes EU law: asks traced to amendments and to the final text, with the evidence side by side.",
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
