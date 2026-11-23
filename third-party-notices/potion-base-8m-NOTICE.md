# Bundled potion-base-8M text-embedding model

Uoink 3.18 and later ship one small text-embedding model, so shelf
suggestions can compare saves by meaning on any install, with no download.

- Model: potion-base-8M, a Model2Vec static embedding model by MinishLab. Its
  model card describes it as a distilled version of the baai/bge-base-en-v1.5
  Sentence Transformer, pre-trained with Tokenlearn. It is a table of word-piece
  vectors: Uoink averages the rows for a text's word pieces. No neural network
  runs.
- Source: https://huggingface.co/minishlab/potion-base-8M
- Pinned revision: `bf8b056651a2c21b8d2565580b8569da283cab23`
- Location: `models/embed-bundled/potion-base-8m/` in the Windows app folder, and
  `Contents/Resources/models/embed-bundled/potion-base-8m/` in the macOS app.
  The `uoink-model.json` file beside the weights repeats the hashes below.

| File | Bytes | SHA-256 |
|---|---|---|
| config.json | 202 | `2a6ac0e9aaa356a68a5688070db78fc3a464fefe85d2f06a1905ce3718687553` |
| model.safetensors | 30,236,760 | `f65d0f325faadc1e121c319e2faa41170d3fa07d8c89abd48ca5358d9a223de2` |
| tokenizer.json | 683,666 | `e67e803f624fb4d67dea1c730d06e1067e1b14d830e2c2202569e3ef0f70bb50` |

The build downloads these files from the pinned revision and refuses to
package them unless every size and SHA-256 matches
(`scripts/embed_model_pin.json` and `scripts/stage_embed_model.py` in the
source repository). Uoink does not modify them. Uoink reads them with its own
code (`local_embed.py`); the `model2vec` package is not shipped.

## License

The model card declares `license: mit`. The Hugging Face repository holds no
separate license file. The text below is the MIT License of the Model2Vec
project (https://github.com/MinishLab/model2vec, file `LICENSE`), which the
model card asks users to cite. The configuration names baai/bge-base-en-v1.5
(MIT) as the source of the tokenizer.

This notice records provenance and license declarations. It is not legal
clearance.

---

MIT License

Copyright (c) 2024 Thomas van Dongen

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
