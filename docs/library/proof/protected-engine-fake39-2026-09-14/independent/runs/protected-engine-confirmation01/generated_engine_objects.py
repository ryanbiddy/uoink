"""Fixed generated-only construction values; no backend/native/model calls.

These private types are inert stand-ins, not WhisperModel or WhisperX. Their
shape/prepared flags do not confer ownership. Only the live owner's retained
attempt and exact issued namespace/VAD can authorize generated publication.
There is no caller-selected constructor or callback parameter.
"""


class _GeneratedEngineModel:
    __slots__ = ('namespace', 'vad', 'prepared')

    def __init__(self, namespace, vad):
        self.namespace, self.vad = namespace, vad
        self.prepared = False

    def prepare(self):
        if self.prepared:
            raise RuntimeError('generated_model_prepare_single_use')
        self.prepared = True


class _GeneratedEnginePipeline:
    __slots__ = ('model', 'vad', 'prepared')

    def __init__(self, model, vad):
        self.model, self.vad = model, vad
        self.prepared = False

    def prepare(self):
        if self.prepared:
            raise RuntimeError('generated_pipeline_prepare_single_use')
        self.prepared = True
