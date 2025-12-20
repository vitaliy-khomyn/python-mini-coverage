import ast
import re


class SourceParser:
    """
    Responsible for File I/O, AST generation, Bytecode compilation, and Pragma detection.
    """

    def parse_source(self, filename):
        """
        Returns tuple: (ast_tree, ignored_lines_set)
        """
        ignored_lines = set()
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()

            source_text = "".join(source_lines)
            tree = ast.parse(source_text)

            # Scan for pragmas
            # Pattern: # ... pragma: no cover ...
            pragma_pattern = re.compile(r'#.*pragma:\s*no\s*cover', re.IGNORECASE)

            for i, line in enumerate(source_lines):
                if pragma_pattern.search(line):
                    ignored_lines.add(i + 1)  # Lineno is 1-based in AST

            return tree, ignored_lines

        except (SyntaxError, OSError, UnicodeDecodeError):
            return None, set()

    def compile_source(self, filename):
        """
        Compiles the source file into a Code Object (bytecode).
        Returns the code object or None on failure.
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source = f.read()
            # 'exec' mode is used for module-level compilation
            return compile(source, filename, 'exec')
        except (SyntaxError, OSError, UnicodeDecodeError):
            return None