# Captured VAD parent model link

The saved parent sources establish the field relationship needed by the next constructor repair. This is a source finding, conditional on the future fixed import closure binding these exact classes. No model or inference ran.

The owned VoiceActivitySegmentation first requires an owned Model instance and registry binding, then calls VoiceActivityDetection.__init__. That parent retains the supplied segmentation and passes it through get_model. For a Model instance, the captured getter calls eval and returns that same object. The parent then assigns Inference(model, ...) to _segmentation. Inference assigns the argument to self.model before its evaluation/device work.

The captured Pipeline attribute handlers store Model instances in _models[name] and BaseInference instances in _inferences[name], then retrieve them through __getattr__. A successful fixed construction should therefore retain both relationships:

- vad.segmentation is the exact registered segmentation model.
- vad._segmentation is the exact retained inference object, and vad._segmentation.model is that same model.

The owner should validate the fixed inference class/import binding as well as these references; a shaped object with a .model field is insufficient. Retain the actual VAD returned by the constructor before any later check. Failure inside a constructor before it returns remains a worker-retirement obligation.

Root read the relevant parent constructor/getter/inference and complete attribute-handler branches in b08863 and 5cfda9. The four saved text files match their existing capture map:

| Saved source under _scratch/vad-fixed-loader-proposal01 | Bytes | SHA-256 |
| --- | ---: | --- |
| source/pyannote/audio/pipelines/utils/getter.py | 9339 | 42bc13a1ba61a7a297e311c0f881f2e5abb8cff6dad219ed7ea654752480eab5 |
| source/pyannote/audio/pipelines/voice_activity_detection.py | 7801 | 24f4234c84f934f400f3a23da15d36104c1c04eb0453f6af9ca4ff2c3bd51fbb |
| source/pyannote/audio/core/inference.py | 25120 | c29f525c93a1a5c6bd0a9475ae4fb8c73ce9b48cf9735301302eb99886ad7d41 |
| source/pyannote/audio/core/pipeline.py | 23030 | c126c1ecf3a7172be311e61616145f45fbb5e52f06307adb28ac11103c8ee615 |

Relevant lines: parent95–125; getter111–139; inference78–167; Pipeline341–400. The owned derivative's guard/parent call is at vads/pyannote.py162–173, source aeec3ec0. The frozen CONNECTION-CONTRACT.md originally listed this parent field as unknown because its nine inputs did not include these four captures. Preserve that scoped statement and read this addendum alongside it.

This resolves the captured field name, not live module identity, compatibility, native reader behavior, runtime policy, retirement or release. Only saved source text was read; installed support files, model artifacts and D1/D2 outputs were not accessed.
