# Optional EmbeddingGemma model

Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms

EmbeddingGemma is a Google model. Uoink downloads the Q8 ONNX conversion from
onnx-community/embeddinggemma-300m-ONNX, revision
5090578d9565bb06545b4552f76e6bc2c93e4a66. The converted weights are a modification
of the original model; Uoink does not modify that conversion. Weights are not
included in the installer, MCPB bundle or DMG. Their Gemma license is separate
from Uoink's MIT license.

Before downloading this model, the user must explicitly accept the Gemma Terms
of Use and their incorporated Prohibited Use Policy. Use is subject to those terms,
including their use restrictions. Copies of both documents are included here.

Sources:
- https://ai.google.dev/gemma/terms
- https://ai.google.dev/gemma/prohibited_use_policy
- https://huggingface.co/google/embeddinggemma-300m
- https://huggingface.co/onnx-community/embeddinggemma-300m-ONNX

Checked on 2026-10-21: both current Hugging Face model cards still identify the
license as Gemma and link the Google Gemma terms. The copies here are ported
unchanged from the 2026-09-23 prototype evidence: terms dated April 1, 2026 and
policy dated February 21, 2024. This check confirms the model-card license and
terms link; it is not a fresh comparison of the Google-hosted legal text.
