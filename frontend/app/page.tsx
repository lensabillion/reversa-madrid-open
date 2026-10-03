import { redirect } from "next/navigation";

/** The Atlas's readers start at the lineage explorer; the first brief's workspace moved to /workspace. */
export default function HomePage() {
  redirect("/lineage");
}
