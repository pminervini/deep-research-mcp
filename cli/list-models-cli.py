#!/usr/bin/env python3
"""
CLI script to list available OpenAI models using the OpenAI Python API.
"""

import os
import sys
from openai import OpenAI


def main():
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("Error: OPENAI_API_KEY environment variable is not set", file=sys.stderr)
            sys.exit(1)
        
        client = OpenAI(api_key=api_key)
        
        print("Fetching available OpenAI models...")
        models = client.models.list()
        
        print(f"\nFound {len(models.data)} models:")
        print("-" * 50)
        
        for model in sorted(models.data, key=lambda x: x.id):
            print(f"ID: {model.id}")
            print(f"Created: {model.created}")
            print(f"Owned by: {model.owned_by}")
            print("-" * 30)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()