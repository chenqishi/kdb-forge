"""Run old script paths and alias old imports to one relocated implementation."""
import importlib
import importlib.util
import runpy
import sys
import types


class _LegacyModuleAlias(types.ModuleType):
    """Preserve monkeypatching for callers retaining a spec-loaded module object."""

    def __getattribute__(self, name):
        if name in {"_legacy_implementation", "__class__"}:
            return types.ModuleType.__getattribute__(self, name)
        implementation = types.ModuleType.__getattribute__(self, "_legacy_implementation")
        return getattr(implementation, name)

    def __setattr__(self, name, value):
        if name in {"_legacy_implementation", "__class__"}:
            return types.ModuleType.__setattr__(self, name, value)
        implementation = types.ModuleType.__getattribute__(self, "_legacy_implementation")
        setattr(implementation, name, value)

    def __delattr__(self, name):
        implementation = types.ModuleType.__getattribute__(self, "_legacy_implementation")
        delattr(implementation, name)


def legacy_entry(name: str, target: str, namespace: dict) -> None:
    """Preserve argv/CLI exits; ordinary imports share the canonical module instance."""
    if name == "__main__":
        runpy.run_module(target, run_name="__main__", alter_sys=False)
        return
    original = sys.modules.get(name)
    if original is None:
        # Some existing tools execute module_from_spec without registering it.
        # Execute the same canonical source in that isolated namespace, as before.
        spec = importlib.util.find_spec(target)
        if spec is None or spec.loader is None:
            raise ModuleNotFoundError(target)
        namespace["__package__"] = target.rpartition(".")[0]
        exec(spec.loader.get_code(target), namespace)
        return
    implementation = importlib.import_module(target)
    if original is not implementation:
        original._legacy_implementation = implementation
        original.__class__ = _LegacyModuleAlias
    sys.modules[name] = implementation
    namespace.update(vars(implementation))
