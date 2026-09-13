# Public history-path guard repair

The intended first asset-history request was refused by the local URL guard before any HTTP call or attempt directory creation. Actual process exit was 1; the exception was `Unapproved public repository metadata path` at collector line 17. Requested URL: `https://api.github.com/repos/m-bain/whisperX/commits?path=whisperx%2Fassets%2Fpytorch_model.bin&sha=3ccc17b8de34f305300f8a3fd3c9f76ba820c0d0&per_page=10`.

The pattern placed `commits$` inside an alternative followed by a required `.+`, so it could never admit the exact `/commits` collection endpoint. Before making a fresh request, preserve that collector in collector-draft02 and correct only this path alternative. The fixed endpoint remains unauthenticated, repository-scoped, text/JSON bounded and redirect-disabled. No model/blob data was requested or obtained. The fresh attempt will be named whisperx-asset-history02; this refused preparation remains an actual failure.
