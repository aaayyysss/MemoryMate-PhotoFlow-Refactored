# services/candidate_builders/__init__.py
# Family-first candidate builders for hybrid retrieval.
#
# Each builder produces a CandidateSet using the right index first:
#   type family     -> OCR/structure retrieval first
#   people_event    -> person/face retrieval first
#   pet family      -> animal evidence first
#   scenic family   -> multimodal semantic retrieval first
#   utility family  -> metadata/state retrieval first

from services.candidate_builders.base_candidate_builder import (
    BaseCandidateBuilder,
    CandidateSet,
)
from services.candidate_builders.document_candidate_builder import (
    DocumentCandidateBuilder,
)
from services.candidate_builders.people_candidate_builder import (
    PeopleCandidateBuilder,
)

# Dispatch map for orchestrator
CANDIDATE_BUILDERS = {
    "type": DocumentCandidateBuilder,
    "people_event": PeopleCandidateBuilder,
    # Future:
    # "scenic": ScenicCandidateBuilder,
    # "animal_object": PetCandidateBuilder,
    # "utility": UtilityCandidateBuilder,
}

__all__ = [
    "BaseCandidateBuilder",
    "CandidateSet",
    "DocumentCandidateBuilder",
    "PeopleCandidateBuilder",
    "CANDIDATE_BUILDERS",
]
