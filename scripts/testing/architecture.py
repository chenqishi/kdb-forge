"""Static import boundaries for business modules; no product imports or I/O."""
import ast
from pathlib import Path


def inspect_imports(source_root):
    source_root = Path(source_root)
    modules = {}
    for path in source_root.rglob('*.py'):
        name = '.'.join(path.relative_to(source_root).with_suffix('').parts)
        if name.endswith('.__init__'):
            name = name[:-9]
        modules[name] = path
    edges = []
    for name, path in sorted(modules.items()):
        package = name if path.name == '__init__.py' else name.rsplit('.', 1)[0]
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                parent = node.module or ''
                if node.level:
                    parent = '.'.join(package.split('.')[:len(package.split('.')) - node.level + 1] + ([parent] if parent else []))
                targets = [parent + '.' + alias.name if parent + '.' + alias.name in modules else parent for alias in node.names]
            else:
                continue
            for target in targets:
                edges.append({'source': name, 'target': target, 'line': node.lineno})
    return modules, edges


def boundary_errors(edges):
    errors = []
    for edge in edges:
        source, target = edge['source'], edge['target']
        rule = None
        if source.startswith('kdb.shared.') and target.startswith('kdb.') and not target.startswith('kdb.shared.'):
            rule = 'shared must not import business modules'
        if source.startswith('kdb.mining.common.') and target.startswith(tuple('kdb.mining.' + domain + '.' for domain in ['chat', 'document', 'web', 'tasks', 'bridges'])):
            rule = 'mining common must not import source-specific implementations'
        if source.startswith('kdb.retrieval.') and target.startswith(('kdb.mining.', 'kdb.entrypoints.')):
            rule = 'retrieval must not import mining or entrypoints'
        if source.startswith('kdb.mining.') and target.startswith('kdb.retrieval.') and source != 'kdb.mining.bridges.retrieval':
            rule = 'mining must use its retrieval bridge'
        if source.startswith('kdb.') and not source.startswith('kdb.entrypoints.') and target.startswith('kdb.entrypoints.'):
            rule = 'business modules must not import entrypoints'
        if source.startswith('kdb.') and target.startswith('assistant_data_tools'):
            rule = 'core must not import auxiliary project'
        if source.startswith('assistant_data_tools.') and target.startswith('kdb.') and not target.startswith('kdb.shared.'):
            rule = 'auxiliary project may only import core shared modules'
        if rule:
            errors.append(dict(edge, rule=rule))
    return errors


def import_cycles(modules, edges):
    graph = {name: set() for name in modules}
    for edge in edges:
        if edge['target'] in graph and edge['source'] != edge['target']:
            graph[edge['source']].add(edge['target'])
    index = {}; low = {}; stack = []; active = set(); result = []
    def visit(node):
        index[node] = low[node] = len(index)
        stack.append(node); active.add(node)
        for other in sorted(graph[node]):
            if other not in index:
                visit(other); low[node] = min(low[node], low[other])
            elif other in active:
                low[node] = min(low[node], index[other])
        if low[node] == index[node]:
            group = []
            while True:
                other = stack.pop(); active.remove(other); group.append(other)
                if other == node: break
            if len(group) > 1: result.append(sorted(group))
    for node in sorted(graph):
        if node not in index: visit(node)
    return result
