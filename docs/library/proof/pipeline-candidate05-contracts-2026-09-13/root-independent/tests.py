"""Synthetic contracts; S and N are explicit stdlib seams and selected AST code."""
import copy
import unittest

Pipeline = N['Pipeline']
WhisperPipeline = N['FasterWhisperPipeline']
Iterator = N['PipelineIterator']

def make_pipeline(cls=WhisperPipeline, **kwargs):
    model, tokenizer, options, vad = S.Model(), object(), object(), object()
    pipeline = cls(model, vad, {'synthetic': True}, options, tokenizer=tokenizer, **kwargs)
    return pipeline, model, tokenizer, options

def audio_items(count, consumed=None):
    for identity in range(count):
        if consumed is not None: consumed.append(identity)
        yield {'inputs': S.Audio(identity)}

class PipelineContracts(unittest.TestCase):
    def setUp(self): S.reset()

    def test_constructor_preserves_bypass_and_fields(self):
        pipeline, model, tokenizer, options = make_pipeline(batch_size=3, language='en', suppress_numerals=True)
        self.assertIs(pipeline.model, model)
        self.assertIs(pipeline.tokenizer, tokenizer)
        self.assertIs(pipeline.options, options)
        self.assertEqual(pipeline.device, S.Device('cpu'))
        self.assertEqual((pipeline._batch_size, pipeline._num_workers, pipeline.call_count), (3, 1, 0))
        self.assertEqual((pipeline.preset_language, pipeline.suppress_numerals, pipeline.framework), ('en', True, 'pt'))
        self.assertEqual(pipeline._vad_params, {'synthetic': True})
        self.assertFalse(hasattr(pipeline, 'task'))
        self.assertEqual((pipeline._preprocess_params, pipeline._forward_params, pipeline._postprocess_params), ({}, {}, {}))

    def test_constructor_device_forms(self):
        devices = (-1, 2, 'cuda:3', S.Device('cuda:4'))
        actual = [make_pipeline(device=value)[0].device.name for value in devices]
        self.assertEqual(actual, ['cpu', 'cuda:2', 'cuda:3', 'cuda:4'])

    def test_empty_generator_no_preprocess_or_model(self):
        pipeline, model, _, _ = make_pipeline()
        result = pipeline(audio_items(0), batch_size=3)
        self.assertEqual(result, [])
        self.assertEqual(model.calls, [])
        self.assertEqual(S.mel_calls, [])
        self.assertEqual(pipeline.call_count, 1)

    def test_batched_generator_preserves_first_order_and_partial_last(self):
        pipeline, model, _, _ = make_pipeline()
        result = list(pipeline(audio_items(5), batch_size=2))
        self.assertEqual([row['text'] for row in result], ['item0', 'item1', 'item2', 'item3', 'item4'])
        self.assertEqual(S.loaders[0].batch_lengths, [2, 2, 1])
        self.assertEqual(len(model.calls), 3)
        self.assertEqual([row['avg_logprob'] for row in result], [-0.5] * 5)

    def test_generator_peeks_once_then_consumes_by_batch(self):
        consumed = []
        pipeline, model, _, _ = make_pipeline()
        output = pipeline(audio_items(5, consumed), batch_size=2)
        self.assertEqual(consumed, [0])
        self.assertEqual((model.calls, S.mel_calls), ([], []))
        stream = iter(output)
        self.assertEqual(next(stream)['text'], 'item0')
        self.assertEqual(consumed, [0, 1])
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(next(stream)['text'], 'item1')
        self.assertEqual(consumed, [0, 1])
        self.assertEqual([row['text'] for row in stream], ['item2', 'item3', 'item4'])
        self.assertEqual(consumed, [0, 1, 2, 3, 4])

    def test_nonempty_list_is_eager(self):
        pipeline, model, _, _ = make_pipeline()
        result = pipeline(list(audio_items(3)), batch_size=2)
        self.assertIsInstance(result, list)
        self.assertEqual([row['text'] for row in result], ['item0', 'item1', 'item2'])
        self.assertEqual(len(model.calls), 2)

    def test_none_without_config_means_batch_one_and_list_value(self):
        pipeline, _, _, _ = make_pipeline()
        result = list(pipeline(audio_items(2), batch_size=None))
        self.assertEqual(S.loaders[0].batch_size, 1)
        self.assertEqual([row['text'] for row in result], [['item0'], ['item1']])
        self.assertEqual(S.loaders[0].batch_lengths, [1, 1])

    def test_none_uses_configured_batch_size(self):
        pipeline, _, _, _ = make_pipeline(batch_size=3)
        result = list(pipeline(audio_items(5), batch_size=None))
        self.assertEqual(S.loaders[0].batch_size, 3)
        self.assertEqual(S.loaders[0].batch_lengths, [3, 2])
        self.assertEqual([row['text'] for row in result], ['item0', 'item1', 'item2', 'item3', 'item4'])
        self.assertEqual(pipeline._batch_size, 3)

    def test_batch_one_overrides_configured_batch_size(self):
        pipeline, _, _, _ = make_pipeline(batch_size=3)
        result = list(pipeline(audio_items(2), batch_size=1))
        self.assertEqual([row['text'] for row in result], [['item0'], ['item1']])
        self.assertEqual(S.loaders[0].batch_size, 1)
        self.assertEqual(pipeline._batch_size, 3)

    def test_worker_options_forward_without_changing_stored_default(self):
        pipeline, _, _, _ = make_pipeline()
        list(pipeline(audio_items(1), num_workers=None))
        list(pipeline(audio_items(1), num_workers=0))
        list(pipeline(audio_items(1), num_workers=3))
        self.assertEqual([loader.num_workers for loader in S.loaders], [1, 0, 3])
        self.assertEqual(pipeline._num_workers, 1)
        pipeline._num_workers = None
        list(pipeline(audio_items(1), num_workers=None))
        self.assertEqual(S.loaders[-1].num_workers, 0)

    def test_exact_options_tokenizer_and_feature_size_forwarded(self):
        pipeline, model, tokenizer, options = make_pipeline()
        model.feat_kwargs['feature_size'] = 128
        list(pipeline(audio_items(3), batch_size=2))
        self.assertTrue(all(call['tokenizer'] is tokenizer and call['options'] is options for call in model.calls))
        self.assertEqual(S.mel_calls, [{'identity': n, 'n_mels': 128, 'padding': 479990} for n in range(3)])
        self.assertEqual([call['features'].shape for call in model.calls], [(2, 1, 1), (1, 1, 1)])

    def test_missing_feature_size_uses_eighty(self):
        pipeline, model, _, _ = make_pipeline()
        model.feat_kwargs = {}
        list(pipeline(audio_items(1), batch_size=1))
        self.assertEqual(S.mel_calls, [{'identity': 0, 'n_mels': 80, 'padding': 479990}])

    def test_model_error_propagates_and_contexts_close(self):
        pipeline, model, _, _ = make_pipeline(device='cuda:2')
        problem = RuntimeError('synthetic model sentinel')
        model.error = problem
        with self.assertRaises(RuntimeError) as caught:
            list(pipeline(audio_items(3), batch_size=2))
        self.assertIs(caught.exception, problem)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(S.events[-2:], [('no_grad', 'exit'), ('device', 'cuda:2', 'exit')])

class ParamSpy(WhisperPipeline):
    """Stage overrides are fakes; base call/forward and WX iterator remain exact."""
    def _sanitize_parameters(self, **kwargs):
        return kwargs.get('pre', {}), kwargs.get('fwd', {}), kwargs.get('post', {})
    def preprocess(self, audio, **params):
        self.stage_calls.append(('pre', copy.deepcopy(params)))
        return {'inputs': S.Tensor([[audio['inputs'].identity]])}
    def _forward(self, inputs, **params):
        self.stage_calls.append(('fwd', copy.deepcopy(params), inputs['inputs'].device.name))
        return {'values': inputs['inputs']}
    def postprocess(self, outputs, **params):
        self.stage_calls.append(('post', copy.deepcopy(params), outputs['values'].device.name))
        return outputs

class ParameterContracts(unittest.TestCase):
    def setUp(self): S.reset()

    def test_stage_parameters_merge_override_without_stored_mutation(self):
        defaults = {'pre': {'shared': 'p0', 'keep_pre': 1}, 'fwd': {'shared': 'f0', 'keep_fwd': 2}, 'post': {'shared': 'o0', 'keep_post': 3}}
        original_defaults = copy.deepcopy(defaults)
        pipeline, _, _, _ = make_pipeline(ParamSpy, device='cuda:2', **defaults)
        pipeline.stage_calls = []
        original_refs = (pipeline._preprocess_params, pipeline._forward_params, pipeline._postprocess_params)
        per_call = {'pre': {'shared': 'p1'}, 'fwd': {'shared': 'f1'}, 'post': {'shared': 'o1'}}
        original_call = copy.deepcopy(per_call)
        result = list(pipeline(audio_items(2), batch_size=2, **per_call))
        self.assertEqual(pipeline.stage_calls, [
            ('pre', {'shared': 'p1', 'keep_pre': 1}), ('pre', {'shared': 'p1', 'keep_pre': 1}),
            ('fwd', {'shared': 'f1', 'keep_fwd': 2}, 'cuda:2'),
            ('post', {'shared': 'o1', 'keep_post': 3}, 'cpu'), ('post', {'shared': 'o1', 'keep_post': 3}, 'cpu')])
        self.assertEqual([row['values'].values for row in result], [[[[0]]], [[[1]]]])
        self.assertEqual(defaults, original_defaults)
        self.assertEqual(per_call, original_call)
        self.assertTrue(all(left is right for left, right in zip(original_refs, (pipeline._preprocess_params, pipeline._forward_params, pipeline._postprocess_params))))
        self.assertEqual(S.events, [('device', 'cuda:2', 'enter'), ('no_grad', 'enter'), ('to', 'cpu', 'cuda:2'), ('to', 'cuda:2', 'cpu'), ('no_grad', 'exit'), ('device', 'cuda:2', 'exit')])

    def test_single_input_forwards_all_stage_parameters(self):
        pipeline, _, _, _ = make_pipeline(ParamSpy, device='cuda:1')
        pipeline.stage_calls = []
        result = pipeline({'inputs': S.Audio(7)}, pre={'p': 1}, fwd={'f': 2}, post={'o': 3})
        self.assertEqual(pipeline.stage_calls, [('pre', {'p': 1}), ('fwd', {'f': 2}, 'cuda:1'), ('post', {'o': 3}, 'cpu')])
        self.assertEqual(result['values'].values, [[7]])
        self.assertEqual(S.loaders, [])
        self.assertEqual((pipeline._preprocess_params, pipeline._forward_params, pipeline._postprocess_params), ({}, {}, {}))

    def test_nested_device_transfer_preserves_container_shapes(self):
        pipeline, _, _, _ = make_pipeline()
        original = S.ModelOutput({'list': [S.Tensor([[1]])], 'tuple': (S.Tensor([[2]]),), 'user': S.UserDict({'t': S.Tensor([[3]]), 'none': None}), 'scalar': 'keep'})
        result = pipeline._ensure_tensor_on_device(original, S.Device('cuda:5'))
        self.assertIsInstance(result, S.ModelOutput)
        self.assertIsInstance(result['tuple'], tuple)
        self.assertIsInstance(result['user'], S.UserDict)
        self.assertEqual([result['list'][0].device.name, result['tuple'][0].device.name, result['user']['t'].device.name], ['cuda:5'] * 3)
        self.assertEqual((result['user']['none'], result['scalar']), (None, 'keep'))
        self.assertEqual(original['list'][0].device.name, 'cpu')

class IteratorContracts(unittest.TestCase):
    def setUp(self): S.reset()

    def test_none_batch_preserves_result_identity_and_params(self):
        processed, calls, params = {'text': ['one', 'two']}, [], {'option': 'retained'}
        def infer(value, **kwargs):
            calls.append((value, kwargs))
            return processed
        iterator = Iterator([5], infer, params, loader_batch_size=None)
        result = list(iterator)
        self.assertIs(result[0], processed)
        self.assertEqual(calls, [(5, {'option': 'retained'})])
        self.assertEqual(params, {'option': 'retained'})

    def test_batch_one_preserves_list_value_without_unwrapping(self):
        processed = {'text': ['only']}
        iterator = Iterator([1], lambda value: processed, {}, loader_batch_size=1)
        self.assertIsNone(iterator.loader_batch_size)
        result = list(iterator)
        self.assertIs(result[0], processed)
        self.assertEqual(result, [{'text': ['only']}])

    def test_partial_batch_strings_and_none_preserved(self):
        batches = [{'text': ['a', 'b', 'c'], 'optional': None}, {'text': ['d'], 'optional': None}]
        iterator = Iterator(batches, lambda value: value, {}, loader_batch_size=3)
        result = list(iterator)
        self.assertEqual(result, [{'text': letter, 'optional': None} for letter in 'abcd'])
        self.assertEqual(iterator.loader_batch_size, 1)

    def test_tensor_batch_retains_leading_dimension(self):
        result = list(Iterator([S.Tensor([[1, 2], [3, 4]])], lambda value: value, {}, loader_batch_size=2))
        self.assertEqual([row.values for row in result], [[[1, 2]], [[3, 4]]])
        self.assertEqual([row.shape for row in result], [(1, 2), (1, 2)])

    def test_dictionary_tensor_and_array_preserve_leading_dimension(self):
        batch = S.ModelOutput({'text': ['a', 'b'], 'tensor': S.Tensor([[1, 2], [3, 4]]), 'array': S.Array([[5, 6], [7, 8]])})
        result = list(Iterator([batch], lambda value: value, {}, loader_batch_size=2))
        self.assertTrue(all(isinstance(row, S.ModelOutput) for row in result))
        self.assertEqual([row['tensor'].values for row in result], [[[1, 2]], [[3, 4]]])
        self.assertEqual([row['array'].values for row in result], [[[5, 6]], [[7, 8]]])
        self.assertEqual([row['text'] for row in result], ['a', 'b'])

    def test_iterator_is_lazy_before_first_next(self):
        seen = []
        def inputs():
            for number in range(3):
                seen.append(number)
                yield number
        iterator = Iterator(inputs(), lambda value: value + 10, {})
        self.assertEqual(seen, [])
        iter(iterator)
        self.assertEqual(seen, [])
        self.assertEqual(next(iterator), 10)
        self.assertEqual(seen, [0])

    def test_iterator_propagates_exact_infer_error(self):
        problem = ValueError('synthetic iterator sentinel')
        def infer(value): raise problem
        iterator = iter(Iterator([1], infer, {}))
        with self.assertRaises(ValueError) as caught: next(iterator)
        self.assertIs(caught.exception, problem)
