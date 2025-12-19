import ast
import re


class SourceParser:
    """
    Responsible for File I/O, AST generation, and Pragma detection.
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