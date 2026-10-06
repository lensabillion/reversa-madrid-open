import { redirect } from "next/navigation";

/** The Atlas's readers start at the lineage explorer. */
export default function HomePage() {
  redirect("/lineage");
}
