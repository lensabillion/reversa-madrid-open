"""Browse historical evidence without turning incomplete observations into win rates."""

from collections import defaultdict

from pydantic import ValidationError

from influence.repositories.lobbyplag import DemoRepository, RawAmendment, RawCandidate, RawText
from influence.schemas.demo import (
    AmendmentDetail,
    AmendmentPage,
    AmendmentSummary,
    DatasetOverview,
    GraphEdge,
    GraphNode,
    InfluenceGraph,
    OrganizationPage,
    OrganizationSummary,
    SourceMatch,
    SourceText,
)
from influence.schemas.scoring import ScoreRequest, ScoreResult, TextChange
from influence.services.scoring import score_pair

SOURCE_URL = "https://github.com/lobbyplag/lobbyplag-data"
COVERAGE_NOTE = (
    "Historical LobbyPlag GDPR candidate coverage is incomplete. Verified links record volunteer "
    "verification; other candidates remain unverified, not rejected. Counts do not establish "
    "causation, adoption, or organization win rates. Computed scores are separate "
    "from verification."
)
SOURCE_LIMIT = 20


def _text(text: RawText) -> SourceText:
    return SourceText(language=text.lang, old=text.old, new=text.new)


def _amendment_text(amendment: RawAmendment) -> RawText:
    return amendment.text_in("en") or amendment.text[0]


def _score(
    amendment: RawText, submission: RawText, language: str
) -> tuple[ScoreResult | None, str | None]:
    if amendment.lang != "en" or language != "en":
        return None, "The lexical scorer supports English text only."
    try:
        request = ScoreRequest(
            amendment=TextChange(old=amendment.old, new=amendment.new),
            submission=TextChange(old=submission.old, new=submission.new),
        )
    except ValidationError:
        return None, "Text is empty or exceeds the scorer's input limits; source text is preserved."
    return score_pair(request), None


class DemoService:
    def __init__(self, repository: DemoRepository) -> None:
        """Index the roughly 5,000 amendments once; ordering costs O(A log A + C log C)."""
        self.repository = repository
        by_amendment: defaultdict[str, list[RawCandidate]] = defaultdict(list)
        for candidate in repository.candidates.values():
            by_amendment[candidate.amendment].append(candidate)
        self._candidates = {
            key: tuple(sorted(value, key=lambda candidate: (not candidate.verified, candidate.uid)))
            for key, value in by_amendment.items()
        }
        self._summaries = tuple(
            self._summary(amendment)
            for amendment in sorted(
                repository.amendments.values(),
                key=lambda amendment: (amendment.committee, amendment.number, amendment.uid),
            )
        )

    def _summary(self, amendment: RawAmendment) -> AmendmentSummary:
        candidates = self._candidates.get(amendment.uid, ())
        return AmendmentSummary(
            id=amendment.uid,
            committee=amendment.committee,
            number=amendment.number,
            authors=amendment.authors,
            relations=amendment.relations,
            candidate_links=len(candidates),
            verified_links=sum(candidate.verified for candidate in candidates),
        )

    def overview(self) -> DatasetOverview:
        repository = self.repository
        return DatasetOverview(
            amendments=len(repository.amendments),
            proposals=len(repository.proposals),
            documents=len(repository.documents),
            organizations=len(repository.organizations),
            candidate_links=len(repository.candidates),
            duplicate_candidate_rows=repository.duplicate_candidate_rows,
            verified_links=sum(candidate.verified for candidate in repository.candidates.values()),
            source_url=SOURCE_URL,
            coverage_note=COVERAGE_NOTE,
        )

    def list_amendments(
        self, query: str, offset: int, limit: int, verified_only: bool
    ) -> AmendmentPage:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("offset must be nonnegative and limit must be between 1 and 100")
        terms = query.casefold().split()
        matches = tuple(
            item
            for item in self._summaries
            if (not verified_only or item.verified_links > 0)
            and all(
                term in f"{item.committee} {item.number} {' '.join(item.authors)}".casefold()
                for term in terms
            )
        )
        return AmendmentPage(
            items=matches[offset : offset + limit], total=len(matches), offset=offset, limit=limit
        )

    def amendment(self, amendment_id: str) -> AmendmentDetail:
        amendment = self.repository.amendment(amendment_id)
        text = _amendment_text(amendment)
        candidates = self._candidates.get(amendment_id, ())
        sources: list[SourceMatch] = []
        for candidate in candidates[:SOURCE_LIMIT]:
            proposal = self.repository.proposals[candidate.proposal]
            document = self.repository.documents[proposal.doc_uid]
            organization = self.repository.organization_for(proposal)
            score, score_unavailable_reason = _score(text, proposal.text, document.lang)
            sources.append(
                SourceMatch(
                    candidate_id=candidate.uid,
                    proposal_id=proposal.uid,
                    organization_id=organization.id,
                    organization=organization.title,
                    document_id=document.uid,
                    document=document.filename,
                    page=proposal.page,
                    text=SourceText(
                        language=document.lang, old=proposal.text.old, new=proposal.text.new
                    ),
                    historically_verified=candidate.verified,
                    score=score,
                    score_unavailable_reason=score_unavailable_reason,
                )
            )
        return AmendmentDetail(
            amendment=self._summary(amendment),
            text=_text(text),
            sources=tuple(sources),
            total_sources=len(candidates),
            coverage_note=COVERAGE_NOTE,
        )

    def graph(self, amendment_id: str) -> InfluenceGraph:
        """Return a local graph in O(C + N log N), at most the snapshot's 1,976 candidates."""
        amendment = self.repository.amendment(amendment_id)
        center = f"amendment:{amendment.uid}"
        nodes = {
            center: GraphNode(
                id=center,
                kind="amendment",
                label=f"{amendment.committee.upper()} {amendment.number}",
            )
        }
        edges: dict[tuple[str, str], GraphEdge] = {}
        for author in amendment.authors:
            node_id = f"author:{author}"
            nodes[node_id] = GraphNode(id=node_id, kind="author", label=author)
            edges[node_id, center] = GraphEdge(source=node_id, target=center, kind="authored")
        for candidate in self._candidates.get(amendment_id, ()):
            if candidate.verified:
                proposal = self.repository.proposals[candidate.proposal]
                organization = self.repository.organization_for(proposal)
                node_id = f"organization:{organization.id}"
                nodes[node_id] = GraphNode(
                    id=node_id, kind="organization", label=organization.title
                )
                edges[node_id, center] = GraphEdge(
                    source=node_id, target=center, kind="historically_verified"
                )
        return InfluenceGraph(
            amendment_id=amendment_id,
            nodes=tuple(nodes[key] for key in sorted(nodes)),
            edges=tuple(edges[key] for key in sorted(edges)),
            coverage_note=COVERAGE_NOTE,
        )

    def organizations(self) -> OrganizationPage:
        """Aggregate recorded coverage in O(P + C + O log O), for 44 source organizations."""
        proposal_counts: defaultdict[str, int] = defaultdict(int)
        link_counts: defaultdict[str, int] = defaultdict(int)
        amendment_ids: defaultdict[str, set[str]] = defaultdict(set)
        for proposal in self.repository.proposals.values():
            organization = self.repository.organization_for(proposal)
            proposal_counts[organization.id] += 1
        for candidate in self.repository.candidates.values():
            if candidate.verified:
                proposal = self.repository.proposals[candidate.proposal]
                organization = self.repository.organization_for(proposal)
                link_counts[organization.id] += 1
                amendment_ids[organization.id].add(candidate.amendment)
        return OrganizationPage(
            items=tuple(
                OrganizationSummary(
                    id=organization.id,
                    name=organization.title,
                    proposals=proposal_counts[organization.id],
                    verified_links=link_counts[organization.id],
                    amendments_echoing=len(amendment_ids[organization.id]),
                )
                for organization in sorted(
                    self.repository.organizations.values(),
                    key=lambda organization: (organization.title.casefold(), organization.id),
                )
            ),
            coverage_note=COVERAGE_NOTE,
        )
