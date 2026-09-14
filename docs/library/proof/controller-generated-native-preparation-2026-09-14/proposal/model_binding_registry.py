"""Concrete worker-local identity registry proposal; real bootstrap is absent."""
from dataclasses import dataclass
from contextlib import contextmanager
from threading import RLock

from state_bridge import FIXED_SHAPES

FIXED_RECIPE_SHA256 = '69136c1f7d5cd7bf283e3634dff730c9fd951a314a80b0fa134208f3d1c1820b'


class ModelBindingRefusal(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise ModelBindingRefusal(reason)


def open_real_model_registry(*args, **kwargs):
    raise ModelBindingRefusal('real_worker_bootstrap_absent')


@dataclass(frozen=True, slots=True)
class _StateBindingProposal:
    # Passive values alone confer no authority. Only the bootstrap permit may
    # issue a capability after independently verifying this exact state recipe.
    output_sha256: str
    profile_binding_sha256: str
    tensor_digests: tuple  # (exact key, exact shape tuple, 32-byte value digest)


def _binding(value):
    _require(type(value) is _StateBindingProposal, 'state_binding_type')
    for digest in (value.output_sha256, value.profile_binding_sha256):
        _require(type(digest) is str and len(digest) == 64
                 and all(char in '0123456789abcdef' for char in digest), 'state_binding_digest')
    _require(type(value.tensor_digests) is tuple and len(value.tensor_digests) == 54,
             'state_binding_schema')
    for row, (key, shape) in zip(value.tensor_digests, FIXED_SHAPES, strict=True):
        _require(type(row) is tuple and len(row) == 3
                 and type(row[0]) is str and row[0] == key
                 and type(row[1]) is tuple and all(type(n) is int for n in row[1])
                 and row[1] == shape and type(row[2]) is bytes and len(row[2]) == 32,
                 'state_binding_schema')


class _WorkerModelRegistryProposal:
    """One worker generation, one factory capability, one exact model lease.

    bootstrap_permit is a nonserialized identity held only by reviewed bootstrap
    code. Creating this private class is not an application admission. Actual
    binding to the controller's live OwnedSession/permit over authenticated IPC
    is unimplemented. No model or lease may be returned by the controller facade.
    """

    def __init__(self, bootstrap_permit, expected_factory_type):
        _require(type(bootstrap_permit) is object and isinstance(expected_factory_type, type),
                 'bootstrap_binding')
        self._bootstrap_permit = bootstrap_permit
        self._factory_type = expected_factory_type
        self._generation = object()
        self._lock = RLock()
        self._active = True
        self._capability = None
        self._lease = None

    def _live_locked(self):
        _require(self._active is True, 'worker_generation_revoked')

    def assert_active(self):
        with self._lock:
            self._live_locked()

    def _issue_for_bootstrap(self, permit, factory, state_binding, recipe_sha256):
        with self._lock:
            self._live_locked()
            _require(permit is self._bootstrap_permit, 'bootstrap_permit_identity')
            _require(type(factory) is self._factory_type and self._capability is None,
                     'factory_capability_already_issued_or_foreign')
            _require(type(recipe_sha256) is str and recipe_sha256 == FIXED_RECIPE_SHA256, 'fixed_recipe')
            _binding(state_binding)
            capability = _FactoryModelCapability(self, factory, state_binding, self._generation)
            self._capability = capability
            return capability

    def assert_vad_model_binding(self, model):
        # This is the exact owned constructor's required runtime method.
        with self._lock:
            self._live_locked()
            lease = self._lease
            _require(lease is not None and lease._active is True
                     and lease._generation is self._generation and lease._model is model
                     and lease._capability is self._capability
                     and self._capability._active is True, 'model_identity_not_registered')

    def revoke_generation(self, permit):
        retiring = []
        with self._lock:
            _require(permit is self._bootstrap_permit, 'bootstrap_permit_identity')
            # Revoke before dropping any strong model/factory references. This
            # makes later checks fail even if native references remain alive.
            self._active = False
            if self._capability is not None:
                self._capability._active = False
            if self._lease is not None:
                self._lease._active = False
                retiring.append(self._lease._model)
                self._lease._model = None
            if self._capability is not None:
                retiring.append(self._capability._factory)
                self._capability._factory = None
        # A last native owner reference may run destruction. Drop it after the
        # state lock is released; revocation itself already took effect above.
        retiring.clear()


class _FactoryModelCapability:
    def __init__(self, registry, factory, state_binding, generation):
        self._registry = registry
        self._factory = factory
        self._state_binding = state_binding
        self._generation = generation
        self._active = True
        self._used = False

    def _factory_locked(self, factory):
        registry = self._registry
        registry._live_locked()
        _require(registry._capability is self and self._active is True
                 and self._generation is registry._generation and self._factory is factory,
                 'factory_capability_identity')

    def assert_factory_and_runtime(self, factory, owned_runtime_module):
        with self._registry._lock:
            self._factory_locked(factory)
            _require(owned_runtime_module._RUNTIME is self._registry, 'owned_runtime_registry_identity')

    def register_verified_model(self, factory, owned_runtime_module, model, observed_rows):
        with self._registry._lock:
            self.assert_factory_and_runtime(factory, owned_runtime_module)
            _require(self._used is False and self._registry._lease is None,
                     'model_registration_already_used')
            _binding(_StateBindingProposal(self._state_binding.output_sha256,
                                          self._state_binding.profile_binding_sha256, observed_rows))
            _require(observed_rows == self._state_binding.tensor_digests,
                     'verified_state_binding_mismatch')
            _require(type(model) is factory._factory.PyanNet, 'fixed_model_type')
            lease = _ModelRegistrationLease(self._registry, self, model, self._generation)
            self._registry._lease = lease
            self._used = True
            return lease

    def revoke(self, factory):
        registry = self._registry
        retiring = []
        with registry._lock:
            # Revocation remains available after generation closure. Identity is
            # checked against the held capability, not a caller-provided token.
            _require(registry._capability is self, 'factory_capability_identity')
            _require(self._factory is factory or self._active is False, 'factory_capability_identity')
            self._active = False
            lease = registry._lease
            if lease is not None and lease._capability is self:
                lease._active = False
                retiring.append(lease._model)
                lease._model = None
            retiring.append(self._factory)
            self._factory = None
        retiring.clear()


class _ModelRegistrationLease:
    def __init__(self, registry, capability, model, generation):
        self._registry = registry
        self._capability = capability
        self._model = model
        self._generation = generation
        self._active = True

    def assert_bound(self, factory, model):
        with self._registry._lock:
            self._capability._factory_locked(factory)
            _require(self._registry._lease is self and self._active is True
                     and self._model is model and self._generation is self._registry._generation,
                     'model_lease_identity')
            self._registry.assert_vad_model_binding(model)

    def revoke(self, factory):
        self._capability.revoke(factory)

    @contextmanager
    def publication(self, factory, model):
        # Caller performs only final Python ownership assignments while held;
        # no native calls, constructors or user-selected callbacks are allowed.
        with self._registry._lock:
            self.assert_bound(factory, model)
            yield
