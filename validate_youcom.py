#!/usr/bin/env python3
"""
Simple validation script for the You.com backend without full dependency imports.
"""

import sys
import ast
import os

def validate_python_syntax(filepath):
    """Validate Python syntax without importing."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        ast.parse(content)
        print(f"✓ {filepath}: Syntax valid")
        return True
    except SyntaxError as e:
        print(f"✗ {filepath}: Syntax error - {e}")
        return False

def check_file_exists(filepath):
    """Check if file exists."""
    if os.path.exists(filepath):
        print(f"✓ {filepath}: File exists")
        return True
    else:
        print(f"✗ {filepath}: File missing")
        return False

def main():
    """Run validation checks."""
    print("=== You.com Backend Validation ===")
    
    files_to_check = [
        "src/deep_research_mcp/backends/youcom_backend.py",
        "src/deep_research_mcp/backends/__init__.py",
        "tests/test_agents.py"
    ]
    
    all_good = True
    
    for filepath in files_to_check:
        if not check_file_exists(filepath):
            all_good = False
        elif not validate_python_syntax(filepath):
            all_good = False
    
    if all_good:
        print("\n✓ All validation checks passed!")
        return 0
    else:
        print("\n✗ Some validation checks failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())