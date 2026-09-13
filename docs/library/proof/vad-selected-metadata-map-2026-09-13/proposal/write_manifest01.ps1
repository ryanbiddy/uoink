$ErrorActionPreference='Stop'
$taskDir='E:\AI\projects\uoink\checkouts\Yoink-library\_scratch\vad-selected-metadata-map01'
$taskMapPath=Join-Path $taskDir 'mapping.json'
if ((Get-FileHash -LiteralPath $taskMapPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca') { throw 'Mapping digest mismatch' }
$taskMap=Get-Content -Raw -LiteralPath $taskMapPath | ConvertFrom-Json
$taskSupplement=Get-Content -Raw -LiteralPath (Join-Path $taskDir 'supplement01.json') | ConvertFrom-Json
$taskSchema=@()
foreach($taskRow in $taskMap.tensor_rows) {
    $taskRole='parameter_in_proposed_current_factory'
    if ($taskRow.key -in @('sincnet.conv1d.0.filterbank.window_','sincnet.conv1d.0.filterbank.n_')) { $taskRole='persistent_buffer_in_proposed_current_factory' }
    $taskSchema += [ordered]@{ key=$taskRow.key; proposed_plain_dtype='F32'; declared_shape=$taskRow.size.values; declared_stride=$taskRow.stride.values; proposed_role=$taskRole; evidence=[ordered]@{ key_ref=$taskRow.key_ref; reducer_ref=$taskRow.reducer_ref; shape_ref=$taskRow.size.ref; stride_ref=$taskRow.stride.ref; persistent_ref=$taskRow.storage.persistent_record.id; storage_key_literal=$taskRow.storage.key_literal; storage_offset_ref=$taskRow.storage_offset.ref; storage_offset_literal=$taskRow.storage_offset.value } }
}
$taskManifest=[ordered]@{
    schema='uoink.fixed-vad.inert-proposal.v2'
    status='CONCRETE_PROPOSAL_UNAPPROVED_NO_EXECUTION_AUTHORITY'
    fixed_factory_id='uoink-pyannet-16k-4x128-bi-v1'
    version_bridge_id='legacy-specification-to-pyannote4-v1'
    factory_text_sha256=(Get-FileHash -LiteralPath (Join-Path $taskDir 'fixed-factory.proposal.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
    evidence_receipt_sha256='60b0078f3367bf80b8ed526d681850c47b0caae09f4fbd8da3de0883f927247d'
    mapping_sha256='b6ef4d932556a24e46661e5600e50b386f3243a3aeeb19fa0dad592e439fd5ca'
    artifact_status_from_receipt='refused'
    artifact_reader_exit_from_receipt=2
    checkpoint_recorded=[ordered]@{
        architecture=[ordered]@{ module='pyannote.audio.models.segmentation.PyanNet'; module_ref=3064; class='PyanNet'; class_ref=3066; parent_dict_ref=3062; provenance_verified=$false }
        constructor=[ordered]@{ sample_rate=16000; num_channels=1; sincnet=[ordered]@{stride=10;sample_rate=16000}; lstm=[ordered]@{hidden_size=128;num_layers=4;bidirectional=$true;monolithic=$true;dropout=0.5;batch_first=$true}; linear=[ordered]@{hidden_size=128;num_layers=2}; evidence_root_ref=3022 }
        specifications_tagged_build_state=[ordered]@{ object_ref=3086; state_ref=3087; problem=[ordered]@{global_literal='pyannote.audio.core.task Problem'; reducer_ref=3092; argument_ref=3090; integer_argument=2}; resolution=[ordered]@{global_literal='pyannote.audio.core.task Resolution'; reducer_ref=3097; argument_ref=3095; integer_argument=1}; duration=5.0; duration_ref=3099; warm_up=@(0.0,0.0); warm_up_ref=3103; classes=@('speaker#1','speaker#2','speaker#3'); classes_ref=3105; permutation_invariant=$true; permutation_invariant_ref=3110; missing_fields=@('min_duration','powerset_max_classes'); evaluated_build_state=$false }
    }
    proposed_current_source_bridge=[ordered]@{
        min_duration=[ordered]@{value=$null;origin='absent checkpoint field; explicit proposed current TASK:89 default'; approved=$false}
        powerset_max_classes=[ordered]@{value=$null;origin='absent checkpoint field; proposed TASK:104 default; TASK:110-119 then disables powerset, consistent with three-row classifier and proposed MULTI_LABEL choice'; approved=$false}
        problem=[ordered]@{value='Problem.MULTI_LABEL_CLASSIFICATION';origin='TASK:59-64 maps integer2; legacy reducer not evaluated';approved=$false}
        resolution=[ordered]@{value='Resolution.FRAME';origin='TASK:71-73 maps integer1; legacy reducer not evaluated';approved=$false}
        lstm_bias=[ordered]@{value=$true;origin='absent checkpoint constructor field; TORCH_RNN:90 default and recorded sixteen bias vectors';approved=$false}
        lstm_proj_size=[ordered]@{value=0;origin='absent checkpoint constructor field; TORCH_RNN:94 default and absence of projection keys in the 54 state entries';approved=$false}
        task=[ordered]@{value=$null;origin='new inference-only factory choice; no checkpoint training task reconstructed';approved=$false}
        state_metadata=[ordered]@{value='Do not replay state_dict BUILD or legacy metadata';origin='new plain-state migration choice; requires strict current-module compatibility qualification';approved=$false}
        dtype=[ordered]@{value='CPU float32';origin='proposed plain format/current-factory policy supported by FloatStorage literal and four-byte declarations; storage encoding unverified';approved=$false}
    }
    proposed_tensor_schema=$taskSchema
    proposed_artifact=[ordered]@{filename='default-vad.safetensors';exists=$false;sha256=$null;bytes=$null;exact_tensor_count=54;total_elements=1472999;expected_dense_tensor_payload_bytes=5891996;max_header_bytes=32768;max_file_bytes=6291456;header_metadata_allowed=$false;scalar_value_finiteness_required=$true;format_version_qualified=$null;byte_order_evidence=$null;source_storage_key_count=23;source_storage16_elements=1380352;source_storage16_tensor_views=32;plain_export_policy='Materialize each reviewed disjoint source range into a plain contiguous zero-offset tensor; no cast, reshape, renaming or omitted buffers';storage_sharing_change_approved=$false}
    proposed_inference=[ordered]@{device='cpu for initial qualification';window='sliding';duration=5.0;step=0.5;batch_size=32;skip_aggregation=$false;skip_conversion=$false;expected_powerset_conversion='Identity under proposed bridge';pre_aggregation='Source-defined maximum over score channels';onset=0.500;offset=0.363;min_duration_on=0.1;min_duration_off=0.1;training=$false;requires_grad=$false;speaker_attribution=$false}
    retained_sources=$taskMap.retained_source_hashes_rechecked
    additional_staged_source_text=$taskSupplement.sources
    unresolved_gates=@('trusted model provenance and redistribution/license receipt','reviewed version bridge acceptance','source byte order and storage serialization protocol','approved nonexecuting conversion protocol or authoritative plain export','new artifact exact hash and byte count and release trust anchor','native plain-tensor parser and full header/shape/allocation bounds qualification','target runtime/import graph and advisory/dependency qualification','CPU model state and numerical/end-to-end VAD receipts','separate GPU/device receipt if enabled','release and installed candidate receipts')
    release_trust_anchor=$null
    conversion_or_export_receipt=$null
    license_receipt=$null
    qualified_runtime_lock_sha256=$null
    qualification_receipts=@()
    approval_receipt=$null
    network_allowed=$false
    checkpoint_selected_imports_allowed=$false
    pickle_loading_allowed=$false
    unrestricted_fallback_allowed=$false
    speaker_attribution_allowed=$false
}
$taskOut=Join-Path $taskDir 'manifest.proposal.json'
if (Test-Path -LiteralPath $taskOut) { throw 'Refuse overwrite' }
$taskManifest | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $taskOut -Encoding utf8
[ordered]@{status='inert_manifest_written';tensor_schema_entries=$taskSchema.Count;factory_text_sha256=$taskManifest.factory_text_sha256;manifest_sha256=(Get-FileHash -LiteralPath $taskOut -Algorithm SHA256).Hash.ToLowerInvariant();exit=0} | ConvertTo-Json
