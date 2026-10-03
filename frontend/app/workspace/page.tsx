import type { Metadata } from "next";
import EvidenceWorkspace from "../../components/workspace";

export const metadata: Metadata = {
  title: "Influence · Evidence workspace",
  description: "The first brief's GDPR amendment workspace and the text comparison tool.",
};

export default function WorkspacePage() {
  return <EvidenceWorkspace />;
}
