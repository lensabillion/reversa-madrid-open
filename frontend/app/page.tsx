import { redirect } from "next/navigation";

/** Readers start at the lineage explorer. */
export default function HomePage() {
  redirect("/lineage");
}
