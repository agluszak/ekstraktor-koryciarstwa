from __future__ import annotations

from typing import NewType

AssessmentId = NewType("AssessmentId", str)
ArgumentBindingCandidateId = NewType("ArgumentBindingCandidateId", str)
CandidateRetrievalProposalId = NewType("CandidateRetrievalProposalId", str)
DocumentId = NewType("DocumentId", str)
EntityCandidateId = NewType("EntityCandidateId", str)
EventCandidateId = NewType("EventCandidateId", str)
EvidenceId = NewType("EvidenceId", str)
FactCandidateId = NewType("FactCandidateId", str)
InferenceFactorId = NewType("InferenceFactorId", str)
InferenceComponentId = NewType("InferenceComponentId", str)
InferenceStateId = NewType("InferenceStateId", str)
InferenceVariableId = NewType("InferenceVariableId", str)
MentionId = NewType("MentionId", str)
ProducerId = NewType("ProducerId", str)
ResolutionClaimId = NewType("ResolutionClaimId", str)
ScorerId = NewType("ScorerId", str)
SentenceId = NewType("SentenceId", str)
SignalId = NewType("SignalId", str)
TokenId = NewType("TokenId", str)
