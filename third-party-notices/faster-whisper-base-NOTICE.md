# Bundled Whisper base model

Uoink 3.12 and later ship one speech-recognition model, so a fresh install can
transcribe a video that has no captions without downloading anything.

- Model: OpenAI Whisper `base`, converted to the CTranslate2 format by SYSTRAN
  for faster-whisper.
- Source: https://huggingface.co/Systran/faster-whisper-base
- Pinned revision: `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`
- Location: `models/whisper-bundled/base/` in the Windows app folder, and
  `Contents/Resources/models/whisper-bundled/base/` in the macOS app. The
  `uoink-model.json` file beside the weights repeats the hashes below.

| File | Bytes | SHA-256 |
|---|---|---|
| config.json | 2,309 | `56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a` |
| model.bin | 145,217,532 | `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9` |
| tokenizer.json | 2,203,239 | `fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab` |
| vocabulary.txt | 459,861 | `34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913` |

The build downloads these files from the pinned revision and refuses to
package them unless every size and SHA-256 matches
(`scripts/whisper_model_pin.json` and `scripts/stage_whisper_model.py` in the
source repository). Uoink does not modify them.

## Licenses

**Whisper model weights.** OpenAI releases Whisper's code and model weights
under the MIT License (https://github.com/openai/whisper, "License"). The text
below is that license as published at
https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/LICENSE.

**CTranslate2 conversion.** SYSTRAN published the converted model in the
Hugging Face repository above. Its model card declares `license: mit` and
records the conversion: `ct2-transformers-converter --model openai/whisper-base
--copy_files tokenizer.json --quantization float16`. The repository holds no
separate license file. faster-whisper itself (MIT, Copyright (c) 2023 SYSTRAN)
is listed in THIRD-PARTY-NOTICES.md.

This notice records provenance and license declarations. It is not legal
clearance.

---

MIT License

Copyright (c) 2022 OpenAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
