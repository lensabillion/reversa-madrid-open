import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Influence Graph",
  description:
    "Scores how likely an EU amendment was written from a lobby submission, maps who wins, and predicts which consultation proposals reach the final law.",
};

/**
 * The `<html>` and `<body>` shared by every route. Colors follow the reader's light or
 * dark system setting; `scheme-light-dark` makes the browser's own surfaces, such as
 * scrollbars and overscroll, follow it too.
 */
export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className="scheme-light-dark">
      <body className="bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">{children}</body>
    </html>
  );
}
