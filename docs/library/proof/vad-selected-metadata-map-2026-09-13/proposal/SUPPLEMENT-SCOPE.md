# Shared-storage and source-text supplement

The first mapping completed with exit 0. Its full per-entry fields are retained unchanged. It records 54 entries but 23 storage-key literals: 32 LSTM entries refer to key `16` with different offsets. Consequently the per-entry sum of advertised member sizes counts that shared member 32 times, and the aggregate equality of each tensor's shape product to the entire storage length is false. Those fields describe shared storage; they are not failed model tests.

Add a separate arithmetic report grouped by storage-key literal. Retain every interval and reference ID, report distinct advertised bytes, and check whether the declared row-major intervals overlap or leave gaps. This remains arithmetic on safe JSON declarations, without resolving persistent IDs or reading payloads.

Read and preserve three additional staged Python sources as text: Torch `__init__.py`, `nn/modules/rnn.py`, and `_utils.py`. Their explicit filenames are required to bind the candidate FloatStorage interpretation, LSTM bias/projection defaults and reducer argument names. Hash the source bytes and exact scratch copies; do not import or execute them. This does not inspect any checkpoint, install a dependency or change the original fixed-loader proposal.
