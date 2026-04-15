# Publishing apimon to PyPI

## Prerequisites

- A [PyPI](https://pypi.org/) account
- `build` and `twine` installed:
  ```bash
  pip install build twine
  ```

## 1. Update Version

Update the version in `apimon/__init__.py`:

```python
__version__ = "0.2.0"  # or your new version
```

## 2. Build the Package

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build
python3 -m build
```

This creates `dist/` with `.tar.gz` and `.whl` files.

## 3. Test on TestPyPI (Recommended)

```bash
python3 -m twine upload --repository testpypi dist/*
```

Test installation:
```bash
pip install --index-url https://test.pypi.org/simple/ apimon
```

## 4. Upload to PyPI

```bash
python3 -m twine upload dist/*
```

## 5. Verify Installation

```bash
pip install apimon
apimon --version
apimon --help
```

## Optional: LLM Dependencies

Users who want LLM features should install:
```bash
pip install apimon[llm]
```

This installs `openai`, `google-genai`, and `anthropic` packages.
