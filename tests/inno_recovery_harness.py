"""Execute the small Pascal control-flow subset used by recovery callbacks.

Reads the actual installer bodies. All external calls are supplied by tests;
unsupported syntax fails instead of silently approximating an installer step.
This is not an Inno compiler or installed-uninstaller proof.
"""
import re


class ReturnFromPascal(BaseException):
    pass


class PascalBody:
    def __init__(self, source):
        pattern = r"'(?:''|[^'])*'|\(\*[\s\S]*?\*\)|\{[^}]*\}|//[^\n]*|:=|<>|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[();,+\-=]|\s+"
        self.tokens = []
        cursor = 0
        for match in re.finditer(pattern, source):
            assert match.start() == cursor, source[cursor:match.start()]
            cursor = match.end()
            token = match[0]
            if token.isspace() or token.startswith(('(*', '{', '//')):
                continue
            self.tokens.append(token if token.startswith("'") else token.lower())
        assert cursor == len(source)
        self.at = self.tokens.index('begin')
        self.tree = self.statement()
        self.take(';')
        assert self.at == len(self.tokens), self.tokens[self.at:]

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def take(self, token):
        assert self.peek() == token, (token, self.tokens[self.at:self.at + 10])
        self.at += 1

    def expression(self, stops):
        start, depth = self.at, 0
        while self.at < len(self.tokens):
            token = self.peek()
            if depth == 0 and token in stops:
                break
            depth += (token == '(') - (token == ')')
            self.at += 1
        assert depth == 0 and self.at > start
        return self.tokens[start:self.at]

    def sequence(self, stops):
        items = []
        while self.peek() not in stops:
            items.append(self.statement())
            if self.peek() == ';':
                self.take(';')
            else:
                assert self.peek() in stops
        return ('sequence', items)

    def statement(self):
        token = self.peek()
        if token == 'begin':
            self.take('begin')
            body = self.sequence({'end'})
            self.take('end')
            return body
        if token == 'if':
            self.take('if')
            condition = self.expression({'then'})
            self.take('then')
            yes = self.statement()
            no = ('sequence', [])
            if self.peek() == 'else':
                self.take('else')
                no = self.statement()
            return ('if', condition, yes, no)
        if token == 'try':
            self.take('try')
            body = self.sequence({'except'})
            self.take('except')
            handler = self.sequence({'end'})
            self.take('end')
            return ('try', body, handler)
        if token == 'exit':
            self.take('exit')
            return ('exit',)
        if self.tokens[self.at + 1] == ':=':
            self.at += 2
            return ('assign', token, self.expression({';', 'end', 'else'}))
        return ('call', self.expression({';', 'end', 'else'}))

    @staticmethod
    def evaluate(tokens, scope):
        converted = []
        for token in tokens:
            if token.startswith("'"):
                converted.append(repr(token[1:-1].replace("''", "'")))
            else:
                converted.append({'=': '==', '<>': '!='}.get(token, token))
        return eval(' '.join(converted), {'__builtins__': {}}, scope)

    def execute(self, node, scope):
        kind, *args = node
        if kind == 'sequence':
            for item in args[0]:
                self.execute(item, scope)
        elif kind == 'if':
            self.execute(args[1] if self.evaluate(args[0], scope) else args[2], scope)
        elif kind == 'assign':
            scope[args[0]] = self.evaluate(args[1], scope)
        elif kind == 'call':
            value = self.evaluate(args[0], scope)
            if callable(value):
                value()
        elif kind == 'exit':
            raise ReturnFromPascal()
        elif kind == 'try':
            try:
                self.execute(args[0], scope)
            except Exception:
                self.execute(args[1], scope)
        else:
            raise AssertionError(kind)


class InstallerCallbacks:
    def __init__(self, source, externals, execute):
        self.source, self.externals, self.exec = source, externals, execute

    def call(self, name, **arguments):
        match = re.search(r'(?mi)^(?:function|procedure) ' + name + r'\b', self.source)
        assert match, name
        rest = self.source[match.start():]
        # Stop at the next declaration; keep only the function's begin/end body.
        end = re.search(r'(?mi)^(?:function|procedure) ', rest[1:])
        if end:
            rest = rest[:end.start() + 1]
        # Comments between functions aren't part of the executable body.
        rest = rest[:rest.rfind('end;') + 4]
        rest = rest[re.search(r'\bbegin\b', rest).start():]
        program = PascalBody(rest)
        scope = dict(self.externals, true=True, false=False, resultcode=0, result=None, **arguments)
        def execute(*args):
            ok, code = self.exec(*args)
            scope['resultcode'] = code
            return ok
        scope['exec'] = execute
        scope['unregisterhelperrecovery'] = lambda preview: self.call('UnregisterHelperRecovery', preview=preview)
        try:
            program.execute(program.tree, scope)
        except ReturnFromPascal:
            pass
        return scope['result']
