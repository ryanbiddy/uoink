# Safetensors format reference

Consulted 2026-09-13: the upstream [Safetensors README format section](https://github.com/safetensors/safetensors/blob/main/README.md#format), retrieved as text only. No package or model was fetched.

The format places an unsigned 64-bit little-endian header length before UTF-8 JSON. Each tensor entry supplies a dtype, shape and half-open byte offsets relative to the following data region. The JSON starts with an opening brace and may end with space padding. Duplicate keys are forbidden. Tensor data is little-endian and row-major; offsets must cover the data region without holes. This proposal omits the optional metadata entry and supports only dense F32 tensors with fixed positive dimensions. It additionally rejects nonfinite encodings, although the format itself permits them.

The upstream text defines the output format. It establishes nothing about the original PyTorch archive's byte order, writer version, provenance or scalar contents. Its main-branch URL is a consultation reference; exact production/native-reader version qualification remains open.
