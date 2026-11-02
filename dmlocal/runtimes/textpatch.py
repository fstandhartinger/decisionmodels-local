"""Restricted UTF-8 unified diffs. No commands, fuzz, links, renames or mode changes."""
import re
import stat


def tree_hashes(root, contained, digest):
    result = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        contained(root, relative)
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode) or path.name.startswith('.dm-local-'):
            raise RuntimeError('checkout contains a special or reserved file')
        result[relative] = digest(path)
    return result


def apply_text_patch(root, data, contained):
    """Validate the entire patch and exact old contents before writing staged files."""
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('patch must be UTF-8 text') from exc
    if '\x00' in text or '\r' in text or not text.endswith('\n'):
        raise ValueError('patch must be LF-terminated text without NUL')
    lines = text.splitlines(keepends=True)
    updates, i = {}, 0
    while i < len(lines):
        header = re.fullmatch(r'diff --git a/([^\s]+) b/([^\s]+)\n', lines[i])
        if not header or header[1] != header[2]:
            raise ValueError('only same-path git text diffs are supported')
        name = header[1]
        target = contained(root, name)
        if any(part.lower() in ('.git', '.hg', '.svn') or part.startswith('.dm-local-') for part in target.relative_to(root).parts):
            raise ValueError('patch target is reserved')
        if name.casefold() in {key.casefold() for key in updates}:
            raise ValueError('duplicate patch target')
        i += 1
        new = i < len(lines) and lines[i] == 'new file mode 100644\n'
        if new:
            i += 1
        if i >= len(lines) or not re.fullmatch(r'index [0-9a-f]+\.\.[0-9a-f]+(?: 100644)?\n', lines[i]):
            raise ValueError('unsupported patch metadata (binary, links, modes or renames)')
        if new and not re.fullmatch(r'index 0+\.\.[0-9a-f]+\n', lines[i]):
            raise ValueError('new patch file must have a zero source index')
        i += 1
        before = '--- /dev/null\n' if new else '--- a/' + name + '\n'
        # Git permits omission of ---/+++ only for a declared new regular file.
        if not (new and i < len(lines) and lines[i].startswith('@@ ')):
            if lines[i:i + 2] != [before, '+++ b/' + name + '\n']:
                raise ValueError('patch file headers disagree')
            i += 2
        if new:
            if target.exists():
                raise RuntimeError('new patch file already exists')
            old = []
        else:
            if not target.is_file():
                raise RuntimeError('patch target is not a regular file')
            raw = target.read_bytes()
            if b'\x00' in raw:
                raise ValueError('patch target is binary')
            old = raw.decode('utf-8').splitlines(keepends=True)
        output, cursor, hunks = [], 0, 0
        while i < len(lines) and not lines[i].startswith('diff --git '):
            hunk = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n', lines[i])
            if not hunk:
                raise ValueError('unsupported or malformed patch hunk')
            start, count = int(hunk[1]), int(hunk[2] or 1)
            new_start, new_count = int(hunk[3]), int(hunk[4] or 1)
            pos = start - 1 if count else start
            if pos < cursor or pos > len(old):
                raise ValueError('patch hunks overlap or escape file')
            output.extend(old[cursor:pos])
            cursor = pos
            if new_start != (len(output) + 1 if new_count else len(output)):
                raise ValueError('patch new hunk position disagrees')
            i += 1
            consumed = produced = 0
            while consumed < count or produced < new_count:
                if i >= len(lines) or lines[i][0] not in ' +-':
                    raise ValueError('patch hunk is truncated')
                kind, content = lines[i][0], lines[i][1:]
                if kind in ' -':
                    if cursor >= len(old) or old[cursor] != content:
                        raise RuntimeError('patch context does not match verified source')
                    cursor += 1
                    consumed += 1
                if kind in ' +':
                    output.append(content)
                    produced += 1
                if consumed > count or produced > new_count:
                    raise ValueError('patch hunk counts disagree')
                i += 1
            hunks += 1
        if not hunks:
            raise ValueError('patch has no text hunks')
        output.extend(old[cursor:])
        updates[name] = ''.join(output).encode('utf-8')
    if not updates:
        raise ValueError('empty patch')
    for name, content in updates.items():
        target = contained(root, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
