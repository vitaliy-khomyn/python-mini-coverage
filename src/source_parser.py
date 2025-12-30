import ast
import re
import types
from typing import Tuple, Set, Optional, Iterable


class SourceParser:
    """
    Handles file I/O, AST generation, Bytecode compilation, and Pragma detection.
    """

    def parse_source(
        self,
        filename: str,
        exclude_patterns: Optional[Iterable[str]] = None
    ) -> Tuple[Optional[ast.Module], Set[int]]:
        """
        Read a source file and parse it into an AST.

        Scans for '# pragma: no cover' comments AND provided regex patterns
        to populate the ignored lines set.

        Args:
            filename (str): Path to the source file.
            exclude_patterns (iterable): List of regex strings to ignore.
        Returns:
            tuple: (ast.Module, set) containing the AST tree and a set of ignored line numbers.
                   Returns (None, set()) on failure.
        """
        ignored_lines: Set[int] = set()
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()

            source_text = "".join(source_lines)
            tree = ast.parse(source_text)

            # default pragma pattern
            regexes = [re.compile(r'#.*pragma:\s*no\s*cover', re.IGNORECASE)]

            # add user-defined patterns
            if exclude_patterns:
                for pat in exclude_patterns:
                    try:
                        regexes.append(re.compile(pat))
                    except re.error:
                        pass  # ignore invalid regex

            for i, line in enumerate(source_lines):
                for regex in regexes:
                    if regex.search(line):
                        ignored_lines.add(i + 1)
                        break

            return tree, ignored_lines

        except (SyntaxError, OSError, UnicodeDecodeError):
            return None, set()

    def compile_source(self, filename: str) -> Optional[types.CodeType]:
        """
        Compile the source file into a Python Code Object.
        Args:
            filename (str): Path to the source file.
        Returns:
            types.CodeType: The compiled code object, or None on failure.
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                source = f.read()
            return compile(source, filename, 'exec')
        except (SyntaxError, OSError, UnicodeDecodeError):
            return None
